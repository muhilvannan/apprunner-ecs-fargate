---
phase: 01-infra-swap-drop-envoy-wire-cloud-map
plan: "01"
subsystem: infra
tags: [ecs, fargate, alb, cloud-map, envoy-removal, option-c]

# Dependency graph
requires: []
provides:
  - Single-container workspace task definition (landing-page only, no Envoy)
  - ALB target group pointing to LANDING_PAGE_PORT (3001)
  - TG registration using LANDING_PAGE_PORT
  - Removed ENVOY_PORT, ENVOY_ADMIN_PORT, _ENVOY constants from controller
affects:
  - 01-02
  - landing-page-server
  - cloud-map-wiring

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-container workspace task — landing-page is the sole container, volumes=[]"
    - "ALB forwards directly to landing page port 3001; landing page handles per-app proxy"

key-files:
  created: []
  modified:
    - controller-python/main.py

key-decisions:
  - "Removed Envoy sidecar entirely — Option C uses Node.js http-proxy-middleware in landing page instead"
  - "ALB TG now points to LANDING_PAGE_PORT (3001) directly; no Envoy port intermediary"
  - "volumes=[] passed explicitly to register_task_definition for clarity"

patterns-established:
  - "workspace task def = 1 container (landing-page), no shared volumes, no sidecar"
  - "TG registration always uses LANDING_PAGE_PORT constant"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

# Metrics
duration: 3min
completed: 2026-03-30
---

# Phase 01 Plan 01: Infra Swap — Strip Envoy, Fix TG Port Summary

**Removed Envoy sidecar and emptyDir volume from workspace task definition; ALB target group wired to landing-page port 3001 (LANDING_PAGE_PORT) instead of Envoy port 8080**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-30T23:09:51Z
- **Completed:** 2026-03-30T23:12:17Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- `register_workspace_task_definition` now produces a single-container task (landing-page only) with no mountPoints and `volumes=[]`
- Removed `ENVOY_PORT`, `ENVOY_ADMIN_PORT`, `_ENVOY` constants from controller
- `ensure_workspace_target_group` creates TG on port 3001 (`LANDING_PAGE_PORT`)
- `register_workspace_to_tg` registers workspace task IP at port 3001
- `/health` endpoint `arch` field updated to `per-app-run_task+cloudmap`
- All Envoy references in docstrings and comments removed

## Task Commits

Each task was committed atomically:

1. **Task 1: Strip Envoy container and emptyDir volume from workspace task definition** - `fdca8c2` (feat)
2. **Task 2: Fix ALB target group and TG registration to use LANDING_PAGE_PORT** - `dba75b5` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `controller-python/main.py` - Removed Envoy container def, volumes, constants; fixed TG port to 3001; updated arch tag and all docstrings

## Decisions Made
- `volumes=[]` passed explicitly (not omitted) so intent is clear in the register_task_definition call
- Updated all docstrings referring to "envoy" or "landing page + envoy" to reflect Option C reality

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Controller is ready for Cloud Map wiring (plan 01-02)
- `register_workspace_task_definition` produces the correct single-container task definition
- ALB routing chain is clean: ALB → TG (port 3001) → landing-page → Cloud Map proxy

---
*Phase: 01-infra-swap-drop-envoy-wire-cloud-map*
*Completed: 2026-03-30*
