# Security Threat Model

Last reviewed: 2026-07-13

## Assets

- Patient demographics and clinical handover data.
- ICU bed availability and patient assignment.
- Ambulance locations, crew identity, and active missions.
- Transfer decisions, route recommendations, and audit logs.
- Traffic/routing data and model artifacts.
- Database credentials and external routing API keys.

## Trust Boundaries

- Browser to FastAPI API.
- FastAPI to database.
- FastAPI to local model/routing artifacts.
- FastAPI to optional Google Routes API.
- FastAPI background simulation thread to database.
- Hospital admins to scoped hospital data.
- Ambulance crews to assigned mission data.
- Super admin to network-wide operations.

## Primary Threats

| Threat | Risk | Current State | Required Control |
|---|---:|---|---|
| Missing authentication | Critical | Argon2 credentials, signed access tokens, revocable sessions implemented | Integrate approved IdP and MFA before hospital rollout |
| Privilege escalation | Critical | Database-backed identity and scoped role checks implemented | Expand endpoint authorization tests and independent review |
| Insecure direct-object reference | High | Scope checks exist on many endpoints | Exhaustive endpoint tests |
| Patient data leakage in logs | High | Audit/event details now redacted | Structured logger redaction and regression tests |
| Forged SSE user id | High | Fixed with short-lived one-use event tickets | Monitor ticket failures and expire stale rows |
| Race condition on bed/ambulance | Critical | Not yet fixed | Postgres row locks, idempotency keys |
| SQL injection | Medium | SQLAlchemy ORM used | Avoid raw SQL, validate inputs |
| XSS | Medium | React escapes text by default | Avoid unsafe HTML; CSP headers |
| CSRF | Medium | Refresh cookie uses SameSite plus double-submit CSRF validation | Validate reverse-proxy cookie/TLS behavior in staging |
| SSRF | Medium | Optional external routing API controlled by backend config | Do not accept arbitrary route URLs |
| Secret leakage | High | `.env.example` contains no real secrets; Compose has dev password | Secret manager/env injection |
| Denial of service | Medium | Route/model work can be CPU-heavy | Rate limits, worker queues, timeouts |
| Dependency vulnerabilities | Medium | Pinned Python packages; no scanner configured | pip-audit/npm audit in CI |
| Container misconfiguration | Medium | Compose is local-dev only | non-root images, hidden DB ports, healthchecks |

## Implemented Controls

- Missing identity no longer defaults to `super-admin`.
- Legacy `X-User-Id` impersonation is rejected.
- Passwords use Argon2; access JWTs are short-lived and tied to revocable database sessions.
- Refresh secrets are hashed, rotated on use, and protected by HttpOnly/SameSite cookies and CSRF tokens.
- Reuse of an invalidated refresh secret revokes its session.
- Login failures trigger account lockout.
- SSE identity uses a short-lived one-use ticket.
- Production startup fails if dev default auth is enabled.
- Production startup fails when SQLite is configured.
- Audit/event detail payloads are recursively redacted for sensitive key names.
- Transfer state transitions are centrally validated.

## Required Production Controls Not Yet Implemented

- MFA-ready architecture for privileged roles.
- Approved enterprise or national health identity-provider integration.
- Network-level login rate limiting in addition to account lockout.
- Correlation IDs and structured security logs.
- Security headers and production CORS allowlist.
- Encrypted backups and retention policy.
- Alembic migrations with constraints and locking.
- Dependency scanning in CI.
- Threat-model review after real live integrations are added.

## Audit Logging Rules

Audit events should record:

- actor user id
- actor role when available
- action
- resource type and id
- timestamp
- previous/new operational state where appropriate
- override reason where applicable

Audit events must not store:

- patient name
- patient identifier
- date of birth
- vitals
- diagnosis
- medications
- contact details
- access tokens
- secrets

The redaction helper is a safety net. Callers should still avoid passing PHI into audit details.
