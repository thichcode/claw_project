# WorldMonitor Hybrid Production Roadmap

## Goal

Move `worldmonitor-hybrid` from a compelling demo into a production-capable monitoring platform.

---

## Phase 0 — Immediate Hardening

### Objectives
- remove unsafe demo defaults from runtime-critical paths
- prevent demo behavior from leaking into production
- improve operator trust during failures

### Tasks
- require explicit demo credentials via environment variables
- enforce demo-mode checks on simulation/reset endpoints
- stop silently falling back to mock data in production mode
- require explicit JWT secret in non-demo environments
- begin removing plaintext password assumptions

### Exit Criteria
- no hardcoded runtime credentials in web/API code
- demo-only endpoints blocked outside demo mode
- production UI shows failure/degraded state instead of fake data

---

## Phase 1 — Production Baseline

### Objectives
- improve maintainability and governance
- establish a secure application core

### Tasks
- split backend into route/service/auth modules
- add password hashing + migration strategy
- implement RBAC for sensitive actions
- add audit logging for incident and admin actions
- add baseline automated tests

### Exit Criteria
- auth flow is secure enough for internal use
- key workflows are covered by tests
- sensitive endpoints enforce role checks

---

## Phase 2 — Observability Foundation

### Objectives
- make the monitoring platform observable itself
- enable safe operation and troubleshooting

### Tasks
- add structured application logging
- expose metrics endpoints
- add tracing/request correlation
- deploy Prometheus + Grafana + logs/traces stack
- create alerts for API, DB, ingest, and auth failures

### Exit Criteria
- operators can detect and diagnose platform issues quickly
- dashboards exist for product health and ingest health

---

## Phase 3 — Complete NOC Workflows

### Objectives
- support real operator usage, not just demo flows

### Tasks
- improve incident lifecycle UX
- add advanced filtering, search, ownership, suppression, dedup
- add runbooks/remediation guidance
- add escalations and on-call integrations

### Exit Criteria
- an operator can manage alerts/incidents end-to-end without workarounds

---

## Phase 4 — Scale and Platformization

### Objectives
- evolve from MVP into a scalable monitoring platform

### Tasks
- move ingest/correlation to async workers or queues
- use Redis or queueing intentionally
- add multi-team or multi-tenant support
- add SSO/OIDC and enterprise config management
- add retention, archival, and export strategies

### Exit Criteria
- platform can support broader internal adoption and larger workloads

---

## Recommended Implementation Order

1. Phase 0 hardening
2. Auth + RBAC + backend modularization
3. Observability stack
4. Workflow completeness
5. Scaling and enterprise features