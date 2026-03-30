# ECS App Tester

A multi-workspace application management system on AWS ECS Fargate. Deploy multiple applications in isolated workspaces, control them via ALB-based start/stop (no cold-start), and scale them instantly.

**Status:** v0.1 Alpha ✅ **Live:** https://brewer.muhilvannan.com

---

## What It Does

- **One workspace = one ECS service** with a multi-container task (one container per app)
- **Start/stop via ALB rule toggle** — no container cold-start, instant response
- **Multiple app types:** Streamlit, FastAPI, React.js, mkDocs, or custom Python
- **Always-running containers** on private subnets behind a public ALB
- **S3 sync endpoints** for user app code and files
- **Infrastructure as Code** — Terraform provisions all AWS resources

```
┌─────────────────────┐
│  Browser (3000)     │
│  brewer.muhilvannan │
└──────────┬──────────┘
           │ HTTP/HTTPS
           ▼
┌─────────────────────────────────┐
│  Express UI (localhost:3000)     │  ← Node.js proxy
│  ui-nodejs/app.js               │
└──────────┬──────────────────────┘
           │ JSON API (localhost:8000)
           ▼
┌─────────────────────────────────┐
│  FastAPI Controller (port 8000)  │  ← Python + boto3
│  controller-python/main.py       │
└──────────┬──────────────────────┘
           │ boto3 AWS SDK calls
           ▼
      AWS (eu-west-1)
    ┌─────────────────┐
    │  ECS Cluster    │
    │  ALB (443/80)   │
    │  VPC, EFS, IAM  │
    └─────────────────┘
```

---

## Architecture

### Core Concept

**One Service Per Workspace** (required for ECS console visibility):
```
ECS Service: {workspaceId}
  ├─ desiredCount=1 (always running)
  └─ Task: {workspaceId}-task
       ├─ Container: app1  (port 8501 if streamlit)
       ├─ Container: app2  (port 8000 if fastapi)
       └─ Container: appN  (port varies)
```

**ALB Listener Rules** per app:
```
/workspace{id}/app1*  →  forward (running)  | fixed-response 503 (stopped)
/workspace{id}/app2*  →  forward (running)  | fixed-response 503 (stopped)
```

**Start/Stop Logic**: Toggle the ALB rule action. Containers never stop — traffic is toggled.

### Why This Architecture?

- **AWS hard constraint:** Tasks launched via `run_task` never appear under a service in the console. Only the service scheduler's tasks are visible. So we use one service, one task, all apps as containers.
- **No cold-start:** ALB rule toggle is instant. No `stop_task` / `start_task` delays.
- **Multi-app grouping:** All workspace apps visible together under one service in the AWS console.

See [specs/adr/002-workspace-service-multicontainer-task.md](specs/adr/002-workspace-service-multicontainer-task.md) for the locked architectural decision.

---

## Components

| Component | Path | Tech | Port | Purpose |
|-----------|------|------|------|---------|
| **Controller API** | `controller-python/` | Python 3.12 + FastAPI + boto3 | 8000 | AWS ECS/ALB/IAM management |
| **Web UI** | `ui-nodejs/` | Node.js + Express | 3000 | Web interface, proxies to controller |
| **Infrastructure** | `terraform/` | Terraform ~5.0 | — | VPC, ECS, ALB, IAM, EFS, Route53 |

---

## App Types Supported

The controller dynamically configures containers for these app types:

| Type | Port | Runtime | Notes |
|------|------|---------|-------|
| **streamlit** | 8501 | Python 3.12 + pip | `hello` demo app, `--server.baseUrlPath` for ALB routing |
| **fastapi** | 8000 | Python 3.12 + pip + uvicorn | Minimal JSON API demo |
| **reactjs** | 3000 | Python 3.12 + http.server | React CDN HTML served via Python |
| **mkdocs** | 8001 | Python 3.12 + pip | MkDocs static site demo |
| **custom** | 8080 | Python 3.12 | Sleep placeholder (extend as needed) |

All images: `public.ecr.aws/docker/library/python:3.12-slim` (no Docker Hub auth required).

---

## API Endpoints

All endpoints are proxied through the Express UI to the FastAPI controller:

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/workspace/bootstrap` | Register task def, create service, create TGs + ALB rules |
| `GET` | `/workspace/{id}/apps` | List apps in running task + rule states |
| `POST` | `/app/start` | Enable ALB rule (forward traffic) |
| `POST` | `/app/stop` | Disable ALB rule (return 503) |
| `PUT` | `/app/sync` | List S3 objects for syncing |
| `GET` | `/health` | Health check + AWS caller identity |

---

## Quick Start

### Prerequisites
- AWS account with credentials configured (`aws configure`)
- Terraform 1.0+
- Docker (for local testing)
- Make

### 1. Deploy Infrastructure (Phase 01)

```bash
cd terraform
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
terraform output -json > ../infrastructure-outputs.json
```

**Expected:** 35 AWS resources created in ~5 minutes

### 2. Build & Run Controller (Phase 02)

```bash
make api-build        # Build controller Docker image
make api-run          # Start controller (mounts ~/.aws + infrastructure-outputs.json)
make ui-start         # Start UI (npm install if needed)
```

**Access:** http://localhost:3000

### 3. Bootstrap a Workspace

**Via UI:** Enter workspace ID, select app types, click "Bootstrap"

**Via API:**
```bash
curl -X POST http://localhost:3000/api/workspace/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{
    "workspaceId": "ws-001",
    "apps": [
      {"name": "demo", "type": "streamlit"}
    ]
  }'
```

### 4. Start an App

```bash
curl -X POST http://localhost:3000/api/app/start \
  -H 'Content-Type: application/json' \
  -d '{
    "workspaceId": "ws-001",
    "appId": "demo"
  }'
```

Visit: https://brewer.muhilvannan.com/workspace-001/demo

---

## Make Commands

### Controller
```bash
make api-build        # docker build controller
make api-run          # docker run (mounts ~/.aws + infra outputs)
make api-rebuild      # stop + build + run
make api-stop         # docker stop
make api-logs         # docker logs -f
make api-clean        # remove image
```

### UI
```bash
make ui-install       # npm install
make ui-start         # node app.js (port 3000)
```

### Infrastructure
```bash
make tf-init          # terraform init
make tf-plan          # terraform plan
make tf-apply         # terraform apply
make tf-output        # terraform output → infrastructure-outputs.json
make tf-destroy       # tear down all AWS resources
make cleanup-aws      # stop all tasks, delete TGs/rules
```

---

## Directory Structure

```
apprunner-ecs-fargate/
├── controller-python/         # FastAPI controller
│   ├── main.py               # All AWS logic (boto3)
│   ├── Dockerfile            # Python 3.12-slim
│   ├── requirements.txt       # Dependencies
│   └── Makefile              # docker build/run
├── ui-nodejs/                # Express web UI
│   ├── app.js                # Routes + proxies
│   ├── index.html            # Dark theme frontend
│   ├── package.json          # Dependencies
│   └── Makefile              # npm install/start
├── terraform/                # AWS infrastructure
│   ├── main.tf               # Provider config
│   ├── vpc.tf                # VPC, subnets, NAT, IGW
│   ├── ecs.tf                # ECS cluster, CloudWatch
│   ├── alb.tf                # ALB, target groups, listeners
│   ├── iam.tf                # IAM roles & policies
│   ├── efs.tf                # EFS file system
│   ├── variables.tf          # Input variables
│   ├── outputs.tf            # Output variables
│   └── terraform.tfvars      # Dev configuration
├── specs/                    # Documentation
│   ├── PROJECT.md            # Vision & architecture
│   ├── ROADMAP.md            # Release timeline
│   ├── MILESTONES.md         # v0.1 Alpha details
│   ├── STATE.md              # Current status & decisions
│   ├── adr/                  # Architecture Decision Records
│   └── milestones/           # Historical milestones
├── infrastructure-outputs.json # Terraform outputs (auto-gen)
├── CLAUDE.md                 # Dev instructions (you are here)
└── README.md                 # This file
```

---

## AWS Environment

| Variable | Value |
|----------|-------|
| **Region** | `eu-west-1` |
| **Environment** | `dev` |
| **Cluster** | `ecs-app-tester-dev` |
| **Domain** | `brewer.muhilvannan.com` |
| **VPC CIDR** | `10.0.0.0/16` |
| **Availability Zones** | `eu-west-1a`, `eu-west-1b` |
| **Log Group** | `/ecs/app-tester` |

---

## Naming Conventions

```
ECS service:      {workspaceId}
Task def family:  {workspaceId}-task
Container name:   {appId}
Target group:     {workspaceId}-{appId}-tg  (max 32 chars)
ALB path:         /workspace{workspaceId}/{appId}*
App URL:          https://brewer.muhilvannan.com/workspace{workspaceId}/{appId}
```

---

## Key Architectural Decisions

| Decision | Rationale | See Also |
|----------|-----------|----------|
| **Python/FastAPI over Node.js** | boto3 is canonical; simpler stack | — |
| **Multi-container task** | Required for ECS console grouping | [ADR-002](specs/adr/002-workspace-service-multicontainer-task.md) |
| **ALB rule toggle for start/stop** | No container cold-start | — |
| **No CloudMap** | ALB target groups work without it | [ADR-001](specs/adr/001-cloudmap-not-used.md) |
| **No `loadBalancers` on service** | Manual TG registration enables N apps per service | — |

---

## Next Steps

### Completed (v0.1)
- ✅ Terraform base infrastructure provisioned
- ✅ Controller API with boto3 AWS integration
- ✅ Workspace bootstrap flow
- ✅ App start/stop via ALB rules
- ✅ Streamlit base URL path fix
- ✅ Web UI for management

### Future Enhancements
- [ ] EFS file mounting in task containers
- [ ] S3 ↔ EFS sync implementation
- [ ] Formal test suite
- [ ] Pre-built app code templates
- [ ] User authentication & RBAC
- [ ] Cost tracking per workspace

---

## Documentation

For deeper information:

- **Architecture & Vision:** [specs/PROJECT.md](specs/PROJECT.md)
- **Release Timeline:** [specs/ROADMAP.md](specs/ROADMAP.md)
- **Current Status:** [specs/STATE.md](specs/STATE.md)
- **v0.1 Details:** [specs/MILESTONES.md](specs/MILESTONES.md)
- **Architecture Decisions:** [specs/adr/](specs/adr/)
- **Developer Instructions:** [CLAUDE.md](CLAUDE.md)

---

## Development

**Local setup** (see CLAUDE.md for detail):

```bash
# After changes to controller or UI code
make api-rebuild && make api-run  # for controller changes
make ui-start                      # for UI changes (hot reload)

# After infra changes
make tf-plan && make tf-apply && make tf-output
```

---

## License

MIT License — see [LICENSE](LICENSE) file.

---

**Project Status:** v0.1 Alpha shipped 2026-03-30. Live at https://brewer.muhilvannan.com
