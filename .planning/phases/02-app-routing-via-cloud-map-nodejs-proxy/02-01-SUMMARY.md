---
phase: 02-app-routing-via-cloud-map-nodejs-proxy
plan: "01"
subsystem: controller
tags: [cloudmap, servicediscovery, boto3, ecs, python, fastapi, envoy-removal]

# Dependency graph
requires:
  - phase: 01-infra-swap-drop-envoy-wire-cloud-map/01-02
    provides: create_cloudmap_service, sd client, CLOUDMAP_NAMESPACE_ID
provides:
  - get_cloudmap_service_id helper in controller-python/main.py
  - Cloud Map register_instance on app start (app_task_arn as InstanceId)
  - Cloud Map deregister_instance on app stop (deregister-first order)
  - discover_instances-based list_workspace_apps (no httpx)
  - Clean bootstrap_workspace (no Envoy route registration)
affects:
  - phase-02-plan-02 (landing page proxy relies on Cloud Map; controller side now complete)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cloud Map InstanceId = app_task_arn: ties instance lifecycle to ECS task ARN"
    - "Deregister-first stop: Cloud Map deregistration before ECS stop_task prevents in-flight traffic loss"
    - "discover_instances with HealthStatus=HEALTHY: only returns live app instances"

key-files:
  created: []
  modified:
    - controller-python/main.py

key-decisions:
  - "app_task_arn used as Cloud Map InstanceId — ties instance record directly to the ECS task, enabling deregister by ARN on stop"
  - "deregister_instance called before stop_app_task — prevents routing to task while it is still shutting down (D-01)"
  - "list_workspace_apps uses sd.discover_instances directly (not get_cloudmap_service_id) — discover_instances accepts service name, not service ID"

patterns-established:
  - "Cloud Map registration flow: run_task → wait_for_task_ip → get_cloudmap_service_id → sd.register_instance"
  - "Cloud Map deregistration flow: _find_app_task_arns → get_cloudmap_service_id → sd.deregister_instance → stop_app_task"
  - "App listing flow: sd.discover_instances(HealthStatus=HEALTHY) → set of app_id attributes → cross-ref task families"

requirements-completed:
  - CMAP-02
  - CMAP-03
  - CTRL-01
  - CTRL-02
  - CTRL-03

# Metrics
duration: 12min
completed: 2026-03-31
---

# Phase 02 Plan 01: Cloud Map Register/Deregister Wiring Summary

**Cloud Map `register_instance`/`deregister_instance` wired into app start/stop with task ARN as InstanceId; all Envoy route management (httpx, register_app_route, deregister_app_route, get_landing_page_ip) removed from controller**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-31T10:15:48Z
- **Completed:** 2026-03-31T10:27:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `get_cloudmap_service_id` helper added: list_services paginator pattern, raises RuntimeError if not found (requires bootstrap first)
- `httpx` import removed; `get_landing_page_ip`, `register_app_route`, `deregister_app_route` functions deleted
- `start_app`: now calls `sd.register_instance` with `InstanceId=app_task_arn` and `Attributes={AWS_INSTANCE_IPV4, AWS_INSTANCE_PORT, app_id}` after task reaches RUNNING
- `stop_app`: `sd.deregister_instance` called first (deregister-first order per D-01), then `stop_app_task`; handles `InstanceNotFound` gracefully
- `list_workspace_apps`: replaced httpx GET to landing page with `sd.discover_instances(HealthStatus=HEALTHY)` — running apps are those with a healthy Cloud Map instance
- `bootstrap_workspace`: removed `workspace_ip = wait_for_task_ip(...)` block and `register_app_route` call; `routeRegistered` field removed from app results

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_cloudmap_service_id, remove Envoy route functions** - `161971d` (feat)
2. **Task 2: Wire Cloud Map register/deregister into app start/stop, clean bootstrap** - `bb181f6` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `controller-python/main.py` — added `get_cloudmap_service_id` (lines 402-418); rewrote `start_app`, `stop_app`, `list_workspace_apps`, `bootstrap_workspace`; deleted `get_landing_page_ip`, `register_app_route`, `deregister_app_route`; removed `import httpx`

## Decisions Made

- `app_task_arn` as `InstanceId`: direct mapping from ECS task to Cloud Map instance; enables deregistration by task ARN without secondary lookup
- `discover_instances` called directly in `list_workspace_apps` without `get_cloudmap_service_id`: the `discover_instances` API accepts `NamespaceName + ServiceName` (not service ID), so the helper is not needed there
- `deregister_instance` before `stop_app_task`: deregister-first ensures no new traffic is proxied to the task while it is shutting down (per decision D-01 from phase planning)
- Graceful `InstanceNotFound` handling in `stop_app`: manual stop on an already-stopped or already-deregistered app does not raise; logs warning only
- `bootstrap_workspace` app loop kept in place but stripped of Cloud Map registration: bootstrap still starts apps but does not register them; the `/app/start` endpoint is the canonical Cloud Map registration path going forward

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — the task ARN was already in scope in `start_app` (`app_task_arn` variable renamed from `task_arns[0]` in the already-running branch for clarity). No additional imports or dependencies required.

## Self-Check: PASSED

- `controller-python/main.py` — verified present and modified
- Task 1 commit `161971d` — verified in git log
- Task 2 commit `bb181f6` — verified in git log
- 0 references to httpx, register_app_route, deregister_app_route, get_landing_page_ip
- `get_cloudmap_service_id` definition present (line 402)
- `sd.register_instance` in start_app (line 882)
- `sd.deregister_instance` in stop_app (line 917)
- `sd.discover_instances` in list_workspace_apps (line 784)

---
*Phase: 02-app-routing-via-cloud-map-nodejs-proxy*
*Completed: 2026-03-31*
