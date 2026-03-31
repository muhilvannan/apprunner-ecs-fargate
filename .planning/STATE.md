# Project State

## Project Reference

See: specs/PROJECT.md (updated 2026-03-30)

**Core value:** Per-app task isolation with Cloud Map-backed routing — drop Envoy, single landing-page container per workspace
**Current focus:** Phase 2 — App Routing (Cloud Map proxy + Node.js landing page)
**Branch:** task-level-app-experiments

## Current Phase

**Phase 2: App Routing via Cloud Map + Node.js Proxy**

Status: Complete
Current Plan: 2/2 complete

## Phase History

| Phase | Status | Completed |
|-------|--------|-----------|
| 01: Foundation (v0.1) | ✅ Complete | 2026-03-29 |
| 02: Controller API (v0.1) | ✅ Complete | 2026-03-30 |
| 03: Infra Swap (v0.2) | ✅ Complete | 2026-03-31 |
| 04: App Routing (v0.2) | ✅ Complete | 2026-03-31 |
| 05: Docs & Standards (v0.2) | ○ Pending | — |

## Decisions

- Removed Envoy sidecar entirely — Option C uses Node.js http-proxy-middleware in landing page instead (01-01)
- ALB TG now points to LANDING_PAGE_PORT (3001) directly; no Envoy port intermediary (01-01)
- volumes=[] passed explicitly to register_task_definition for clarity (01-01)
- FailureThreshold: 1 for Cloud Map health check — fastest auto-deregistration on task crash (01-02)
- Idempotent Cloud Map service creation: list_services paginator check before create_service (01-02)
- Bootstrap step ordering: Cloud Map service created as step 3, before ECS service launch (01-02)
- pathRewrite strips /workspace{id}/{appId} prefix before forwarding — matches prior Envoy prefix_rewrite: '/' behaviour (02-02)
- Cloud Map cache keyed by workspaceId not appId — one cache entry per workspace covers all apps (02-02)
- IAM DiscoverInstances on Resource: '*' — Cloud Map does not support resource-level restrictions (02-02)

## Next Action

Phase 02 complete. All Cloud Map proxy and landing page routing is implemented. Next: tf-apply for IAM changes, then re-bootstrap workspaces for end-to-end testing.

---
*Initialized: 2026-03-30*
*Last session: 2026-03-31 — Completed 02-02-PLAN.md*
