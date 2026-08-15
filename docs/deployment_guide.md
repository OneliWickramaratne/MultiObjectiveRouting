# Deployment Guide

Last reviewed: 2026-07-13

## Development

Use:

```powershell
.\START_APP.cmd
```

Development defaults:

- FastAPI: `http://127.0.0.1:8001`
- Frontend: `http://127.0.0.1:5173`
- SQLite: `backend/hospital_dss_dev.db`
- Fleet simulation: enabled by default

Protected API calls must send `Authorization: Bearer <access-token>`. The legacy
`X-User-Id` header is rejected. Browser refresh sessions use rotated HttpOnly
cookies plus a matching CSRF header.

## Environment Variables

See `.env.example`.

Required production variables:

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `ALLOW_DEFAULT_DEV_USER=0`
- `AUTH_JWT_SECRET=<at least 32 cryptographically random bytes>`
- `AUTH_COOKIE_SECURE=1`
- `AUTH_JWT_ISSUER` and `AUTH_JWT_AUDIENCE` set to deployment-specific values
- `CORS_ALLOW_ORIGIN_REGEX=<escaped production origin regex>`
- `GOOGLE_MAPS_API_KEY=<secret>` only when Google integration is enabled
- `FLEET_SIMULATION=0` when real ambulance GPS is connected
- Database pool and timeout variables from `.env.example`

Production startup intentionally fails if:

- `ALLOW_DEFAULT_DEV_USER=1`
- `DATABASE_URL` starts with `sqlite`

## PostgreSQL/PostGIS

Alembic is the production schema authority. The baseline revision is
`0001_initial_schema`; it creates the application schema, foreign keys,
uniqueness rules, query indexes, and enables PostGIS when the target is
PostgreSQL.

### Preserve the existing SQLite database

Run this once from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python backend/scripts/migrate.py bootstrap
python backend/scripts/migrate.py current
```

`bootstrap` does not recreate tables. It verifies every expected table and
column before stamping the baseline revision. If verification fails, it stops
without stamping.

### Create a fresh database

For any empty SQLite or PostgreSQL database:

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
python scripts/migrate.py current
```

### Local PostgreSQL with Compose

Docker Desktop must be installed first. Create `.env` from `.env.example`, set
a strong `POSTGRES_PASSWORD`, and set a URL-encoded `DATABASE_URL` when the
username/database differ from their defaults.

```powershell
docker compose up -d postgres
docker compose --profile app up -d --build backend
docker compose ps
```

The database port binds to `127.0.0.1` only. The backend waits for the database
health check, runs `alembic upgrade head`, and then starts Uvicorn. Use
`APP_ENV=development` only for a local seeded demonstration.

### Production deployment order

1. Create an encrypted PostgreSQL backup or storage snapshot.
2. Set `APP_ENV=production`, `ALLOW_DEFAULT_DEV_USER=0`, `AUTH_COOKIE_SECURE=1`, and secret values for `DATABASE_URL` and `AUTH_JWT_SECRET`.
3. Run one migration job: `python backend/scripts/migrate.py upgrade head`.
4. Start API replicas with `RUN_MIGRATIONS=0` so replicas do not race migrations.
5. Verify `/ready`; production readiness fails when the database revision is behind.
6. Provision hospitals and real users through an approved administrative process. Use `backend/scripts/set_user_password.py` only for controlled bootstrap or credential recovery; production startup never inserts development users or sample patients.
7. Keep PostgreSQL private and place the API behind TLS termination/reverse proxy controls.

For PgBouncer transaction pooling, connect `DATABASE_URL` to PgBouncer and keep
the application pool bounded. Start with `DB_POOL_SIZE=10` and
`DB_MAX_OVERFLOW=10`, then tune from observed connection and latency metrics.

Never commit `.env` or place database passwords directly in Compose files.

## Deployment Verification Checklist

- Backend starts with `APP_ENV=production`.
- `python backend/scripts/migrate.py current` reports the Alembic head revision.
- `/health` returns `{"status":"ok"}`.
- `/ready` returns `{"status":"ready"}`.
- Protected endpoint without auth returns `401`.
- `X-User-Id: super-admin` without a bearer token returns `401`.
- Refresh tokens rotate, logout revokes the session, and reused/revoked sessions return `401`.
- Hospital admin cannot read another hospital's beds.
- Ambulance crew cannot read another ambulance mission.
- Transfer accept reserves one bed only.
- Ambulance assignment assigns one available ambulance only.
- Audit logs redact patient details.
- Frontend build succeeds.
- Routing source labels show local OSM, external provider, or fallback.

## Rollback

1. Stop write traffic.
2. Snapshot database.
3. Roll application image back.
4. Run `python backend/scripts/migrate.py downgrade <tested-revision>` only when the release explicitly supports it.
5. Verify health, auth, transfer creation, bed update, and ambulance mission.

The initial migration downgrade removes the entire application schema and must
never be run against a database containing required data. Restore from backup
instead of downgrading the baseline.

## PostgreSQL Backup Examples

```powershell
pg_dump --format=custom --no-owner --file hospital_dss.dump $env:DATABASE_URL
pg_restore --clean --if-exists --no-owner --dbname $env:DATABASE_URL hospital_dss.dump
```

Test restore into a separate database before relying on a backup. Use separate,
least-privileged backup credentials and encrypt retained backup files.

## Production Gaps

- Approved enterprise/health identity-provider integration and MFA are not yet implemented.
- No CI/CD pipeline yet.
- No backup automation yet.
- No automated production reference-data/user provisioning yet.
