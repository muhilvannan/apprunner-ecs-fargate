# Phase 02-02 Execution Summary (Retrospective)

**Status:** ✅ COMPLETE (major architectural pivot from plan)
**Wave:** 2 (Workspace Bootstrap)
**Plan intent:** Create ECS service per workspace, CloudMap registration, S3 bucket access

## What Was Actually Built

`POST /workspace/bootstrap` — registers a multi-container task definition, creates one ECS service per workspace at `desiredCount=1`, creates one ALB target group and one disabled listener rule per app, waits for the task to be RUNNING, then manually registers the task's private IP to all target groups.

### Architectural Pivot: Multi-Container Task

The original plan had one task per app. The actual architecture uses **one task with multiple containers** (one container per app). This was driven by the requirement that apps appear under a service in the ECS console — standalone `run_task` tasks never appear under a service.

```
ECS Service: {workspaceId}  (desiredCount=1)
  └── Task: {workspaceId}-task
        ├── Container: app1  (streamlit, port 8501)
        ├── Container: app2  (fastapi, port 8000)
        └── Container: appN  (...)
```

All containers in the same task share the same ENI (private IP). Each app gets its own port.

### Bootstrap Flow

1. **S3 IAM policy** — if `s3Bucket` provided, `iam.put_role_policy` on the workspace task role
2. **Task definition** — `register_task_definition`: family=`{workspaceId}-task`, one container def per app, awsvpc networking, FARGATE, cpu=512, memory=1024, CloudWatch logging per container
3. **ECS service** — `ensure_workspace_service`: creates service named `{workspaceId}` at `desiredCount=1`; handles DRAINING/INACTIVE by force-delete + recreate
4. **Target groups** — `ensure_target_group`: HTTP TG per app, `Matcher={"HttpCode":"200-499"}`
5. **Listener rules** — `ensure_listener_rule`: path `/workspace{id}/{appId}*`, created as `fixed-response 503` (disabled) by default
6. **Wait + register** — `wait_for_task_running` polls until service starts task; `wait_for_task_ip` polls ENI; `register_task_to_tgs` calls `elbv2.register_targets` with `{ip}:{port}` for each app

### Why No `loadBalancers` on Service

ECS service `loadBalancers` config only supports registering ONE container/port to ONE target group.
With N apps there are N TGs. Solution: create service without `loadBalancers`, then register IPs manually
after the task is RUNNING.

### Key Functions

| Function | Purpose |
|----------|---------|
| `register_workspace_task_definition` | Multi-container task def, one cdef per app |
| `ensure_workspace_service` | Create/update service; handle DRAINING state |
| `ensure_target_group` | Idempotent TG creation |
| `ensure_listener_rule` | Idempotent rule creation at priority 100–399 |
| `wait_for_task_running` | Polls `list_tasks(serviceName=...)` |
| `wait_for_task_ip` | Polls ENI `privateIPv4Address` from task attachment |
| `register_task_to_tgs` | Registers `{ip}:{port}` to each app's TG |

### App Types Supported

| Type | Image | Port | Startup |
|------|-------|------|---------|
| `streamlit` | `public.ecr.aws/docker/library/python:3.12-slim` | 8501 | `pip install streamlit && python -m streamlit hello --server.baseUrlPath=...` |
| `fastapi` | same | 8000 | `pip install fastapi uvicorn && uvicorn inline` |
| `dash` | same | 8050 | `pip install dash && app.run(...)` |
| `jupyter` | same | 8888 | `pip install jupyterlab && jupyter lab ...` |
| `custom` | same | 8080 | `time.sleep(86400)` placeholder |

All images from `public.ecr.aws` — no Docker Hub auth required on Fargate.

## Issues Resolved During Implementation

- **`ServiceNotActiveException`**: `update_service` on DRAINING service → detect status, force-delete, recreate
- **`TCP` health check protocol**: ALB TGs only support HTTP/HTTPS → fixed: `HealthCheckProtocol="HTTP"`
- **`ws-ws-` double prefix**: naming function was prepending `ws-` on top of user-passed `ws-{id}` → removed prefix, service name = workspace ID directly
- **VPC not found**: stale `infrastructure-outputs.json` after `terraform destroy` → re-run `terraform apply && terraform output`
