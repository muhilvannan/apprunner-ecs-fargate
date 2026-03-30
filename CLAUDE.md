# ECS App Tester — Claude Instructions

## Project Overview

Multi-workspace application management system on AWS ECS Fargate.

## BRANCH: task-level-app-experiments

> **This branch implements Option C (Cloud Map + Node.js proxy), superseding the Option B (Envoy) architecture.**
> See [specs/adr/002-workspace-service-multicontainer-task.md](specs/adr/002-workspace-service-multicontainer-task.md) for the full 3-option comparison.

### Architecture on this branch (Option C — target state)

```
ECS Cluster (ecs-app-tester-exp-dev, eu-west-1)
  └── Service: {workspaceId}       desiredCount=1
        └── Task: {workspaceId}-task    ← service-managed (landing-page only)
              └── Container: landing-page   port 3001  (workspace hub UI + Cloud Map proxy)

Standalone App Tasks (run_task — NOT under service):
  ├── Task: {workspaceId}-{appId}   IAM role: {workspaceId}-app-role
  └── Task: {workspaceId}-{appId2}  IAM role: {workspaceId}-app-role

ALB (ecs-app-tester-exp-dev-alb)
  └── /workspace{id}/*  → TG: {workspaceId}-tg  → Landing Page :3001

Cloud Map (workspace-discovery.local):
  {workspaceId}-apps service:
    ├── instance: {appId}  → {taskIP}:{port}  (registered on app start)
    └── instance: {appId2} → {taskIP}:{port}  (auto-deregisters on task crash)

Landing page routing:
  /workspace{id}/{appId}/*  →  http-proxy-middleware → Cloud Map lookup → {taskIP}:{port}
  /workspace{id}            →  serves index.html (workspace hub)

Domain: builder.muhilvannan.com
```

### Key Design Decisions (this branch)

- **1 ECS Service per workspace** — contains landing-page container only (no Envoy)
- **1 `run_task` per app** — independent lifecycle, own ENI, own IAM role
- **Start/Stop = Cloud Map register/deregister + task run/stop** — no ALB rule changes
- **1 ALB rule per workspace** — always forward to landing page; landing page handles per-app routing
- **Per-workspace IAM role** — `{workspaceId}-app-role` scoped to ECS describe, denies lateral movement
- **Landing page hub** — Node.js app with iframe embeds, app status cards, Cloud Map proxy
- **Cloud Map** — `register_instance`/`deregister_instance` on app start/stop; health checks auto-deregister crashed tasks

## Development Standards

### Infra Cost — Experiment Stack

> **This is a personal development experiment stack. Cost efficiency takes priority over resilience.**

- **Single NAT Gateway only** — do NOT add a second NAT GW for HA. The experiment stack never needs cross-AZ NAT redundancy.
- **No multi-AZ resource redundancy** — single NAT GW, single private route table shared by all private subnets.
- **No standby or failover resources** — RDS Multi-AZ, redundant NAT, cross-region replication are all out of scope.
- **No EIP hoarding** — 1 EIP for the NAT GW, none pre-allocated.
- If Terraform suggests adding resilience resources (second NAT GW, standby instances), reject and keep single-instance.

### General

- Never commit `infrastructure-outputs.json` — contains live AWS resource IDs
- Refresh Docker and local setup after any controller or infra change (see "After Making Changes")
- Keep `specs/` up to date — all architecture decisions, planning docs, and ADRs live there

## Components

| Component | Path | Tech | Port |
|-----------|------|------|------|
| Controller API | `controller-python/` | Python 3.12, FastAPI, Boto3, Docker | 8000 |
| Landing Page | `ui-nodejs/workspace-landing/` | Node.js, Express, http-proxy-middleware | 3001 |
| Web UI (legacy) | `ui-nodejs/` | Node.js, Express | 3000 |
| Infrastructure | `terraform/` | Terraform ~5.0, AWS | — |

## Naming Conventions

```
ECS service:          {workspaceId}
Task def family:      {workspaceId}-task
App task family:      {workspaceId}-{appId}
Container name:       landing-page  (workspace task)
Target group:         {workspaceId}-tg   (max 32 chars — 1 per workspace)
Cloud Map service:    {workspaceId}-apps  (in workspace-discovery.local)
Cloud Map instance:   {appId}  → {taskIP}:{port}
ALB path:             /workspace{workspaceId}/*  → landing page
App URL:              https://builder.muhilvannan.com/workspace{workspaceId}/{appId}
```

## API Endpoints

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/workspace/bootstrap` | Register task def (landing-page only), create Cloud Map service, create service (desiredCount=1), create TG + ALB rule, wait for task IP |
| `GET`  | `/workspace/{id}/apps` | Query Cloud Map for registered app instances |
| `POST` | `/app/start` | `run_task` → `wait_for_task_ip` → `register_instance` in Cloud Map |
| `POST` | `/app/stop` | `deregister_instance` from Cloud Map → `stop_task` |
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
3. **Landing page changes** — restart landing page container or `make api-rebuild` if bundled
4. **Re-bootstrap after infra redeploy** — run `make cleanup-aws` first, then re-bootstrap via UI

## Key Files

- [controller-python/main.py](controller-python/main.py) — all AWS logic (boto3): task defs, ECS service, TGs, ALB rules, Cloud Map
- [controller-python/Dockerfile](controller-python/Dockerfile) — Python 3.12-slim
- [controller-python/Makefile](controller-python/Makefile) — mounts `~/.aws` + `infrastructure-outputs.json`
- [ui-nodejs/workspace-landing/server.js](ui-nodejs/workspace-landing/server.js) — landing page (proxy + Cloud Map SDK)
- [ui-nodejs/index.html](ui-nodejs/index.html) — legacy web UI (dark theme, card layout)
- [terraform/](terraform/) — base infra (VPC, ECS cluster, ALB, IAM, EFS, Cloud Map namespace)
- [terraform/cloudmap.tf](terraform/cloudmap.tf) — Cloud Map namespace `workspace-discovery.local`
- [infrastructure-outputs.json](infrastructure-outputs.json) — deployed resource IDs (never commit)
- [specs/adr/](specs/adr/) — architecture decision records
- [specs/REQUIREMENTS.md](specs/REQUIREMENTS.md) — v1 requirements with REQ-IDs
- [specs/ROADMAP.md](specs/ROADMAP.md) — phase breakdown

## AWS Environment

- Region: `eu-west-1`
- Environment: `dev`
- Domain: `builder.muhilvannan.com`
- VPC CIDR: `10.0.0.0/16`
- AZs: `eu-west-1a`, `eu-west-1b`
- Cluster: `ecs-app-tester-exp-dev`
- Log group: `/ecs/app-tester`
- Cloud Map namespace: `workspace-discovery.local`

## App Types

| Type | Port | Notes |
|------|------|-------|
| `streamlit` | 8501 | `--server.baseUrlPath` set per workspace/app |
| `fastapi` | 8000 | Installs fastapi + uvicorn at runtime |
| `reactjs` | 3000 | Serves React CDN HTML via python http.server |
| `mkdocs` | 8001 | Installs mkdocs at runtime |
| `custom` | 8080 | Sleep placeholder |

All images: `public.ecr.aws/docker/library/python:3.12-slim` — no Docker Hub auth needed.

## Bootstrap Flow (Option C)

1. Attach S3 IAM policy to task role (if s3Bucket provided)
2. `register_workspace_task_definition` — single-container (landing-page only), family=`{workspaceId}-task`
3. `create_cloudmap_service` — creates `{workspaceId}-apps` service in `workspace-discovery.local`
4. `ensure_workspace_service` — create/update service `{workspaceId}` at desiredCount=1
5. `ensure_target_group` + `ensure_listener_rule` (forward to landing page TG)
6. `wait_for_task_running` — polls until service scheduler starts task
7. `wait_for_task_ip` — polls ENI attachment for `privateIPv4Address`
8. Returns service name + workspace URL (apps started individually via `/app/start`)
