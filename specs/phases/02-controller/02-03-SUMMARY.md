# Phase 02-03 Execution Summary (Retrospective)

**Status:** ✅ COMPLETE (absorbed Phases 03 and 04 from original roadmap)
**Wave:** 3 (App Lifecycle + ALB Routing)
**Plan intent:** Start/stop app tasks, file sync from S3 to EFS

## What Was Actually Built

App start/stop is implemented as **ALB listener rule toggling** — not task lifecycle management.
The task always runs (`desiredCount=1`). Starting an app switches the listener rule action from
`fixed-response 503` to `forward` (to the app's target group). Stopping switches it back.

This also absorbed Phases 03 (Integration/Routing) and 04 (Testing/Verification) from the original roadmap,
as ALB path routing was implemented directly in the controller rather than as a separate integration phase.

### App Start/Stop

`POST /app/start` and `POST /app/stop` both call `set_app_rule_enabled(workspace_id, app_id, enabled)`:

1. `get_https_listener_arn()` — find ALB HTTPS listener (port 443)
2. `find_listener_rule(listener_arn, workspace_id, app_id)` — match rule by path pattern `/workspace{id}/{appId}*`
3. `elbv2.modify_rule(RuleArn=..., Actions=[action])` — switch action

```python
# Enabled (running):
{"Type": "forward", "TargetGroupArn": tg_arn}

# Disabled (stopped):
{"Type": "fixed-response", "FixedResponseConfig": {
    "StatusCode": "503", "ContentType": "text/plain", "MessageBody": "App is stopped"
}}
```

Container keeps running throughout. No ECS API calls for start/stop.

### App Sync

`PUT /app/sync` — S3 listing only (no EFS mounting):
- Lists objects in `s3://{bucket}/{prefix}` via paginator
- Returns object count
- EFS integration (actual file transfer to `/mnt/efs`) is known tech debt

### Streamlit Base URL Path Fix

Streamlit serves static assets relative to its base URL. Without configuration, static assets are
requested at `/workspace{id}/static/...` (wrong) instead of `/workspace{id}/{appId}/static/...`.

Fix: `--server.baseUrlPath=/workspace{workspaceId}/{appId}` injected at startup:

```python
command = ["sh", "-c",
    f"pip install --quiet streamlit && "
    f"python -m streamlit hello "
    f"--server.port=8501 --server.headless=true --server.address=0.0.0.0 "
    f"--server.baseUrlPath={base_path}"]
```

`_app_config(app_type, workspace_id, app_id)` accepts workspace and app IDs and builds the command
dynamically for Streamlit; other app types ignore these parameters.

### ALB Routing (absorbed from Phase 03)

Path pattern rules created during bootstrap:
- Pattern: `/workspace{id}/{appId}*`
- Priority: first available in range 100–399
- Default state: `fixed-response 503` (disabled)

HTTPS listener on port 443 is the target. HTTP-only setups return no listener and skip rule creation
with a warning.

### End-to-End Verification (absorbed from Phase 04)

Tested live at `https://brewer.muhilvannan.com`:
- Bootstrap workspace with 2 apps → ECS console shows 1 service, 1 task, 2 containers
- `/app/start` → ALB returns 200 (after ~90s container cold start for pip install)
- `/app/stop` → ALB returns 503 "App is stopped"; other app unaffected
- Streamlit assets load correctly at `/workspace{id}/{appId}/static/...`

## Issues Resolved

- **502 Bad Gateway**: Streamlit serving assets at wrong path → fixed with `--server.baseUrlPath`
- **"App is stopped" on start**: Container still installing pip packages (~90s) → not a bug, health check becomes healthy after startup
- **`InvalidParameterException: Invalid namespace for group`**: `run_task` group param validation → removed group param; later found `run_task` tasks never appear under a service (architectural constraint, resolved by switching to service scheduler)

## Known Tech Debt

- **No EFS mounting**: App containers do not mount EFS; `/app/sync` only lists S3 objects
- **No formal test suite**: Verification was manual (live testing against AWS)
- **Cold start ~90s**: All app types install packages at runtime on every task start
- **Streamlit uses `hello` demo**: Not user-supplied code; code loading from S3/EFS is not yet wired
