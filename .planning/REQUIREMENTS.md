# Requirements: ECS App Tester — Option C Experiment

**Defined:** 2026-03-30
**Branch:** task-level-app-experiments
**Core Value:** Per-app isolation with Cloud Map-backed routing — drop Envoy, simplify to single landing-page container per workspace

## v1 Requirements (Option C Experiment)

### Infra — Envoy Removal

- [x] **INFRA-01**: Workspace task definition contains only `landing-page` container (Envoy container removed)
- [x] **INFRA-02**: emptyDir shared volume removed from workspace task definition
- [x] **INFRA-03**: Envoy task definition registration removed from controller bootstrap flow

### Cloud Map — Service Discovery

- [x] **CMAP-01**: Controller creates a Cloud Map service (`{workspaceId}-apps`) per workspace at bootstrap time
- [x] **CMAP-02**: Controller registers app task IP + port in Cloud Map on app start (`register_instance`)
- [x] **CMAP-03**: Controller deregisters app instance from Cloud Map on app stop (`deregister_instance`)
- [x] **CMAP-04**: Cloud Map health check configured (`FailureThreshold: 1`) to auto-deregister crashed tasks

### Landing Page — Proxy + Discovery

- [x] **LP-01**: Landing page proxies `GET/POST /workspace{id}/{appId}/*` to app task via `http-proxy-middleware`
- [x] **LP-02**: Landing page resolves app IP + port via Cloud Map `DiscoverInstances` API call (not DNS)
- [x] **LP-03**: Landing page caches Cloud Map lookups with short TTL (≤5s) to reduce API calls per request
- [x] **LP-04**: Landing page returns 503 when app instance not found in Cloud Map (not running)
- [x] **LP-05**: `GET /internal/routes` queries Cloud Map API and returns live app list (replaces in-memory Envoy route table)
- [x] **LP-06**: Remove all Envoy config management code (`/internal/routes/add`, `/internal/routes/remove`, `writeEnvoyConfig`, `reloadEnvoy`, `kill -SIGHUP`)

### Controller — Route API Cleanup

- [x] **CTRL-01**: Remove `register_app_route` and `remove_app_route` controller functions (Envoy route management)
- [x] **CTRL-02**: App start flow: `run_task` → `wait_for_task_ip` → `register_instance` (replaces run_task → wait → POST /internal/routes/add)
- [x] **CTRL-03**: App stop flow: `deregister_instance` → `stop_task` (replaces POST /internal/routes/remove → stop_task)
- [x] **CTRL-04**: Bootstrap flow creates Cloud Map service before launching workspace service

### Docs & Standards

- [x] **DOC-01**: ADR-002 updated with unified 3-option comparison table (Option A / B / C side-by-side)
- [x] **DOC-02**: CLAUDE.md updated with cheap-infra development standard: single NAT GW, no HA for experiment stack
- [x] **DOC-03**: CLAUDE.md updated to reflect Option C architecture (remove Envoy references, add Cloud Map)

## v2 Requirements (Deferred)

### Observability

- **OBS-01**: CloudWatch log stream viewer in landing page UI for app container logs
- **OBS-02**: App resource usage (CPU/memory) displayed in workspace hub

### Reliability

- **REL-01**: Controller bootstrap idempotency (resume from last failed step, not full restart)
- **REL-02**: Exponential backoff on AWS API polling loops (currently fixed 5s × 24 retries)
- **REL-03**: App crash auto-restart via ECS restart policy (requires investigation of run_task restart behavior)

### Developer Experience

- **DX-01**: Controller refactored into layers (ecs_tasks.py, alb_routing.py, cloudmap.py, polling.py)
- **DX-02**: Input validation on workspace_id and app_id (alphanumeric + dash, max 63 chars)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Envoy L7 features (retries, circuit breaking) | Not required for experiment; Cloud Map proxy is sufficient |
| ECS console grouping for app tasks | AWS platform constraint — run_task tasks never appear under service |
| Per-app ECS service (Option D) | Would require N services per workspace; out of experiment scope |
| Multi-region deployment | Single region experiment only |
| Formal test suite | Manual live testing sufficient for experiment |
| NAT Gateway HA / redundancy | Experiment stack; cost savings outweigh resilience for dev use |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| CMAP-01 | Phase 1 | Complete |
| CMAP-02 | Phase 2 | Complete |
| CMAP-03 | Phase 2 | Complete |
| CMAP-04 | Phase 1 | Complete |
| LP-01 | Phase 2 | Complete |
| LP-02 | Phase 2 | Complete |
| LP-03 | Phase 2 | Complete |
| LP-04 | Phase 2 | Complete |
| LP-05 | Phase 2 | Complete |
| LP-06 | Phase 2 | Complete |
| CTRL-01 | Phase 2 | Complete |
| CTRL-02 | Phase 2 | Complete |
| CTRL-03 | Phase 2 | Complete |
| CTRL-04 | Phase 1 | Complete |
| DOC-01 | Phase 3 | Complete |
| DOC-02 | Phase 3 | Complete |
| DOC-03 | Phase 3 | Complete |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-30*
*Last updated: 2026-03-31 after 02-01 controller Cloud Map wiring*
