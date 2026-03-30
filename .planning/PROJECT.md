# ECS App Tester — Project Overview

## What This Is

A multi-workspace application management system on AWS ECS Fargate. The project has shipped v0.1 (multi-container task per workspace, ALB rule toggle) and is actively experimenting with a per-app isolated task architecture using Cloud Map service discovery for dynamic routing.

## Core Value

Per-app isolation (crash containment, independent CPU/memory) with a workspace hub UI — replacing monolithic multi-container task management with independently-lifecycled app tasks routed via Cloud Map + Node.js proxy.

## Tech Stack (Actual, as of v0.1 / experiment branch)

**Controller API:**
- Python 3.12 + FastAPI + boto3
- Docker (`python:3.12-slim`, port 8000)
- Reads `infrastructure-outputs.json` at startup for AWS resource IDs

**Web UI (Workspace Landing Page):**
- Node.js + Express (port 3001 in experiment, 3000 legacy UI)
- http-proxy-middleware for app request proxying (Option C)
- `@aws-sdk/client-servicediscovery` for Cloud Map lookups (Option C)

**Infrastructure:**
- Terraform ~5.0 (base infra — VPC, ECS cluster, ALB, IAM, EFS, Cloud Map)
- AWS Fargate, eu-west-1
- Single NAT Gateway (experiment stack — no HA required)

## Architecture

### Current Experiment (Option B — Envoy, branch: task-level-app-experiments)

```
Browser → ALB → Envoy :8080 → App Tasks (run_task)
                    ↑
             Landing Page :3001 (manages Envoy config via /internal/routes/*)

ECS Service: {workspaceId}  desiredCount=1
  └── Task: {workspaceId}-task
        ├── Container: landing-page  :3001
        └── Container: envoy         :8080   ← to be removed in Option C
```

### Target (Option C — Cloud Map + Node.js proxy)

```
Browser → ALB → TG: {workspaceId}-tg → Landing Page :3001
                                              │
              Cloud Map: workspace-discovery.local    │
              {wsId}-{appId}: A 10.0.x.x :PORT  ←────┘
                                              │
                              http-proxy-middleware → App Task :PORT

ECS Service: {workspaceId}  desiredCount=1
  └── Task: {workspaceId}-task
        └── Container: landing-page  :3001   ← single container (no Envoy)

App Tasks (run_task — unchanged):
  ├── Task: {workspaceId}-{appId}   registered in Cloud Map on start
  └── Task: {workspaceId}-{appId2}  deregistered on stop / auto-deregisters on crash
```

## Requirements

### Validated (v0.1 — main branch)

- ✓ ECS Fargate cluster provisioned via Terraform — v0.1
- ✓ Controller API in Docker with boto3 AWS SDK — v0.1
- ✓ Workspace bootstrap: multi-container task def + ECS service — v0.1
- ✓ App start/stop via ALB listener rule toggle — v0.1
- ✓ ALB path routing: `{domain}/workspace{id}/{appId}` — v0.1
- ✓ IAM roles scoped per workspace — v0.1
- ✓ Apps visible under workspace service in ECS console — v0.1
- ✓ Streamlit base URL path routing through ALB — v0.1

### Active (Option C Experiment — branch: task-level-app-experiments)

- [ ] Remove Envoy container from workspace task definition
- [ ] Remove emptyDir shared volume from workspace task
- [ ] Cloud Map service created per workspace at bootstrap
- [ ] App task registered in Cloud Map on app start (`register_instance`)
- [ ] App task deregistered from Cloud Map on app stop (`deregister_instance`)
- [ ] Landing page proxies app requests via http-proxy-middleware + Cloud Map lookup
- [ ] Landing page queries Cloud Map for live app list (`/internal/routes`)
- [ ] Remove Envoy config management code from controller and landing page
- [ ] ADR-002 updated with 3-option comparison table (Option A / B / C)
- [ ] Cheap-infra standards documented: single NAT GW, no HA for experiment stack

### Out of Scope

- ECS console service grouping for app tasks — `run_task` tasks never appear under service (AWS constraint, documented in ADR-002)
- Full Envoy L7 features (retries, circuit breaking) — not required for experiment scope
- Formal test suite — manual live testing
- Multi-region deployment — single region experiment

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python/FastAPI over Node.js for controller | boto3 is canonical AWS SDK | ✓ Good |
| Multi-container task per workspace (main) | Required for ECS console service grouping | ✓ Good |
| ALB rule toggle for start/stop (main) | No container cold-start on every start | ✓ Good |
| No `loadBalancers` on service | Manual IP registration enables N TGs per service | ✓ Good |
| `public.ecr.aws` images | No Docker Hub auth on Fargate | ✓ Good |
| CloudMap not used (main) | ALB + IP-mode TGs bypass DNS layer entirely | ✓ Good (main only) |
| Per-app run_task + Envoy routing (Option B) | App isolation experiment, but Envoy adds operational surface area | ⚠️ Revisit → Option C |
| Replace Envoy with Cloud Map + Node.js proxy (Option C) | Drops Envoy config management; Cloud Map is AWS-managed state; 50% fewer containers per workspace | — Pending |
| Single NAT Gateway for experiment stack | No HA needed; cost savings; resilience not required for dev experiment | ✓ Good |

## Context

- v0.1 shipped 2026-03-30 (main branch)
- Experiment branch `task-level-app-experiments` diverges from main at ADR-002
- Controller: ~923 LOC Python (main.py — monolithic, known tech debt)
- Infrastructure: ~1,200 LOC HCL (35 Terraform resources)
- Region: eu-west-1 | Domain: builder.muhilvannan.com
- Cloud Map namespace `workspace-discovery.local` already provisioned in `terraform/cloudmap.tf`
- Known debt: runtime pip install (~90s cold start), no EFS mounting, no test suite, monolithic main.py

## Constraints

- **Tech stack**: Python/FastAPI for controller, Node.js/Express for landing page — established
- **AWS region**: eu-west-1 — single region, no DR needed
- **Cost**: Single NAT GW only — no resilient/HA nat gateway for experiment stack
- **Console visibility**: run_task tasks are NOT visible under workspace service in ECS console (AWS platform constraint, no workaround)
- **Scope**: Experiment branch only — main branch multi-container model untouched

---
*Last updated: 2026-03-30 after Option C experiment initialization*
