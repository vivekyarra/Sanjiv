# Recovery runbook

## Automated evidence

- `py -m uv run python scripts/reliability_drill.py` stops and restores Redis, MinIO, PostgreSQL,
  the compute worker and API one at a time. It always attempts to restart anything it stopped and
  writes `reports/recovery/reliability-drill.json`.
- `py -m uv run python scripts/backup_restore.py` creates a permission-restricted temporary logical
  backup, restores it into an isolated database, verifies migration head and rejects a corrupted
  artifact. The temporary backup is deleted after verification; only the portable report remains.

## Incident sequence

1. Preserve the correlation ID, operations-status payload and service logs. Do not log or paste
   credentials.
2. Confirm `/health/live`; then inspect `/health/ready` and `/api/v1/operations/status` to identify
   the failing component.
3. Keep the visible truth state honest. A failed live source may transition only through the audited
   degraded/replay path; never relabel replay as live.
4. Restore the single dependency with `docker compose start <service>` for local/demo deployments.
   Do not destroy volumes during diagnosis.
5. Wait for the Compose health check and API readiness, then rerun `npm run demo:preflight`.
6. For PostgreSQL recovery, restore into a new database first, verify the Alembic head and immutable
   records, then switch traffic under the operator's change procedure.
7. For a failed migration, allow the transaction to roll back, capture logs, downgrade one verified
   revision and re-upgrade. Never force-edit `alembic_version`.
8. For a corrupted replay/export, reject on checksum mismatch and regenerate only from the immutable
   audited source record.

## Covered failure evidence

Source outage/replay, stale data, LLM timeout/invalid output, solver timeout/error/infeasibility,
WebSocket overflow/resync, immutable transaction rollback, browser refresh/readback, checksum
corruption and migration cycles are covered in their domain tests. The stored recovery drill covers
single-host dependency, worker and API interruption. Multi-region failover and physically isolated
network operation remain production/operator exercises.
