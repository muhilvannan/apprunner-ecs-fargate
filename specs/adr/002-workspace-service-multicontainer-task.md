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

## Future: Per-App Service (If Console Visibility Required)

If both independent task lifecycle AND ECS console visibility are needed, the correct model is
**1 service per app** named `{workspaceId}-{appId}` (desiredCount=1). That gives each app its
own service-managed task visible in the console. This changes workspace = 1 service to
workspace = N services and requires an explicit decision.

---

_See also: [ADR-001](001-cloudmap-not-used.md) — CloudMap not used_
