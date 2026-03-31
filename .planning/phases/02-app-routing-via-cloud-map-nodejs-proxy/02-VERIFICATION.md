---
phase: 02-app-routing-via-cloud-map-nodejs-proxy
verified: 2026-03-31T11:30:00Z
status: passed
score: 13/13 must-haves verified
re_verification: false
---

# Phase 02: App Routing via Cloud Map + Node.js Proxy Verification Report

**Phase Goal:** Controller registers/deregisters apps in Cloud Map. Landing page proxies via http-proxy-middleware.
**Verified:** 2026-03-31T11:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | POST /app/start calls sd.register_instance with app task ARN as InstanceId and app_id in Attributes | VERIFIED | `main.py:882-890` — `sd.register_instance(ServiceId=service_id, InstanceId=app_task_arn, Attributes={..., "app_id": app_id})` |
| 2  | POST /app/stop calls sd.deregister_instance before stop_task (deregister-first order) | VERIFIED | `main.py:912-927` — deregister_instance at line 917, stop_app_task at line 927 |
| 3  | register_app_route and deregister_app_route functions are deleted from main.py | VERIFIED | grep returns 0 matches for either function name |
| 4  | get_landing_page_ip is deleted (no longer needed) | VERIFIED | grep returns 0 matches |
| 5  | httpx import is removed (no other usages remain) | VERIFIED | grep returns 0 matches for httpx in main.py |
| 6  | bootstrap_workspace no longer calls register_app_route or references workspace_ip for routing | VERIFIED | grep returns 0 matches for workspace_ip, register_app_route, routeRegistered |
| 7  | list_workspace_apps uses Cloud Map DiscoverInstances, not httpx GET to landing page | VERIFIED | `main.py:784` — `sd.discover_instances(NamespaceName="workspace-discovery.local", HealthStatus="HEALTHY")` |
| 8  | GET /workspace{id}/{appId}/any-path proxies to the app task IP resolved from Cloud Map | VERIFIED | `server.js:58-88` — proxy middleware on `${BASE_PATH}/:appId`, calls resolveCloudMap, forwards to `http://${resolved.ip}:${resolved.port}` |
| 9  | GET /internal/routes returns live Cloud Map instance list, not an in-memory table | VERIFIED | `server.js:93-112` — calls DiscoverInstancesCommand directly, returns apps array |
| 10 | When no Cloud Map instance exists for an app, the proxy returns 503 | VERIFIED | `server.js:66-67` — `if (!resolved) return res.status(503).json(...)` |
| 11 | Cloud Map lookups are cached for up to 5 seconds (CACHE_TTL_MS = 5000) | VERIFIED | `server.js:26` — `const CACHE_TTL_MS = 5000`, cache checked at line 33 |
| 12 | No Envoy code remains in server.js | VERIFIED | grep for buildEnvoyConfig, writeEnvoyConfig, reloadEnvoy, ENVOY_CONFIG, ENVOY_ADMIN_PORT, child_process, execSync, routes/add, routes/remove returns 0 matches |
| 13 | The workspace task IAM role has servicediscovery:DiscoverInstances in terraform/iam.tf | VERIFIED | `iam.tf:77-91` — `aws_iam_role_policy.ecs_workspace_task_cloudmap` with Action `servicediscovery:DiscoverInstances` attached to `ecs_workspace_task_role` |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `controller-python/main.py` | Cloud Map register/deregister on app start/stop, cleaned-up route helpers | VERIFIED | Exists, substantive (925+ lines), `get_cloudmap_service_id` at line 402, `register_instance` at line 882, `deregister_instance` at line 917, `discover_instances` at line 784 |
| `ui-nodejs/workspace-landing/server.js` | Cloud Map proxy + live /internal/routes endpoint | VERIFIED | Exists (151 lines), contains DiscoverInstancesCommand, createProxyMiddleware, resolveCloudMap, /internal/routes handler — no Envoy remnants |
| `ui-nodejs/workspace-landing/package.json` | http-proxy-middleware and @aws-sdk/client-servicediscovery dependencies | VERIFIED | Both dependencies present: `http-proxy-middleware: ^3.0.3`, `@aws-sdk/client-servicediscovery: ^3.0.0`; package-lock.json generated with 97 packages |
| `terraform/iam.tf` | servicediscovery:DiscoverInstances permission on workspace task role | VERIFIED | `aws_iam_role_policy.ecs_workspace_task_cloudmap` resource present at line 77; terraform validate passes |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `start_app in main.py` | `sd.register_instance` | `get_cloudmap_service_id(workspace_id)` | WIRED | `main.py:875` calls `get_cloudmap_service_id`, result used as `ServiceId` in `sd.register_instance` at line 882 |
| `stop_app in main.py` | `sd.deregister_instance then stop_app_task` | `get_cloudmap_service_id(workspace_id)` | WIRED | `main.py:915` calls `get_cloudmap_service_id`, `sd.deregister_instance` at line 917, `stop_app_task` at line 927 — correct deregister-first order |
| `proxy route in server.js` | `resolveCloudMap(workspaceId, appId)` | http-proxy-middleware router option | WIRED | `server.js:65` — `const resolved = await resolveCloudMap(WORKSPACE_ID, appId)` inside proxy middleware handler; result used to construct `target` |
| `resolveCloudMap` | `DiscoverInstancesCommand` | `@aws-sdk/client-servicediscovery` | WIRED | `server.js:36-41` — `sdClient.send(new DiscoverInstancesCommand({...}))` inside resolveCloudMap |
| `terraform/iam.tf ecs_workspace_task_role` | `servicediscovery:DiscoverInstances` | inline policy | WIRED | `iam.tf:79` — `role = aws_iam_role.ecs_workspace_task_role.id` on the inline policy resource |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CMAP-02 | 02-01 | Controller registers app task IP + port in Cloud Map on app start | SATISFIED | `main.py:882-890` — register_instance with AWS_INSTANCE_IPV4, AWS_INSTANCE_PORT, app_id |
| CMAP-03 | 02-01 | Controller deregisters app instance from Cloud Map on app stop | SATISFIED | `main.py:917` — deregister_instance before stop_app_task |
| CTRL-01 | 02-01 | Remove register_app_route and remove_app_route controller functions | SATISFIED | Both functions absent; grep returns 0 matches |
| CTRL-02 | 02-01 | App start flow: run_task → wait_for_task_ip → register_instance | SATISFIED | `main.py:861-890` — run_app_task → wait_for_task_ip → sd.register_instance |
| CTRL-03 | 02-01 | App stop flow: deregister_instance → stop_task | SATISFIED | `main.py:912-927` — deregister_instance at 917, stop_app_task at 927 |
| LP-01 | 02-02 | Landing page proxies GET/POST /workspace{id}/{appId}/* via http-proxy-middleware | SATISFIED | `server.js:58-88` — app.use(`${BASE_PATH}/:appId`) with createProxyMiddleware |
| LP-02 | 02-02 | Landing page resolves app IP + port via Cloud Map DiscoverInstances API | SATISFIED | `server.js:36-41` — DiscoverInstancesCommand used in resolveCloudMap |
| LP-03 | 02-02 | Landing page caches Cloud Map lookups with TTL ≤5s | SATISFIED | `server.js:26,33` — CACHE_TTL_MS=5000, cache keyed by workspaceId |
| LP-04 | 02-02 | Landing page returns 503 when app instance not found in Cloud Map | SATISFIED | `server.js:66-68` — res.status(503).json({error: 'App not available'...}) on null resolve |
| LP-05 | 02-02 | GET /internal/routes queries Cloud Map API, returns live app list | SATISFIED | `server.js:93-112` — calls DiscoverInstancesCommand directly, returns instances array |
| LP-06 | 02-02 | Remove all Envoy config management code from landing page | SATISFIED | server.js is a complete rewrite; no Envoy identifiers present (confirmed by grep) |

**Requirements declared in plans but outside Phase 2 scope (informational):**

CTRL-04 (Phase 1 — bootstrap creates Cloud Map service) was not claimed by any Phase 2 plan — correctly absent. Phase 2 plans claim exactly CMAP-02, CMAP-03, CTRL-01, CTRL-02, CTRL-03, LP-01 through LP-06. All 11 IDs accounted for and SATISFIED.

---

### Anti-Patterns Found

None. No TODO/FIXME/PLACEHOLDER comments, no empty implementations, no stub handlers found in any modified file.

---

### Human Verification Required

Two items need a live AWS environment to fully confirm:

**1. Cloud Map DiscoverInstances IAM permission**

- Test: Deploy `terraform apply`, bootstrap a workspace, start an app, call `GET /internal/routes` from the running landing-page container.
- Expected: Response contains the registered app's IP and port; no IAM authorization errors in CloudWatch logs.
- Why human: IAM policy is correct in HCL but requires a live deployment to confirm the permission propagates to the task execution environment.

**2. pathRewrite strips prefix correctly for all app types**

- Test: Start a Streamlit or React app, navigate to `https://builder.muhilvannan.com/workspace{id}/{appId}/some/page`.
- Expected: Upstream app receives `/some/page`, not `/workspace{id}/{appId}/some/page`; page renders without 404.
- Why human: pathRewrite logic involves dynamic string interpolation (`^${BASE_PATH}/${appId}`) that is correct in static analysis but path-stripping behaviour for edge cases (trailing slash, query params) requires live traffic.

---

### Deviations from Plan (informational, not gaps)

- **Port resolution in start_app:** The plan specified `_, port, _ = _app_config(app_type)` to get the port. The implementation instead reads the port from the registered task definition's container portMappings (`td["containerDefinitions"][0]["portMappings"][0]["containerPort"]`). This is functionally equivalent — the same port value — and arguably more correct since it reads the authoritative registered port rather than recomputing it. Not a gap.

- **list_workspace_apps uses `sd.discover_instances` directly** (not through `get_cloudmap_service_id`): documented as an intentional decision in SUMMARY (discover_instances accepts namespace+service name, not service ID). Consistent with plan intent.

---

## Summary

Phase 02 goal is fully achieved. The controller exclusively uses Cloud Map for app registration/deregistration with no Envoy coupling. The landing page proxies all app traffic via `http-proxy-middleware` backed by live Cloud Map DiscoverInstances lookups, with a 5-second TTL cache, pathRewrite prefix stripping, and 503 on cache miss. The workspace task IAM role has the required DiscoverInstances permission. All 11 requirement IDs claimed by Phase 2 plans are satisfied. Syntax validation passes for all three modified subsystems (Python, Node.js, Terraform HCL).

---

_Verified: 2026-03-31T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
