# Project State

## Project Reference

See: specs/PROJECT.md (updated 2026-03-30)

**Core value:** Per-app task isolation with Cloud Map-backed routing — drop Envoy, single landing-page container per workspace
**Current focus:** Phase 1 — Infra Swap (drop Envoy, wire Cloud Map)
**Branch:** task-level-app-experiments

## Current Phase

**Phase 1: Infra Swap — Drop Envoy, Wire Cloud Map**

Status: In progress
Current Plan: 1/2 complete

## Phase History

| Phase | Status | Completed |
|-------|--------|-----------|
| 01: Foundation (v0.1) | ✅ Complete | 2026-03-29 |
| 02: Controller API (v0.1) | ✅ Complete | 2026-03-30 |
| 03: Infra Swap (v0.2) | ○ Pending | — |
| 04: App Routing (v0.2) | ○ Pending | — |
| 05: Docs & Standards (v0.2) | ○ Pending | — |

## Decisions

- Removed Envoy sidecar entirely — Option C uses Node.js http-proxy-middleware in landing page instead (01-01)
- ALB TG now points to LANDING_PAGE_PORT (3001) directly; no Envoy port intermediary (01-01)
- volumes=[] passed explicitly to register_task_definition for clarity (01-01)

## Next Action

Execute plan 01-02: Cloud Map wiring

---
*Initialized: 2026-03-30*
*Last session: 2026-03-30 — Completed 01-01-PLAN.md*
