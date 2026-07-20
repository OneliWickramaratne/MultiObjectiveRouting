# Operations Runbook

Last reviewed: 2026-07-13

## Daily Checks

- Confirm backend `/health` and `/ready`.
- Confirm frontend loads and protected dashboards require identity.
- Check hospital bed data freshness.
- Check ambulance location freshness.
- Check route provider status.
- Check model status at `/api/traffic/status`.
- Review transfer errors and failed dispatch attempts.

## Incident: Backend Offline

1. Check `backend/uvicorn-8001.err.log`.
2. Restart with `START_APP.cmd` for development.
3. Verify `/health`.
4. Verify frontend reconnects.
5. If production, check database connectivity and deployment healthchecks.

## Incident: No Eligible Hospital

1. Confirm required ICU type.
2. Confirm ventilator requirement.
3. Confirm hospitals have current bed data.
4. Check whether all candidate hospitals are excluded for capability or capacity.
5. Escalate to manual dispatcher workflow. Do not override clinical requirements silently.

## Incident: Bed Reservation Conflict

Bed claims use conditional atomic updates. A conflict should return `409` and
must not reserve the same bed twice.

Immediate response:

1. Use bed lifecycle view to identify assigned bed.
2. Confirm with receiving hospital.
3. Manually correct bed status.
4. Record override reason in notes.

If repeated conflicts occur, inspect transaction latency and database locks;
do not manually overwrite an active reservation without receiving-hospital confirmation.

## Incident: Ambulance Assignment Conflict

Ambulance claims use ranked conditional atomic updates. A losing concurrent
dispatcher falls through to the next available unit.

Immediate response:

1. Check transfer events for assigned ambulance IDs.
2. Confirm actual crew mission.
3. Reassign one transfer manually only after confirming availability.
4. Record override reason.

If assignments diverge from crew reality, stop automated dispatch for the
affected transfer and reconcile the transfer event log before reassignment.

## Incident: Routing Provider Failure

1. Verify local OSM graph file exists.
2. Check `/api/traffic/status`.
3. Confirm route payload source label.
4. If fallback route is used, treat ETA/risk as degraded and require dispatcher confirmation.
5. Do not present fallback straight-line route as live traffic.

## Incident: Model Unavailable

1. Check `/api/traffic/status`.
2. If model is unavailable, system uses deterministic fallback time formula.
3. Confirm UI labels show fallback source.
4. Do not represent fallback as trained ML prediction.

## Backup and Restore

Alembic supplies schema versioning, but backup scheduling remains an operations responsibility.

Required before production:

- Encrypted database backups.
- Restore rehearsal.
- Backup retention policy.
- Separate backup credentials.
- Audit of backup access.
- Alerting on failed backup jobs and migration failures.

## Data Correction

- Super admin may update hospital and ambulance metadata.
- Hospital admins may update scoped beds and patients.
- Every operational correction should produce audit and lifecycle events.
- PHI must not be entered into free-text operational logs unless required and protected.
