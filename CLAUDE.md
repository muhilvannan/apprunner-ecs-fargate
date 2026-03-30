# ECS App Tester — Claude Instructions

## Project Overview

Multi-workspace application management system on AWS ECS Fargate.

## BRANCH: task-level-app-experiments

> **This branch intentionally overrides the main branch architecture (ADR-002).**
> See [specs/adr/002-workspace-service-multicontainer-task.md](specs/adr/002-workspace-service-multicontainer-task.md) for the full comparison.

### Architecture on this branch

```
ECS Cluster (ecs-app-tester-exp-dev, eu-west-1)
  └── Service: {workspaceId}       desiredCount=1
        └── Task: {workspaceId}-task    ← service-managed (landing page + Envoy)
              ├── Container: landing-page   port 3001  (workspace hub UI + Envoy config API)
              └── Container: envoy          port 8080  (L7 proxy, shared emptyDir config)

Standalone App Tasks (run_task — NOT under service):
  ├── Task: {workspaceId}-{appId}   IAM role: {workspaceId}-app-role
  └── Task: {workspaceId}-{appId2}  IAM role: {workspaceId}-app-role

ALB (ecs-app-tester-exp-dev-alb)
  └── /workspace{id}/*  → TG: {workspaceId}-tg  → Envoy :8080

Envoy routes (hot-reloaded via Admin API + SIGHUP):
  /workspace{id}/{appId}/*  →  {appTaskIP}:{port}
  /workspace{id}            →  127.0.0.1:3001 (landing page)

Domain: builder.muhilvannan.com
```

### Key Design Decisions (this branch)

- **1 ECS Service per workspace** — contains landing-page + envoy only
- **1 `run_task` per app** — independent lifecycle, own ENI, own IAM role
- **Start/Stop = Envoy route add/remove + task run/stop** — no ALB rule changes
- **1 ALB rule per workspace** — always forward to Envoy; Envoy handles per-app routing
- **Per-workspace IAM role** — `{workspaceId}-app-role` scoped to ECS describe, denies lateral movement
- **Landing page hub** — Node.js app with iframe embeds, app status cards, Envoy config API
- **Envoy config API** — `POST /internal/routes/add|remove` rewrites config + SIGHUP reload

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
App URL:          https://builder.muhilvannan.com/workspace{workspaceId}/{appId}
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
- Domain: `builder.muhilvannan.com`
- VPC CIDR: `10.0.0.0/16`
- AZs: `eu-west-1a`, `eu-west-1b`
- Cluster: `ecs-app-tester-exp-dev`
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
