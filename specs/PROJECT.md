# ECS App Tester — Project Overview

## What This Is

A multi-workspace application management system on AWS ECS Fargate. Each workspace maps to one ECS service with an always-running multi-container task (one container per app). ALB listener rules control per-app routing — start/stop toggles traffic, not the task lifecycle.

## Core Value

Instant app start/stop via ALB rule toggling with no container cold-start, apps grouped visibly under ECS services.

## Tech Stack (Actual, as of v0.1)

**Controller API:**
- Python 3.12 + FastAPI + boto3
- Docker (`python:3.12-slim`, port 8000)
- Reads `infrastructure-outputs.json` at startup for AWS resource IDs

**Web UI:**
- Node.js + Express (port 3000)
- Proxies to controller API

**Infrastructure:**
- Terraform ~5.0 (base infra only — VPC, ECS, ALB, IAM, EFS)
- AWS Fargate, eu-west-1

## Architecture

```
Browser → Express UI (3000) → FastAPI Controller (8000) → boto3 → AWS

ECS Service: {workspaceId}  desiredCount=1
  └── Task: {workspaceId}-task
        ├── Container: app1  (port varies by type)
        └── Container: appN

ALB listener rule per app:
  /workspace{id}/{appId}*  →  forward (running) | fixed-response 503 (stopped)
```

## Requirements

### Validated (v0.1)

- ✓ ECS Fargate cluster provisioned via Terraform — v0.1
- ✓ Controller API in Docker with boto3 AWS SDK — v0.1
- ✓ Workspace bootstrap: registers multi-container task def + ECS service — v0.1
- ✓ App start/stop via ALB listener rule toggle — v0.1
- ✓ ALB path routing: `{domain}/workspace{id}/{appId}` — v0.1
- ✓ IAM roles scoped per workspace (S3 bucket access on bootstrap) — v0.1
- ✓ Apps visible under workspace service in ECS console — v0.1
- ✓ Streamlit base URL path routing through ALB — v0.1

### Active

- [ ] Multiple app type selection at bootstrap (ReactJS, mkdocs)
- [ ] App listing endpoint for workspace (GET /workspace/{id}/apps)
- [ ] Start/stop UI with app dropdown populated from ECS
- [ ] EFS file mounting in task containers
- [ ] User-supplied app code via S3 sync

### Out of Scope

- CloudMap service discovery — not needed for ALB-based routing (see ADR-001)
- Formal test suite — manual live testing confirmed working
- Per-app ECS service — would prevent multi-app grouping under workspace service

## Key Decisions

| Decision | Outcome | Notes |
|----------|---------|-------|
| Python/FastAPI over Node.js | ✓ Good | boto3 is canonical; simpler stack |
| Multi-container task per workspace | ✓ Good | Required for ECS console service grouping |
| ALB rule toggle for start/stop | ✓ Good | No container cold-start on every start |
| No `loadBalancers` on service | ✓ Good | Manual IP registration enables N TGs per service |
| `public.ecr.aws` images | ✓ Good | No Docker Hub auth on Fargate |
| CloudMap not used | ✓ Good | ALB + IP-mode TGs bypass DNS layer entirely |

## Context

- v0.1 shipped 2026-03-30
- Controller: ~520 LOC Python
- Infrastructure: ~1,200 LOC HCL (35 Terraform resources)
- Region: eu-west-1
- Domain: brewer.muhilvannan.com
- Known debt: runtime pip install (~90s cold start), no EFS mounting, no test suite

---
*Last updated: 2026-03-30 after v0.1 Alpha milestone*
