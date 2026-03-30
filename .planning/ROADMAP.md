# ECS App Tester — Roadmap (Option C Experiment)

## Milestone: v0.2 Experiment

**Goal:** Replace Envoy with Cloud Map + Node.js proxy in the experiment branch. 3 phases, 6 plans total.

## Phases

### Phase 1: Infra Swap — Drop Envoy, Wire Cloud Map

**Goal:** Remove Envoy from workspace task; create Cloud Map service at bootstrap.

**Requirements:** INFRA-01, INFRA-02, INFRA-03, CMAP-01, CMAP-04, CTRL-04

**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md — Strip Envoy from workspace task definition, fix TG port to LANDING_PAGE_PORT
- [ ] 01-02-PLAN.md — Add Cloud Map service creation to controller bootstrap

**Success Criteria:**
1. Workspace bootstrap runs single-container task (landing-page only)
2. Cloud Map `{workspaceId}-apps` service created in `workspace-discovery.local` after bootstrap
3. No Envoy container or emptyDir in task definition

---

### Phase 2: App Routing via Cloud Map + Node.js Proxy

**Goal:** Controller registers/deregisters apps in Cloud Map. Landing page proxies via http-proxy-middleware.

**Requirements:** CMAP-02, CMAP-03, LP-01–LP-06, CTRL-01–CTRL-03

**Plans:**
- [ ] Plan 2-A: Controller — Cloud Map register/deregister on app start/stop
- [ ] Plan 2-B: Landing page — http-proxy-middleware + Cloud Map SDK lookup

**Success Criteria:**
1. App start registers in Cloud Map; app accessible through landing page proxy
2. App stop deregisters; URL returns 503
3. No Envoy config code remains anywhere

---

### Phase 3: Docs & Standards

**Goal:** ADR-002 3-option table, CLAUDE.md cheap-infra standards.

**Requirements:** DOC-01, DOC-02, DOC-03

**Plans:**
- [ ] Plan 3-A: Update ADR-002 with 3-option comparison table
- [ ] Plan 3-B: Update CLAUDE.md — Option C architecture + cheap-infra standards

**Success Criteria:**
1. ADR-002 has unified 3-option comparison table
2. CLAUDE.md reflects Option C architecture
3. Cheap-infra standard documented: single NAT GW, no HA for experiment stack

---

## Requirement → Phase Mapping

| Requirement | Phase |
|-------------|-------|
| INFRA-01, INFRA-02, INFRA-03 | Phase 1 |
| CMAP-01, CMAP-04, CTRL-04 | Phase 1 |
| CMAP-02, CMAP-03 | Phase 2 |
| LP-01 → LP-06 | Phase 2 |
| CTRL-01, CTRL-02, CTRL-03 | Phase 2 |
| DOC-01, DOC-02, DOC-03 | Phase 3 |
