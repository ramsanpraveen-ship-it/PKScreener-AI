# Incident and Recovery Guide

## Current scope

There is no live broker execution path. Incidents covered here concern scan freshness, scheduled jobs, the local API/database, and simulated paper state. If a future broker adapter is added, stop and use its separately reviewed emergency runbook.

## Freshness or market-data failure

1. Stop interpreting candidates and do not advance paper state manually.
2. Check the latest scan metadata, expected session, benchmark date, stock dates, and analysis-error flag.
3. Preserve logs and source artifacts; do not replace a stale run with an older result.
4. Re-run only after the source/calendar issue is understood. The simulator must reject missing or mismatched metadata.

## Scheduler/API/database failure

1. Disable the scheduled job before repairing it to prevent overlapping runs.
2. Capture process output, timestamps, health status, and database error details without exposing secrets.
3. Back up SQLite using a consistent backup procedure; do not edit the database while the simulator is active.
4. Restore into a copy first, verify session/trade counts and uniqueness, then resume.
5. Keep PostgreSQL-backed dashboard panels disabled until connectivity and migrations/schema checks succeed.

## Duplicate or inconsistent paper session

The simulator uses a unique session key and an immediate SQLite write transaction. If integrity errors or unexpected state appear, stop scheduling, preserve the database, compare the session ledger and source scan, and require manual review before resuming. Do not delete rows to force a rerun.

## Future broker critical event (not currently supported)

Freeze new entries; do not retry a timed-out order until broker state is reconciled; preserve broker order/trade snapshots; verify account identity and positions; record every discrepancy; require explicit human recovery. Do not automatically liquidate positions.
