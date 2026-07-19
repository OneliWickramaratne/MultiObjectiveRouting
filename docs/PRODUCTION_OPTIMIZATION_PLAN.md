# Production Optimization Plan

Last reviewed: 2026-07-13

## Phase 0: Current Baseline

- Backend compile: passing.
- Frontend build: passing.
- Backend unit tests: 5 passing.
- Known performance warning: large 3D navigation bundle.
- Known production blockers: real auth, migrations, concurrency locks, production deployment hardening.

## Phase 1: Safety and Security

1. Replace development identity with real auth.
2. Add bearer/cookie token validation to every protected endpoint.
3. Move SSE authentication off query parameters.
4. Add rate limiting for login and critical write endpoints.
5. Add security headers and production CORS allowlist.
6. Add structured logging with correlation IDs and PHI redaction.
7. Add authorization regression tests for every admin and ambulance endpoint.

## Phase 2: Database Integrity

1. Add Alembic. **Implemented with a baseline migration and guarded legacy bootstrap.**
2. Add foreign-key indexes. **Baseline indexes implemented; migration ownership remains.**
3. Add unique constraints for bed number per hospital and active patient per bed. **Implemented for new schemas and local development.**
4. Add status check constraints or enum tables.
5. Add UTC timestamp policy.
6. Implement concurrency-safe bed reservation. **Implemented with conditional atomic claims.**
7. Implement atomic ambulance assignment. **Implemented with ranked conditional claims.**
8. Add idempotency keys for transfer create, accept, reject, and dispatch.

The claim workflow uses short compare-and-set updates that work in SQLite development and PostgreSQL. PostgreSQL migrations can later adopt `FOR UPDATE SKIP LOCKED` when dispatch is moved to parallel worker queues.

## Phase 3: Domain Refactor

1. Split `admin.py` into hospitals, beds, transfers, ambulances, analytics, events.
2. Move serialization to dedicated mapper modules.
3. Move transfer creation/accept/reject into service methods.
4. Keep HTTP routes thin.
5. Add service-layer unit tests before and after extraction.

## Phase 4: Routing and Dispatch

1. Define a `RoutingProvider` interface for OSM, Google, and fallback.
2. Add route timeouts and bounded retry.
3. Add unreachable-route handling and degraded-mode warnings.
4. Persist route source, generated time, and freshness.
5. Add dispatcher override with reason.
6. Add ambulance capability fields before scoring equipment-sensitive missions.

## Phase 5: ML/MLOps

1. Add model registry file.
2. Add model cards for urgency, traffic, capacity forecast, dispatch scoring.
3. Store model version in every prediction response.
4. Add deterministic baseline comparison.
5. Add validation metrics and training-data provenance.
6. Add latency/failure counters.
7. Add drift monitoring once live outcome data exists.

## Phase 6: Frontend UX and Performance

1. Split `App.tsx` by role and command tab.
2. Keep 3D navigation lazy-loaded only for driver mode.
3. Add timestamps/source labels to capacity, traffic, routes, forecasts, and simulation.
4. Add accessible focus management for unignorable notifications.
5. Add double-submit protection on transfer creation and accept/reject.
6. Add reconnect state for SSE.
7. Run keyboard and screen-reader review.

## Phase 7: DevOps

1. Add production Dockerfiles with non-root users.
2. Replace hardcoded Compose DB credentials with environment variables.
3. Add healthchecks.
4. Add migration command to deployment flow.
5. Add backup/restore runbook.
6. Add rollback checklist.
7. Add CI for backend tests, frontend build, dependency audit, and Docker build.

## Measurement Targets

- `GET /api/admin/dashboard`: p95 under 300 ms for 9 hospitals and 18 ambulances.
- Transfer accept with dispatch: p95 under 2.5 s with warm OSM graph.
- Route calculation fallback: deterministic and labelled within 5 s timeout.
- Frontend initial route: under 500 kB gzip excluding lazy 3D navigation.
- SSE reconnect: within 5 s after network recovery.
