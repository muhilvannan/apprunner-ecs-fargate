---
phase: 02-app-routing-via-cloud-map-nodejs-proxy
type: context
created: 2026-03-31
source: codebase analysis (ADR-002, Phase 1 plans, server.js, main.py) + user direction
---

# Phase 2 Context — App Routing via Cloud Map + Node.js Proxy

## What Phase 1 Left Behind (Pre-conditions for Phase 2)

Phase 1 completed:
- Workspace task def: single `landing-page` container only (no Envoy)
- Cloud Map service `{workspaceId}-apps` created at bootstrap (`create_cloudmap_service`)
- `sd` boto3 client, `CLOUDMAP_NAMESPACE_ID`, `cloudmap_service_name` helper all exist in `main.py`
- Bootstrap returns `cloudmapServiceId`

What still uses Envoy logic (Phase 2 must replace/remove):
- `controller-python/main.py`: `register_app_route` / `deregister_app_route` (Envoy /internal/routes/add|remove HTTP calls)
- `controller-python/main.py`: `list_workspace_apps` cross-references Envoy route state via `GET /internal/routes`
- `controller-python/main.py`: `start_app` calls `register_app_route` after task IP obtained
- `controller-python/main.py`: `stop_app` calls `deregister_app_route` before stop_task
- `ui-nodejs/workspace-landing/server.js`: entire Envoy config management layer (buildEnvoyConfig, writeEnvoyConfig, reloadEnvoy, ENVOY_CONFIG, ENVOY_ADMIN_PORT, /internal/routes/add, /internal/routes/remove, in-memory `routes` table)

---

## Decisions (LOCKED — implement exactly)

### D-01: Controller Cloud Map registration on app start/stop

**app/start flow:**
```
run_task → wait_for_task_ip → sd.register_instance(ServiceId, InstanceId=app_task_arn, Attributes={AWS_INSTANCE_IPV4, AWS_INSTANCE_PORT})
```
No HTTP call to landing page. No `register_app_route`. Direct boto3 call.

**app/stop flow:**
```
sd.deregister_instance(ServiceId, InstanceId=app_task_arn) → stop_task
```
Order matters: deregister first (prevents traffic), then stop task.

CloudMap service ID lookup: use `cloudmap_service_name(workspace_id)` to find existing service via `list_services` paginator (same pattern as `create_cloudmap_service`'s idempotency check). Extract `svc["Id"]` — add a `get_cloudmap_service_id(workspace_id) -> str` helper.

### D-02: Remove CTRL-01 — Envoy route management functions from controller

Remove from `controller-python/main.py`:
- `register_app_route` function (lines ~665-675)
- `deregister_app_route` function (lines ~677-686)
- All call sites in `bootstrap_workspace`, `start_app`, `stop_app`
- Section header comment `# Envoy route management via landing page internal API`
- `httpx` import (used only for Envoy route calls — verify no other uses before removing)

### D-03: list_workspace_apps uses Cloud Map DiscoverInstances

Replace Envoy route table cross-reference with Cloud Map `DiscoverInstances`:
```python
sd.discover_instances(
    NamespaceName="workspace-discovery.local",
    ServiceName=cloudmap_service_name(workspace_id),
    MaxResults=100,
    QueryParameters={},
    HealthStatus="HEALTHY",
)
```
App is "running" if its `InstanceId` (= app_task_arn or appId) is returned by DiscoverInstances. No ECS task family listing required if Cloud Map is authoritative source. Keep ECS task family list for `appId` enumeration; use Cloud Map health for status.

Instance ID convention: use `app_task_arn` as InstanceId (already unique per task run).

**Note:** `DiscoverInstances` returns instances with `InstanceId` and `Attributes` (AWS_INSTANCE_IPV4, AWS_INSTANCE_PORT). Map by appId tag or derive from InstanceId.

Tag approach: when registering, include `{"app_id": app_id}` in Attributes so DiscoverInstances result maps cleanly to appId without ARN parsing.

### D-04: Landing page — remove all Envoy code (LP-06)

Remove from `ui-nodejs/workspace-landing/server.js`:
- `ENVOY_ADMIN_PORT` constant
- `ENVOY_CONFIG` constant
- `buildEnvoyConfig()` function (entire YAML template)
- `writeEnvoyConfig()` function
- `reloadEnvoy()` function
- `writeEnvoyConfig()` call at startup
- `POST /internal/routes/add` handler
- `POST /internal/routes/remove` handler
- `const routes = {}` in-memory table
- `execSync` require (used only by reloadEnvoy)
- `fs` require (used only by writeEnvoyConfig + serveHub) — keep for serveHub HTML read
- `child_process` require — remove entirely

### D-05: Landing page — http-proxy-middleware + Cloud Map SDK (LP-01, LP-02)

Add to `package.json`:
- `http-proxy-middleware` (^3.x)
- `@aws-sdk/client-servicediscovery`

Landing page proxies `ANY /workspace{id}/{appId}/*` via Cloud Map lookup:
```js
app.use(`${BASE_PATH}/:appId`, async (req, res, next) => {
  const instance = await resolveCloudMap(WORKSPACE_ID, req.params.appId);
  if (!instance) return res.status(503).json({ error: 'App not running' });
  createProxyMiddleware({
    target: `http://${instance.ip}:${instance.port}`,
    changeOrigin: true,
    pathRewrite: { [`^${BASE_PATH}/${req.params.appId}`]: '' },
  })(req, res, next);
});
```

### D-06: Landing page — Cloud Map lookup via DiscoverInstances API (not DNS) (LP-02)

Use `@aws-sdk/client-servicediscovery` `DiscoverInstancesCommand`:
```js
const { ServiceDiscoveryClient, DiscoverInstancesCommand } = require('@aws-sdk/client-servicediscovery');
const sdClient = new ServiceDiscoveryClient({ region: process.env.AWS_DEFAULT_REGION || 'eu-west-1' });

async function resolveCloudMap(workspaceId, appId) {
  const resp = await sdClient.send(new DiscoverInstancesCommand({
    NamespaceName: 'workspace-discovery.local',
    ServiceName: `${workspaceId}-apps`,
    MaxResults: 100,
    HealthStatus: 'HEALTHY',
  }));
  const instance = resp.Instances.find(i => i.Attributes.app_id === appId);
  if (!instance) return null;
  return { ip: instance.Attributes.AWS_INSTANCE_IPV4, port: parseInt(instance.Attributes.AWS_INSTANCE_PORT) };
}
```

### D-07: Cloud Map lookup cache ≤5s TTL in landing page (LP-03)

Cache the full DiscoverInstances result (not per-appId) with a timestamp. On each proxy request, check if cache age > 5s; if stale, re-query. Simple module-level object:
```js
let cloudMapCache = { instances: [], fetchedAt: 0 };
const CACHE_TTL_MS = 5000;
```
Resolve from cache first; fetch if stale.

### D-08: GET /internal/routes returns live Cloud Map state (LP-05)

Replace in-memory `routes` response with live Cloud Map DiscoverInstances query:
```js
app.get('/internal/routes', async (req, res) => {
  const instances = await fetchCloudMapInstances(WORKSPACE_ID);
  const routes = {};
  for (const inst of instances) {
    const appId = inst.Attributes.app_id;
    if (appId) routes[appId] = { appIP: inst.Attributes.AWS_INSTANCE_IPV4, port: parseInt(inst.Attributes.AWS_INSTANCE_PORT) };
  }
  res.json({ routes, workspaceId: WORKSPACE_ID });
});
```
This makes `/internal/routes` authoritative from Cloud Map, not from ephemeral process memory.

### D-09: Landing page IAM — servicediscovery:DiscoverInstances permission

The landing-page task role needs `servicediscovery:DiscoverInstances` added to its IAM policy.
This is in Terraform (`terraform/iam.tf`) — add to the workspace task role inline policy.

### D-10: App task ARN as Cloud Map InstanceId convention

Use the full app task ARN as `InstanceId` when calling `register_instance`. Rationale: unique per task run, enables deregistration by ARN without state storage. Include `app_id` in Attributes for Cloud Map-side filtering.

---

## Claude's Discretion

- **Cache invalidation strategy**: Simple TTL is sufficient. No need to actively invalidate cache on register/deregister events (TTL ≤5s is acceptable lag).
- **Error handling in proxy**: If `resolveCloudMap` throws (AWS API error), return 503 with error message — don't crash the server.
- **`get_cloudmap_service_id` helper**: Can paginate or can store cloudmap_service_id in the bootstrap response and look it up from ECS tags. Pagination approach (same as `create_cloudmap_service`) is cleanest.
- **httpx removal**: Verify `httpx` is only used for Envoy route calls before removing the import. If any other use remains (e.g., health check), keep the import.
- **`list_workspace_apps` simplification**: Can simplify by using Cloud Map as sole source of truth for running apps (skip ECS task family enumeration if Cloud Map already has all registered instances). Decide based on what's cleaner.
- **Package.json description**: Update `description` field to reflect new role (remove "Envoy config API").

---

## Deferred (Out of Scope for Phase 2)

- Circuit breaking, retries, timeouts — Envoy L7 features not needed
- Landing page UI changes (iframe embeds, status cards) — not in Phase 2 requirements
- Controller refactor into separate modules (DX-01) — v2 deferred
- Input validation on workspace_id/app_id (DX-02) — v2 deferred
- CloudWatch log viewer in landing page (OBS-01) — v2 deferred
- Per-app ECS service for ECS console visibility — out of scope

---

## Phase 2 Requirements to Cover

| ID | Component | What |
|----|-----------|------|
| CMAP-02 | controller | register_instance on app start |
| CMAP-03 | controller | deregister_instance on app stop |
| LP-01 | landing page | http-proxy-middleware proxy handler |
| LP-02 | landing page | DiscoverInstances API lookup (not DNS) |
| LP-03 | landing page | ≤5s TTL cache for Cloud Map lookups |
| LP-04 | landing page | 503 when app not in Cloud Map |
| LP-05 | landing page | GET /internal/routes from Cloud Map |
| LP-06 | landing page | Remove all Envoy config management code |
| CTRL-01 | controller | Remove register_app_route / deregister_app_route |
| CTRL-02 | controller | app start: run_task → wait_for_task_ip → register_instance |
| CTRL-03 | controller | app stop: deregister_instance → stop_task |
