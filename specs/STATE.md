# Project State

## Current Position

**Milestone:** v0.1 Alpha — ✅ Shipped 2026-03-30
**Phase:** Post-milestone — active development
**Current focus:** Multi-app type support + UI app control dropdown

---

## Project Reference

See: specs/PROJECT.md (updated 2026-03-30)

**Core value:** Instant app start/stop via ALB rule toggling, apps grouped under ECS services
**Current focus:** Add ReactJS + mkdocs app types; combined start/stop UI with app dropdown

---

## Decisions

| Decision | Rationale |
|----------|-----------|
| Python/FastAPI over Node.js | boto3 canonical; simpler |
| Multi-container task per workspace | ECS console service grouping requires service scheduler |
| ALB rule toggle for start/stop | No cold-start, container stays warm |
| No `loadBalancers` on ECS service | Manual TG registration enables N apps per workspace |
| CloudMap not used | ALB + IP-mode TGs bypass DNS layer (see specs/adr/001-cloudmap-not-used.md) |

---

## Blockers

None

---

## Tech Stack (Actual)

**Controller API:**
- Python 3.12 + FastAPI + boto3
- Docker (`python:3.12-slim`, port 8000)
- Reads `infrastructure-outputs.json` at startup

**Web UI:**
- Node.js + Express (port 3000)
- Proxies API calls to controller

**Infrastructure:**
- Terraform ~5.0 (base infra only)
- AWS Fargate, eu-west-1, domain: brewer.muhilvannan.com

---

## Next Steps

- [x] v0.1 milestone archived
- [ ] Add ReactJS + mkdocs app types to controller
- [ ] Add GET /workspace/{id}/apps endpoint (ECS native list)
- [ ] Update UI: combined app control card with workspace dropdown
- [ ] EFS file mounting in task containers

---

## Quick Tasks Completed

| # | Description | Date | Directory |
|---|-------------|------|-----------|
| 001 | Add reactjs+mkdocs app types, multi-app UI dropdown, GET /workspace/{id}/apps | 2026-03-30 | — |
