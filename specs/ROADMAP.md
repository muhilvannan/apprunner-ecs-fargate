# ECS App Tester — Roadmap

## Milestones

- ✅ **v0.1 Alpha** — Phases 01–02 (shipped 2026-03-30)
- ◆ **v0.2 Experiment** — Phases 03–05 (Option C: Cloud Map + Node.js proxy)

---

## Phases

<details>
<summary>✅ v0.1 Alpha (Phases 01–02) — SHIPPED 2026-03-30</summary>

- [x] Phase 01: Foundation — Terraform base infra (2/2 plans) — completed 2026-03-29
- [x] Phase 02: Controller API — workspace & app management (3/3 plans) — completed 2026-03-30

Full details: [milestones/v0.1-ROADMAP.md](milestones/v0.1-ROADMAP.md)

</details>

---

### Phase 03: Infra Swap — Drop Envoy, Wire Cloud Map

**Goal:** Remove Envoy from the workspace service task; create Cloud Map service infrastructure at bootstrap time. After this phase, workspace tasks run with a single `landing-page` container, and Cloud Map is ready to receive app registrations.

**Branch:** `task-level-app-experiments`

**Requirements:** INFRA-01, INFRA-02, INFRA-03, CMAP-01, CMAP-04, CTRL-04

**Plans:**
- [ ] Plan 03-A: Update workspace task definition (remove Envoy container + emptyDir volume)
- [ ] Plan 03-B: Add Cloud Map service creation to controller bootstrap (`create_service`, `HealthCheckCustomConfig`)

**Success Criteria:**
1. `POST /workspace/bootstrap` completes with workspace service task running a single `landing-page` container
2. Cloud Map console shows `{workspaceId}-apps` service in `workspace-discovery.local` namespace after bootstrap
3. No Envoy container in ECS task definition; no emptyDir volume reference
4. Existing ALB → TG → landing-page routing unchanged

---

### Phase 04: App Routing via Cloud Map + Node.js Proxy

**Goal:** Controller registers/deregisters app tasks in Cloud Map on start/stop. Landing page resolves app IPs via Cloud Map API and proxies requests via `http-proxy-middleware`. Envoy config management code fully removed.

**Branch:** `task-level-app-experiments`

**Requirements:** CMAP-02, CMAP-03, LP-01, LP-02, LP-03, LP-04, LP-05, LP-06, CTRL-01, CTRL-02, CTRL-03

**Plans:**
- [ ] Plan 04-A: Controller — Cloud Map register/deregister on app start/stop (replaces Envoy route add/remove)
- [ ] Plan 04-B: Landing page — http-proxy-middleware + Cloud Map SDK lookup (replaces Envoy config management)

**Success Criteria:**
1. `POST /app/start` registers app instance in Cloud Map; app accessible via `/{workspaceId}/{appId}/` through landing page proxy
2. `POST /app/stop` deregisters app instance; accessing app URL returns 503 immediately
3. `GET /internal/routes` returns live app list from Cloud Map (not in-memory Envoy table)
4. No Envoy config files, no SIGHUP calls, no `/internal/routes/add` or `/remove` endpoints remain in landing page server.js
5. If app task crashes, Cloud Map health check removes instance within ≤30s; subsequent requests return 503

---

### Phase 05: Docs & Standards

**Goal:** Update ADR-002 with unified 3-option comparison; update CLAUDE.md with cheap-infra standards and Option C architecture. Project documentation reflects the current experiment branch state.

**Branch:** `task-level-app-experiments`

**Requirements:** DOC-01, DOC-02, DOC-03

**Plans:**
- [ ] Plan 05-A: Update ADR-002 with 3-option comparison table + recommendation
- [ ] Plan 05-B: Update CLAUDE.md — Option C architecture, cheap-infra standards

**Success Criteria:**
1. ADR-002 contains a single unified comparison table with Option A, B, and C columns
2. CLAUDE.md architecture section reflects Option C (no Envoy, Cloud Map routing)
3. CLAUDE.md contains explicit cheap-infra standard: single NAT GW, no HA for experiment stack
4. `specs/PROJECT.md` and `specs/STATE.md` updated to reflect completed experiment

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|---------------|--------|-----------|
| 01: Foundation | v0.1 | 2/2 | ✅ Complete | 2026-03-29 |
| 02: Controller API | v0.1 | 3/3 | ✅ Complete | 2026-03-30 |
| 03: Infra Swap | v0.2 | 0/2 | ○ Pending | — |
| 04: App Routing | v0.2 | 0/2 | ○ Pending | — |
| 05: Docs & Standards | v0.2 | 0/2 | ○ Pending | — |
