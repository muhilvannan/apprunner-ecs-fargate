# ECS App Tester — Claude Instructions

## Project Overview

Multi-workspace application management system on AWS ECS Fargate.

## CRITICAL Architecture Rules

**DO NOT CHANGE these without an explicit user instruction. This has caused repeated mistakes.**

> **Workspace = 1 ECS Service (desiredCount=1, always running)**
> **All apps in a workspace = containers in ONE multi-container task**
> **Start/Stop = ALB listener rule toggle ONLY — NEVER `run_task` or `stop_task`**

### Why multi-container task (not 1 task per app)

AWS hard constraint: tasks launched via `run_task` NEVER appear under a service in the ECS
console — they always appear as standalone cluster-level tasks. The ONLY way a task is visible
under a service is if the **service scheduler** launched it (desiredCount=1). Therefore the
workspace service must own the task lifecycle. This means one service → one task → all apps
as containers in that task.

See [specs/adr/002-workspace-service-multicontainer-task.md](specs/adr/002-workspace-service-multicontainer-task.md)

```
ECS Cluster (ecs-app-tester-dev, eu-west-1)
  └── Service: {workspaceId}       desiredCount=1
        └── Task: {workspaceId}-task    ← launched by service scheduler, visible in console
              ├── Container: app1       (port varies by type)
              ├── Container: app2
              └── Container: appN

ALB (ecs-app-tester-dev-alb)
  ├── /workspace{id}/app1*  → TG: {id}-app1-tg  (forward | fixed-response 503)
  ├── /workspace{id}/app2*  → TG: {id}-app2-tg
  └── ...

Domain: brewer.muhilvannan.com
```

## Architecture

```
Browser (port 3000)
    ↓
Express UI (ui-nodejs/)
    ↓
FastAPI Controller (port 8000, Docker) — controller-python/
    ↓ boto3 AWS SDK calls
```

### Key Design Decisions

- **1 ECS Service per workspace** — `{workspaceId}`, desiredCount=1, service scheduler owns task
- **Multi-container task** — all apps share one task, one ENI, one private IP, different ports
- **Start/Stop = ALB rule toggle** — `forward` (running) ↔ `fixed-response 503` (stopped); containers never stop
- **No `run_task` / `stop_task`** — task lifecycle is managed entirely by the service
- **No Terraform at runtime** — controller uses boto3 directly; Terraform only provisions base infra
- **Infrastructure IDs** loaded at startup from `infrastructure-outputs.json` (mounted into container)
- **Streamlit base URL path** — `--server.baseUrlPath=/workspace{id}/{appId}` for static asset routing

## Components

| Component | Path | Tech | Port |
|-----------|------|------|------|
| Controller API | `controller-python/` | Python 3.12, FastAPI, Boto3, Docker | 8000 |
| Web UI | `ui-nodejs/` | Node.js, Express | 3000 |
| Infrastructure | `terraform/` | Terraform ~5.0, AWS | — |

## Naming Conventions

```
ECS service:      {workspaceId}
Task def family:  {workspaceId}-task
Container name:   {appId}
Target group:     {workspaceId}-{appId}-tg   (max 32 chars)
ALB path:         /workspace{workspaceId}/{appId}*
App URL:          https://brewer.muhilvannan.com/workspace{workspaceId}/{appId}
```

## API Endpoints

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/workspace/bootstrap` | Register multi-container task def, create service (desiredCount=1), create TGs + disabled ALB rules, wait for task IP, register targets |
| `GET`  | `/workspace/{id}/apps` | List containers in running task + ALB rule state per app |
| `POST` | `/app/start` | Enable ALB listener rule (forward) |
| `POST` | `/app/stop` | Disable ALB listener rule (fixed-response 503) |
| `PUT`  | `/app/sync` | List S3 objects for sync |
| `GET`  | `/health` | Config + caller identity check |

## Commands

### Local Development

```bash
make api-build        # build controller Docker image
make api-rebuild      # stop + rebuild
make api-run          # build + run (mounts ~/.aws and infrastructure-outputs.json)
make api-stop         # stop container
make api-clean        # remove image

make ui-install       # npm install
make ui-start         # start UI on port 3000

make cleanup-aws      # stop all ECS tasks/services, delete workspace TGs + ALB rules
```

### Terraform (base infra only)

```bash
make tf-init          # terraform init
make tf-plan          # review changes
make tf-apply         # deploy base infra
make tf-output        # export outputs → infrastructure-outputs.json (required after tf-apply)
make tf-destroy       # tear down all infra
```

### Controller Docker (direct)

```bash
cd controller-python
make build            # docker build
make run              # docker run (mounts ~/.aws:ro and infrastructure-outputs.json:ro)
make logs             # docker logs -f ecs-controller
make stop             # docker stop + rm
make clean            # remove image
```

## After Making Changes

1. **Controller code changes** — `make api-rebuild && make api-run`
2. **Infra changes** — `make tf-plan && make tf-apply && make tf-output`, then `make api-stop && make api-run`
3. **UI changes** — take effect immediately (no restart needed)
4. **Re-bootstrap after infra redeploy** — run `make cleanup-aws` first, then re-bootstrap via UI

## Key Files

- [controller-python/main.py](controller-python/main.py) — all AWS logic (boto3): task defs, ECS service, TGs, ALB rules
- [controller-python/Dockerfile](controller-python/Dockerfile) — Python 3.12-slim
- [controller-python/Makefile](controller-python/Makefile) — mounts `~/.aws` + `infrastructure-outputs.json`
- [ui-nodejs/index.html](ui-nodejs/index.html) — web UI (dark theme, card layout, dynamic app rows)
- [ui-nodejs/app.js](ui-nodejs/app.js) — Express proxy to controller
- [terraform/](terraform/) — base infra (VPC, ECS cluster, ALB, IAM, EFS, Route53)
- [infrastructure-outputs.json](infrastructure-outputs.json) — deployed resource IDs (never commit)
- [specs/adr/](specs/adr/) — architecture decision records

## AWS Environment

- Region: `eu-west-1`
- Environment: `dev`
- Domain: `brewer.muhilvannan.com`
- VPC CIDR: `10.0.0.0/16`
- AZs: `eu-west-1a`, `eu-west-1b`
- Cluster: `ecs-app-tester-dev`
- Log group: `/ecs/app-tester`

## App Types

| Type | Port | Notes |
|------|------|-------|
| `streamlit` | 8501 | `--server.baseUrlPath` set per workspace/app |
| `fastapi` | 8000 | Installs fastapi + uvicorn at runtime |
| `reactjs` | 3000 | Serves React CDN HTML via python http.server |
| `mkdocs` | 8001 | Installs mkdocs at runtime |
| `custom` | 8080 | Sleep placeholder |

All images: `public.ecr.aws/docker/library/python:3.12-slim` — no Docker Hub auth needed.

## Bootstrap Flow

1. Attach S3 IAM policy to task role (if s3Bucket provided)
2. `register_workspace_task_definition` — multi-container, family=`{workspaceId}-task`, one container per app
3. `ensure_workspace_service` — create/update service `{workspaceId}` at desiredCount=1
4. For each app: `ensure_target_group` + `ensure_listener_rule` (disabled, fixed-response 503)
5. `wait_for_task_running` — polls `list_tasks(serviceName=...)` until service scheduler starts task
6. `wait_for_task_ip` — polls ENI attachment for `privateIPv4Address`
7. `register_task_to_tgs` — registers `{ip}:{port}` to each app's TG
8. Returns service name + per-app URLs (all stopped until `/app/start` called)
