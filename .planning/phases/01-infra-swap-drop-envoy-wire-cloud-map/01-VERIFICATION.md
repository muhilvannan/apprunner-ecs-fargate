---
phase: 01-infra-swap-drop-envoy-wire-cloud-map
verified: 2026-03-31T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 1: Infra Swap — Drop Envoy, Wire Cloud Map — Verification Report

**Phase Goal:** Remove Envoy from workspace task; create Cloud Map service at bootstrap.
**Verified:** 2026-03-31
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workspace task definition registers only the landing-page container — no Envoy container present | VERIFIED | `container_defs` list (lines 269-290) has exactly one entry: `name: landing-page`. No second container. |
| 2 | No emptyDir shared volume in workspace task definition registration call | VERIFIED | `volumes = []` at line 292; `volumes=volumes` passed to `ecs.register_task_definition` at line 303. |
| 3 | ALB target group and TG registration use LANDING_PAGE_PORT (3001) not ENVOY_PORT (8080) | VERIFIED | `Port=LANDING_PAGE_PORT` in `ensure_workspace_target_group` (line 541); `Targets=[{"Id": ip, "Port": LANDING_PAGE_PORT}]` in `register_workspace_to_tg` (line 653). |
| 4 | ENVOY_PORT, ENVOY_ADMIN_PORT constants and _ENVOY image constant are removed from controller | VERIFIED | No occurrences of `ENVOY_PORT`, `ENVOY_ADMIN_PORT`, or `_ENVOY` anywhere in `main.py`. Constants section (lines 42-47) has only `LANDING_PAGE_PORT = 3001` and `_PY`, `_NODE` images. |
| 5 | Envoy environment variable (ENVOY_ADMIN_PORT) removed from landing-page container env | VERIFIED | `environment` list in landing-page container def (lines 276-280) contains only `WORKSPACE_ID`, `BASE_PATH`, `DOMAIN` — no `ENVOY_ADMIN_PORT`. |
| 6 | Bootstrap creates a Cloud Map service named {workspaceId}-apps in workspace-discovery.local before launching the workspace ECS service | VERIFIED | `create_cloudmap_service(workspace_id)` called at line 739 (step 3); `ensure_workspace_service` called at line 742 (step 4). |
| 7 | Cloud Map service has FailureThreshold: 1 health check for auto-deregistration of crashed tasks | VERIFIED | `HealthCheckCustomConfig={"FailureThreshold": 1}` at line 392 inside `create_cloudmap_service`. |
| 8 | Bootstrap response confirms Cloud Map service creation | VERIFIED | `"cloudmapServiceId": cloudmap_service_id` in bootstrap return dict at line 796. |
| 9 | Idempotent: calling bootstrap twice does not error if Cloud Map service already exists | VERIFIED | `create_cloudmap_service` paginates `list_services` with `NAMESPACE_ID` filter (lines 369-380); returns existing `svc["Id"]` if name matches, skips `create_service`. Exception in list call is caught and logged as warning (not raised). |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `controller-python/main.py` | Single-container workspace task definition, TG port fixed to 3001 | VERIFIED | File exists, passes Python `ast.parse` syntax check. Single `container_defs` entry. `LANDING_PAGE_PORT` used in TG creation and registration. |
| `controller-python/main.py` | `create_cloudmap_service` function, `CLOUDMAP_NAMESPACE_ID` from infra, `sd` boto3 client | VERIFIED | `sd = boto3.client("servicediscovery", ...)` at line 144. `CLOUDMAP_NAMESPACE_ID = INFRA.get("cloudmap_namespace_id", "")` at line 39. `create_cloudmap_service` function at lines 359-401. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `register_workspace_task_definition` | `ecs.register_task_definition` | `container_defs` list with single landing-page entry | WIRED | `container_defs` (line 269) has one entry with `name: landing-page`; passed to `ecs.register_task_definition` at line 295. |
| `ensure_workspace_target_group` | `LANDING_PAGE_PORT` | `Port=` argument | WIRED | `Port=LANDING_PAGE_PORT` confirmed at line 541. |
| `bootstrap_workspace` | `create_cloudmap_service` | called after register_workspace_task_definition, before ensure_workspace_service | WIRED | Step 2 (line 736) = `register_workspace_task_definition`; step 3 (line 739) = `create_cloudmap_service`; step 4 (line 742) = `ensure_workspace_service`. Ordering is correct. |
| `create_cloudmap_service` | `sd.create_service` | boto3 servicediscovery client | WIRED | `sd.create_service(...)` at line 385. `sd` client initialized at line 144. |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INFRA-01 | 01-01 | Workspace task definition contains only `landing-page` container | SATISFIED | Single-entry `container_defs` in `register_workspace_task_definition` (lines 269-290). |
| INFRA-02 | 01-01 | emptyDir shared volume removed from workspace task definition | SATISFIED | `volumes = []` at line 292; passed to `register_task_definition`. |
| INFRA-03 | 01-01 | Envoy task definition registration removed from controller bootstrap flow | SATISFIED | No `ENVOY_PORT`, `ENVOY_ADMIN_PORT`, or `_ENVOY` constants remain. No Envoy container in task def. Bootstrap flow has no Envoy task def registration call. (Remaining `register_app_route`/`deregister_app_route` are Envoy-named route-management stubs deferred to Phase 2 CTRL-01 — they are not task definition registrations.) |
| CMAP-01 | 01-02 | Controller creates a Cloud Map service (`{workspaceId}-apps`) per workspace at bootstrap time | SATISFIED | `create_cloudmap_service(workspace_id)` in bootstrap step 3 (line 739); creates service named `cloudmap_service_name(workspace_id)` = `{workspaceId}-apps` (line 365, helper at line 178). |
| CMAP-04 | 01-02 | Cloud Map health check configured (`FailureThreshold: 1`) to auto-deregister crashed tasks | SATISFIED | `HealthCheckCustomConfig={"FailureThreshold": 1}` at line 392. |
| CTRL-04 | 01-02 | Bootstrap flow creates Cloud Map service before launching workspace service | SATISFIED | Step 3 (cloudmap, line 739) precedes step 4 (ECS service, line 742). |

**Orphaned requirements check:** REQUIREMENTS.md maps INFRA-01, INFRA-02, INFRA-03, CMAP-01, CMAP-04, CTRL-04 to Phase 1. All six appear in plan frontmatter and are accounted for. No orphaned requirements.

---

## Anti-Patterns Found

| File | Line(s) | Pattern | Severity | Impact |
|------|---------|---------|----------|--------|
| `controller-python/main.py` | 510 | Section comment: "Target group + ALB (1 per workspace, points to Envoy)" | Info | Stale comment — TG now points to landing-page port 3001, not Envoy. No functional impact. |
| `controller-python/main.py` | 656-687 | Section "Envoy route management via landing page internal API"; `register_app_route` docstring "Tell the landing page to add an Envoy route"; `deregister_app_route` docstring with Envoy references | Warning | These functions and their Envoy references are Phase 2 removals (CTRL-01). Functions are still called in app start/stop flows (lines 779, 909, 931). Not blocking Phase 1 goal — Phase 2 will replace them with Cloud Map register/deregister calls. |
| `controller-python/main.py` | 759, 807, 854, 897, 923 | Comments/docstrings referencing "Envoy route" in bootstrap, `/workspace/{id}/apps`, app start, app stop handlers | Warning | Stale documentation for in-progress flows. All deferred to Phase 2 (CTRL-01, CTRL-02, CTRL-03). No functional impact on Phase 1 goal. |

No blocker anti-patterns. All Envoy references remaining are in route-management code explicitly deferred to Phase 2.

---

## Human Verification Required

None. All Phase 1 must-haves are verifiable statically from the source code. The Cloud Map service creation will be validated live during Phase 2 integration testing.

---

## Gaps Summary

No gaps. All 6 requirement IDs (INFRA-01, INFRA-02, INFRA-03, CMAP-01, CMAP-04, CTRL-04) are satisfied by verifiable code in `controller-python/main.py`. Phase 1 goal is achieved.

---

_Verified: 2026-03-31_
_Verifier: Claude (gsd-verifier)_
