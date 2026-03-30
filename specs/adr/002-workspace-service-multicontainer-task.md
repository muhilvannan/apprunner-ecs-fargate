# ADR-002: 1 Service per Workspace, Multi-Container Task, ALB Toggle for Start/Stop

**Status:** Accepted — DO NOT CHANGE without explicit user instruction
**Date:** 2026-03-30

## Hard AWS Constraint — Read This First

**Tasks launched via `run_task` (standalone tasks) NEVER appear under a service in the ECS console.**

They appear only at the cluster "Tasks" level. The ECS console only lists a task under a service
if the **service scheduler** launched it (i.e. the service has `desiredCount > 0` and ECS placed
the task itself). This is a platform constraint with no workaround.

**Consequence:** The only way to have apps visible under a workspace service in the console is to
have the service scheduler manage the task. This means one service, one task, all apps as
containers in that task.

## Decision

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

## Why Not "1 Task Per App"

This was attempted and caused tasks to appear outside the service (at cluster level only).
The `run_task` API does not associate tasks with a service regardless of tags or grouping parameters.
An ECS service only shows tasks it scheduled itself.

## Why Not "1 Service Per App"

The requirement is workspace = 1 service. Multiple services per workspace breaks this mapping.

## Why Multi-Container Is Correct Here

- All containers in a task share the same ENI (private IP), different ports
- Each app gets its own ALB listener rule and its own target group
- The service scheduler ensures the task (and all containers) stays running
- Start/stop is purely an ALB concern — no ECS API calls needed

## Naming

```python
workspace_service_name(workspace_id)      → workspace_id          # e.g. "ws-001"
workspace_task_family(workspace_id)       → f"{workspace_id}-task" # e.g. "ws-001-task"
app_tg_name(workspace_id, app_id)         → f"{workspace_id}-{app_id}-tg"[:32]
```

## Start / Stop

```
Start: elbv2.modify_rule → forward action (traffic flows to container)
Stop:  elbv2.modify_rule → fixed-response 503 (traffic blocked, container still running)
```

No `ecs.run_task`, no `ecs.stop_task` — task lifecycle is managed entirely by the service.

## Future: Per-App Task (If Needed)

If independent task lifecycle per app is required in a future phase, the correct model is
**1 service per app** (named `{workspaceId}-{appId}`), not `run_task`. That gives each app
its own service-managed task visible in the console. This would change workspace = 1 service
to workspace = N services, which requires an explicit decision.

## Anti-Pattern to Avoid

**Never use `run_task` to launch app tasks.** Tasks started this way always appear outside
the service in the ECS console. This mistake has been made multiple times — do not repeat it.
