---
phase: 01-infra-swap-drop-envoy-wire-cloud-map
plan: "02"
subsystem: infra
tags: [cloudmap, servicediscovery, boto3, ecs, python, fastapi]

# Dependency graph
requires:
  - phase: 01-infra-swap-drop-envoy-wire-cloud-map/01-01
    provides: sd client, CLOUDMAP_NAMESPACE_ID, cloudmap_service_name helper already added in 01-01
provides:
  - create_cloudmap_service function in controller-python/main.py
  - Idempotent Cloud Map service creation with FailureThreshold 1
  - Bootstrap step 3 creates {workspaceId}-apps Cloud Map service before ECS service launch
  - cloudmapServiceId in bootstrap response
affects:
  - phase-02-app-routing (register_instance/deregister_instance will use cloudmap_service_id)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Idempotent Cloud Map service creation: list_services paginator check before create_service"
    - "Bootstrap step ordering: IAM -> task def -> Cloud Map -> ECS service -> TG/ALB -> wait"

key-files:
  created: []
  modified:
    - controller-python/main.py

key-decisions:
  - "FailureThreshold: 1 ensures crashed app tasks are auto-deregistered from Cloud Map on first health check failure"
  - "Idempotent bootstrap: list_services check before create_service prevents duplicate Cloud Map services"
  - "Cloud Map service created as step 3, before ECS service (step 4) — establishes registry before workspace goes live"

patterns-established:
  - "Cloud Map idempotency: paginate list_services with NAMESPACE_ID filter, match by name, return existing ID"
  - "Bootstrap wiring order: create_cloudmap_service called after register_workspace_task_definition, before ensure_workspace_service"

requirements-completed:
  - CMAP-01
  - CMAP-04
  - CTRL-04

# Metrics
duration: 8min
completed: 2026-03-31
---

# Phase 01 Plan 02: Cloud Map Service Creation Summary

**Cloud Map `{workspaceId}-apps` service created at bootstrap via idempotent `create_cloudmap_service` with FailureThreshold 1 for auto-deregistration of crashed tasks**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-31T07:38:38Z
- **Completed:** 2026-03-31T07:46:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `create_cloudmap_service` function implemented with paginated idempotency check (list_services before create)
- `HealthCheckCustomConfig: {FailureThreshold: 1}` configured so crashed app task IPs are auto-deregistered on first failure
- Bootstrap wired as step 3 (after task def reg, before ECS service launch); `cloudmapServiceId` returned in response
- Note: Task 1 items (sd client, CLOUDMAP_NAMESPACE_ID, cloudmap_service_name) were already present from plan 01-01 execution

## Task Commits

Each task was committed atomically:

1. **Task 1: Add servicediscovery client, CLOUDMAP_NAMESPACE_ID, cloudmap_service_name** - `70ba9b0` (feat) — already committed in prior session
2. **Task 2: Implement create_cloudmap_service and wire into bootstrap** - `959f20d` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `controller-python/main.py` — added `create_cloudmap_service` function (lines 356-401), wired into `bootstrap_workspace` as step 3 with `cloudmapServiceId` in return dict

## Decisions Made

- FailureThreshold: 1 chosen (not 2 or 3) — fastest auto-deregistration on task crash, as the plan specifies
- DnsRecords TTL: 10 seconds — low TTL ensures stale IPs are not cached long after task crash
- Idempotent check uses paginator with NAMESPACE_ID filter and name match — safe to call bootstrap multiple times

## Deviations from Plan

None - plan executed exactly as written. Task 1 items (sd client, CLOUDMAP_NAMESPACE_ID, cloudmap_service_name) were already present in main.py from plan 01-01 execution and matched the plan spec precisely.

## Issues Encountered

None — all items already staged correctly from previous plan execution. Task 2 diff was clean and applied without conflict.

## User Setup Required

None - no external service configuration required beyond the existing `infrastructure-outputs.json` which already exports `cloudmap_namespace_id` from Terraform.

## Next Phase Readiness

- Cloud Map service creation is complete and wired into bootstrap
- Phase 2 (app routing) can now call `register_instance`/`deregister_instance` using the `cloudmap_service_id` returned by bootstrap
- The `sd` client is available globally in main.py for Phase 2 app start/stop handlers

---
*Phase: 01-infra-swap-drop-envoy-wire-cloud-map*
*Completed: 2026-03-31*
