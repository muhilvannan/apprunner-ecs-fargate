# ADR-002: Workspace Architecture — Multi-Container Task vs Per-App Service

**Status:** Two approaches documented — see below
**Date:** 2026-03-30

---

## Original Decision (main branch — PRODUCTION)

**Status:** Accepted — DO NOT CHANGE on main without explicit user instruction

### Hard AWS Constraint — Read This First

**Tasks launched via `run_task` (standalone tasks) NEVER appear under a service in the ECS console.**

They appear only at the cluster "Tasks" level. The ECS console only lists a task under a service
if the **service scheduler** launched it (i.e. the service has `desiredCount > 0` and ECS placed
the task itself). This is a platform constraint with no workaround.

**Consequence:** The only way to have apps visible under a workspace service in the console is to
have the service scheduler manage the task. This means one service, one task, all apps as
containers in that task.

### Decision

**1 ECS Service per workspace (desiredCount=1, always running)**
**1 multi-container task per workspace (one container per app)**
**Start/Stop = ALB listener rule toggle only (forward ↔ fixed-response 503)**
**Containers are never stopped — only traffic is toggled**

```
ECS Service: {workspaceId}   desiredCount=1
  └── Task: {workspaceId}-task   (launched by service scheduler — visible in console)
        ├── Container: app1      port 8501
        ├── Container: app2      port 8000
        └── Container: appN      port XXXX

ALB:
  /workspace{id}/app1*  →  forward (running) | fixed-response 503 (stopped)
  /workspace{id}/app2*  →  forward (running) | fixed-response 503 (stopped)
```

### Anti-Pattern to Avoid (main)

**Never use `run_task` to launch app tasks.** Tasks started this way always appear outside
the service in the ECS console.

---

## Experimental Approach (branch: task-level-app-experiments)

**Status:** Under experiment — intentionally overrides the constraint above
**Domain:** `builder.muhilvannan.com` | **Cluster:** `ecs-app-tester-exp-dev`

### Decision

**1 ECS Service per workspace (desiredCount=1) — contains landing page + Envoy proxy only**
**1 standalone `run_task` per app — independent lifecycle, isolated IAM role**
**Start/Stop = Envoy route add/remove + task run/stop**
**ALB has 1 rule per workspace → Envoy; Envoy routes internally to app tasks**

```
ECS Service: {workspaceId}   desiredCount=1
  └── Task: {workspaceId}-task   (landing page + envoy — service-managed)
        ├── Container: landing-page   port 3001  (workspace hub UI + Envoy config API)
        └── Container: envoy          port 8080  (L7 proxy, shared emptyDir config)

Standalone App Tasks (run_task — NOT service-managed):
  ├── Task: {workspaceId}-{appId}   IAM role: {workspaceId}-app-role
  └── Task: {workspaceId}-{appId2}  IAM role: {workspaceId}-app-role

ALB:
  /workspace{id}/*  →  TG: {workspaceId}-tg  →  Envoy :8080

Envoy routes (dynamic, hot-reloaded via Admin API):
  /workspace{id}/app1/*  →  {app1TaskIP}:8501
  /workspace{id}/app2/*  →  {app2TaskIP}:8000
  /workspace{id}         →  127.0.0.1:3001  (landing page)
```

### IAM Segregation

Each workspace gets a dedicated IAM task role for its app tasks:

```
{workspaceId}-app-role:
  - ecs:DescribeTasks, ecs:DescribeTaskDefinition (read own cluster only)
  - DENY ecs:StopTask, ecs:RunTask (no lateral movement)
  - No S3, no EFS (deferred to future phase)
```

Workspace A's app tasks cannot assume Workspace B's role, stop Workspace B's tasks, or access
Workspace B's resources. Enforced at AWS IAM level.

### Why Experiment

This branch answers:
1. Can Envoy hot-reload (Admin API + SIGHUP) reliably serve as the routing control plane?
2. Does per-app task isolation (crash containment, independent CPU/memory) justify the cost?
3. Does the landing page hub UX (iframe embeds + status display) improve workspace experience?
4. What is the real-world bootstrap latency penalty of N sequential `run_task` + IP waits?

---

## Comparison

| Concern | main (multi-container) | experiment (per-app run_task + Envoy) |
|---|---|---|
| **App crash isolation** | No — one crash can destabilize sibling containers | Yes — each task is independent |
| **Per-app CPU/memory** | No — shared task resources | Yes — set per task definition |
| **ECS console visibility** | Workspace as 1 service (all apps grouped) | Apps as standalone tasks (not under service) |
| **Start/stop mechanism** | ALB rule toggle (instant, no task restart) | Envoy route toggle + task run/stop |
| **Start latency** | ~0s (container always running) | ~90s (task cold start on first start) |
| **Bootstrap latency** | ~2 min (1 task wait) | ~2–5 min (N task waits, sequential) |
| **ALB rules** | N rules per workspace (1 per app) | 1 rule per workspace |
| **ENIs** | 1 per workspace | 1 (workspace service) + N (app tasks) |
| **Fargate cost** | 1 task always running | 1 workspace task + N app tasks |
| **Routing complexity** | ALB path rules (AWS-managed) | Envoy config (self-managed) |
| **Workspace IAM** | Shared task role | Per-workspace role, app-scoped |
| **Landing page / hub UI** | None | Yes — iframe embeds, status, metadata |
| **L7 features** | None (ALB basic path routing) | Full Envoy: retries, timeouts, circuit breaking |

### Pros of Experiment

- Independent app lifecycle — restart/stop one without touching others
- Independent resource allocation per app
- App crash is fully isolated
- Envoy enables advanced L7 routing (headers, retries, traffic shaping)
- Landing page is a richer workspace UX than raw ALB routing
- Simpler per-app task definitions (single container)
- Strong per-workspace IAM boundary at AWS level

### Cons of Experiment

- `run_task` tasks not visible under workspace service in ECS console
- Higher Fargate cost (N active tasks vs 1)
- More ENIs → more subnet IP consumption
- Slower bootstrap (N sequential task waits)
- Envoy config management adds operational surface area
- Landing page must implement Envoy config rewrite + hot-reload logic
- More AWS resources per workspace (IAM role, task per app)

---

## Option C: Cloud Map + Landing Page Proxy (Research — Not Yet Implemented)

**Status:** Under research — candidate to replace Envoy in experiment branch
**Motivation:** Reduce operational complexity of Envoy config management + hot-reload

### Why ADR-001's "CloudMap Not Used" Reasoning No Longer Applies

[ADR-001](001-cloudmap-not-used.md) rejected Cloud Map because ALB target groups are a separate
system — Cloud Map DNS does not propagate to ALB `register_targets`. That is still true.

However, the experiment branch changes the routing topology. In the experiment, there is already
an intermediate proxy (Envoy) sitting between the ALB and app tasks. Traffic never goes directly
from ALB to an app task IP. This means:

- The ALB rule only needs to know about the **workspace service** (one static target)
- App task IPs are resolved **inside the cluster** by the proxy
- Cloud Map is designed exactly for internal IP resolution — this is the right use case

### Architecture

```
Browser
  │
  ▼
ALB  /workspace{id}/*  ──►  TG: {workspaceId}-tg  ──►  Landing Page :3001
                                                              │
                                    ┌─────────────────────────┤
                                    │  /workspace{id}         │──► serves index.html (workspace hub)
                                    │  /workspace{id}/{appId} │──► proxy → Cloud Map resolve → appIP:port
                                    └─────────────────────────┘

Cloud Map namespace: workspace-discovery.local
  ├── {workspaceId}-app1  A  10.0.10.x  port 8501  (auto-deregisters on task stop)
  └── {workspaceId}-app2  A  10.0.11.x  port 8000

Workspace Task (service-managed, 1 container — NO Envoy):
  └── Container: landing-page  :3001
        ├── GET /workspace{id}           → serves index.html
        ├── ANY /workspace{id}/{appId}/* → http-proxy-middleware → Cloud Map lookup → forward
        └── GET /internal/routes         → query Cloud Map API → return live app list

App Tasks (run_task — unchanged):
  ├── Task: {workspaceId}-{appId}   IAM role: {workspaceId}-app-role
  └── Task: {workspaceId}-{appId2}  IAM role: {workspaceId}-app-role
```

### How Cloud Map Registration Works With `run_task`

ECS Service Discovery auto-registration only applies to ECS **services**. For `run_task`,
registration must be done manually by the controller via the SDK:

```python
# After wait_for_task_ip(app_task_arn):
servicediscovery.register_instance(
    ServiceId=cloudmap_service_id,          # pre-created per app type, or per workspace
    InstanceId=app_task_arn,
    Attributes={
        "AWS_INSTANCE_IPV4": task_ip,
        "AWS_INSTANCE_PORT": str(app_port),
    }
)

# On app stop:
servicediscovery.deregister_instance(ServiceId=..., InstanceId=app_task_arn)
```

Cloud Map also supports health checks that auto-deregister unhealthy instances — providing
a safety net if a task crashes without the controller calling `deregister_instance`.

### Landing Page as Node.js Proxy

Replace `http-proxy-middleware` for routing instead of Envoy:

```js
// server.js
const { createProxyMiddleware } = require('http-proxy-middleware');
const { ServiceDiscovery } = require('@aws-sdk/client-servicediscovery');

// On request: /workspace{id}/{appId}/{rest}
app.use('/workspace:wsId/:appId', async (req, res, next) => {
  const instance = await resolveCloudMap(req.params.wsId, req.params.appId);
  if (!instance) return res.status(503).json({ error: 'App not running' });

  createProxyMiddleware({
    target: `http://${instance.ip}:${instance.port}`,
    changeOrigin: true,
    pathRewrite: { [`^/workspace${req.params.wsId}/${req.params.appId}`]: '' },
  })(req, res, next);
});
```

No config file. No SIGHUP. No shared volume. Route state lives in Cloud Map (AWS-managed).

### What Changes vs Current Envoy Experiment

| Component | Envoy experiment | Cloud Map + proxy |
|---|---|---|
| Workspace task containers | 2 (landing-page + envoy) | **1 (landing-page only)** |
| emptyDir shared volume | Required (envoy.yaml) | **Removed** |
| Route update mechanism | Rewrite envoy.yaml + SIGHUP | **Cloud Map register/deregister** |
| Controller calls on app start | `run_task` + `POST /internal/routes/add` | `run_task` + `register_instance` |
| Controller calls on app stop | `POST /internal/routes/remove` + `stop_task` | `deregister_instance` + `stop_task` |
| Auto-recovery on task crash | No (stale Envoy route) | **Yes (Cloud Map health check)** |
| L7 features (retries, circuit breaking) | Yes (Envoy full feature set) | No (basic Node.js proxy) |
| Fargate cost | 2 containers per workspace | **1 container per workspace** |
| `terraform/cloudmap.tf` changes | Namespace only | **Add `aws_service_discovery_service` per workspace** |

### Terraform Changes Required

The `workspace-discovery.local` namespace is already provisioned in `cloudmap.tf`. Additional
resources needed at workspace bootstrap time (created dynamically by controller, not Terraform):

```python
# Controller creates a Cloud Map service per workspace at bootstrap:
servicediscovery.create_service(
    Name=f"{workspace_id}-apps",
    NamespaceId=cloudmap_namespace_id,
    DnsConfig={
        "DnsRecords": [{"Type": "A", "TTL": 10}]  # Low TTL for fast updates
    },
    HealthCheckCustomConfig={"FailureThreshold": 1}
)
```

No new Terraform resources needed beyond what already exists.

### Pros

- **50% fewer containers per workspace task** — single landing-page container vs landing-page + Envoy
- **No Envoy config management** — no envoy.yaml, no config templates, no hot-reload
- **No SIGHUP / Admin API calls** — route changes are Cloud Map API calls (same as current `register_targets`)
- **Auto-deregistration on task crash** — Cloud Map health checks remove unhealthy instances automatically
- **Simpler landing page code** — http-proxy-middleware vs Envoy config rewrite logic
- **AWS-native state** — routing state visible in Cloud Map console, not inside a container
- **Lower Fargate cost** — 1 task unit vs 2 per workspace service

### Cons

- **DNS TTL lag** — even at TTL=10s, DNS-based resolution has a brief stale window after app stop
  (mitigated by querying Cloud Map API directly instead of DNS — returns live state immediately)
- **Node.js proxy limitations** — no built-in circuit breaking or retries vs Envoy's full L7 feature set
  (acceptable for experiment scope — these features are not required)
- **Still manual registration** — `run_task` doesn't auto-register in Cloud Map; controller must call
  `register_instance` (same operational surface as the current Envoy route-add call)
- **SDK dependency** — landing page must include `@aws-sdk/client-servicediscovery` and have IAM
  permission to call `servicediscovery:DiscoverInstances` (minor — already needs AWS access)
- **Cloud Map API latency** — `DiscoverInstances` adds ~10–50 ms per proxy request vs in-memory route table
  (mitigated with a short TTL in-memory cache in the landing page, invalidated on each register/deregister)

---

## Recommendation

**For the experiment branch: replace Envoy with Cloud Map + landing page proxy.**

Rationale:

1. The primary complexity driver is Envoy — config templating, hot-reload, Admin API, emptyDir volume,
   and the `/internal/routes/add|remove` API layer. Removing Envoy removes all of this.
2. The landing page is a core requirement regardless. Making it the proxy adds ~20 lines of
   Node.js (`http-proxy-middleware`) vs the full Envoy config management layer it currently implements.
3. Cloud Map is already provisioned (`terraform/cloudmap.tf`). The namespace `workspace-discovery.local`
   exists in the experiment stack. Cost is negligible ($1/million queries).
4. The L7 features Envoy provides (retries, circuit breaking) are not required for this experiment.
5. Auto-deregistration on crash is a safety property the Envoy approach lacks.

The Envoy approach remains valid if L7 features become a hard requirement in a future phase.

---

## Future: Per-App Service (If Console Visibility Required)

If both independent task lifecycle AND ECS console visibility are needed, the correct model is
**1 service per app** named `{workspaceId}-{appId}` (desiredCount=1). That gives each app its
own service-managed task visible in the console. This changes workspace = 1 service to
workspace = N services and requires an explicit decision.

---

_See also: [ADR-001](001-cloudmap-not-used.md) — CloudMap not used (original multi-container model)_
