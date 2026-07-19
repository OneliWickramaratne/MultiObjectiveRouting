# Architecture Audit

Last reviewed: 2026-07-13

## Critical Findings

### C1. Development identity was previously allowed to become super admin (fixed)

- Affected files: `backend/app/auth.py`, `backend/app/main.py`, `.env.example`
- Current behavior after fix: `X-User-Id` is ignored; protected endpoints require a signed access token tied to an active, revocable database session.
- Previous fragile behavior: requests without identity defaulted to `super-admin`.
- Real-world consequence: total account bypass and unrestricted access to patient, bed, ambulance, and transfer administration.
- Implemented solution: Argon2 credentials, short-lived JWT access tokens, hashed rotating refresh secrets, CSRF protection, account lockout, revocation, and one-use SSE tickets.
- Remaining rollout requirement: integrate the approved health identity provider and MFA, then complete penetration and authorization testing.
- Regression tests: claimed-header rejection, valid/revoked sessions, one-use event tickets, role scope, and end-to-end login/refresh/logout checks.

### C2. Bed reservation is not concurrency-safe

- Affected files: `backend/app/api/routes/admin.py`, `backend/app/models.py`
- Current behavior: `reserve_transfer_bed()` selects first available bed and updates it in the same request transaction.
- Why fragile: SQLite has limited concurrency; no row lock, compare-and-set update, unique active reservation constraint, or idempotency key.
- Real-world consequence: two receiving admins could reserve the same bed under load.
- Proposed solution: use PostgreSQL transactions with `SELECT ... FOR UPDATE SKIP LOCKED`, add transfer reservation uniqueness, and add idempotency keys.
- Migration risk: requires Alembic migration and service-level tests.
- Required tests: two concurrent accept requests for one available bed.

### C3. Ambulance assignment is not concurrency-safe

- Affected files: `backend/app/services/dispatch_service.py`, `backend/app/api/routes/admin.py`
- Current behavior: available ambulances are queried and the chosen row is updated to `assigned`.
- Why fragile: no lock or atomic status compare.
- Real-world consequence: two transfers can assign the same ambulance.
- Proposed solution: PostgreSQL row locks or atomic `UPDATE ... WHERE status='available' RETURNING`, plus idempotency and dispatcher override reasons.
- Migration risk: requires database-specific implementation and tests.
- Required tests: two dispatchers assigning one ambulance.

### C4. Production database migrations are missing

- Affected files: `backend/app/database.py`, `backend/app/seed_db.py`, `docker-compose.yml`
- Current behavior: app initializes tables directly for local development.
- Why fragile: no controlled schema history, rollback, data migration, or constraint rollout.
- Real-world consequence: production upgrades risk data loss or inconsistent schema.
- Proposed solution: add Alembic migrations and separate seed data from schema creation.
- Migration risk: initial migration must match existing SQLite/Postgres schema.
- Required tests: migration up/down on empty and seeded database.

## High Findings

### H1. Patient data is stored broadly and lacks retention/encryption policy

- Affected files: `backend/app/models.py`, `backend/app/api/routes/admin.py`, docs.
- Current behavior: transfer and patient records store identifiers, names, contact details, vitals, diagnosis, medications, allergies, and notes.
- Why fragile: no field-level encryption, retention controls, consent workflow, or legal compliance boundary.
- Real-world consequence: PHI exposure if database or backups leak.
- Implemented improvement: audit and event details now redact sensitive keys by default.
- Proposed solution: data minimization review, encrypted fields or encrypted database storage, backup encryption, retention/deletion policy.
- Required tests: sensitive-data logging prevention.

### H2. Server-Sent Events are authenticated by query identity

- Affected files: `backend/app/api/routes/admin.py`, `frontend/src/App.tsx`
- Current behavior: `/api/admin/events/stream?user_id=...` looks up the user from a query parameter.
- Why fragile: identity is forgeable in production.
- Real-world consequence: cross-hospital event exposure.
- Proposed solution: authenticate SSE with bearer/cookie session and authorize each emitted event.
- Required tests: unauthorized SSE connection and cross-hospital filtering.

### H3. Oversized backend and frontend modules

- Affected files: `backend/app/api/routes/admin.py`, `frontend/src/App.tsx`
- Current behavior: admin HTTP handling, serialization, audit, lifecycle helpers, and state transitions share one file; frontend combines most role dashboards and map state in one component.
- Why fragile: high merge risk, difficult testing, accidental regression.
- Proposed solution: split into domain routers/services and React feature modules.
- Required tests: service-layer tests before extraction.

### H4. ML governance is incomplete

- Affected files: `backend/app/services/traffic_model_service.py`, `ml/`, `_incoming_hos_zip/`
- Current behavior: joblib models are loaded when found; fallback formula is used otherwise.
- Why fragile: no model registry, model card, version compatibility, calibration report, drift monitoring, or training reproducibility contract.
- Real-world consequence: unsafe confidence in stale or unvalidated predictions.
- Proposed solution: model registry, validation metrics, deterministic baseline comparison, monitoring, and clear prediction labels.

### H5. Docker Compose contains development credentials

- Affected files: `docker-compose.yml`
- Current behavior: Postgres user/password are hardcoded development values.
- Why fragile: accidental production reuse.
- Real-world consequence: database compromise.
- Proposed solution: use env-file placeholders, secret injection, non-public DB ports in production.

## Medium Findings

- M1. CORS is configurable now, but production origin allowlist still needs deployment-specific setup.
- M2. Health endpoints do not yet validate database/model/routing dependency readiness.
- M3. API lacks version prefix such as `/api/v1`.
- M4. Pagination is missing on dashboards, transfer events, users, ambulances, and bed lists.
- M5. Route calculations can be CPU-heavy and still run inside API workers.
- M6. Frontend production bundle has a large 3D map chunk.
- M7. Structured logging and correlation IDs are missing.
- M8. Simulation is correctly read-only, but should show generated-at and data-source freshness everywhere.

## Low Findings

- L1. Several endpoint examples still use old IDs such as `nhsl` while seeded IDs are numeric strings.
- L2. Some status strings are free-form rather than database constrained enums.
- L3. No formal accessibility audit has been run.

## Implemented In This Pass

- Added `backend/app/config.py`.
- Removed implicit super-admin default authentication.
- Added production startup guards against dev auth and SQLite.
- Added `/ready`.
- Added `backend/app/services/transfer_state_machine.py`.
- Added `backend/app/services/sensitive_data.py`.
- Redacted audit/event details by default.
- Added first-party backend unit tests for auth, redaction, and state transitions.

## Next Priorities

1. Add Alembic and database constraints.
2. Implement concurrency-safe bed and ambulance locking.
3. Replace development identity with real auth.
4. Split admin route/service modules.
5. Add integration and concurrency tests.
