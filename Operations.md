# Operations runbook

Status: the [Phase 3.1 local API and worker](docs/local-service.md) are implemented with a fake provider. AWS procedures and production SLOs remain plans. See [validation evidence](docs/validation.md) for actual results and limitations.

## Local Docker Compose

Prerequisites: Docker Engine/Desktop with Linux containers, Docker Compose v2, and Python (3.12 intended CI baseline; local validation version recorded separately). Ports bind loopback only; default host PostgreSQL port is 55432 to avoid common local conflicts. No AWS, provider, or Langfuse credentials are needed.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m ruff check scripts
.venv\Scripts\python scripts/validate_scaffold.py
Copy-Item .env.example .env
# Edit .env to set a local-only password. Do not overwrite an existing .env.
docker compose config --quiet
docker compose up -d --wait postgres
docker compose ps
docker compose exec postgres psql -U lab -d lab -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
docker compose down
```

`down` stops/removes containers but retains the named data volume. Bootstrap SQL runs only on first initialization. Changing SQL does not migrate an existing volume, and changing `.env` does not rotate an initialized database password; future application migrations and explicit password rotation must handle those changes. If bootstrap failed, inspect `docker compose logs postgres`. To reset a disposable local DB, first confirm there is no valuable data and then explicitly run `docker compose down --volumes`; this destroys the local database. Never use that reset procedure for shared data.

The commands above start PostgreSQL alone. For the working API, separate worker and migration container, use `docker compose --profile local up -d --build --wait` and follow the [local service runbook](docs/local-service.md). S3 and Langfuse remain absent. A future S3 emulator cannot prove AWS IAM/KMS/conditional-write correctness. A Langfuse profile must track its full upstream dependencies and compatible versions.

## Proposed production controls

Before launch: finish runtime/migrations, IAM/RLS and network modules, pin image/dependency versions, provision state and secrets through approved channels, confirm data approval, configure budgets/alarms, validate full evaluation gate, rehearse cancellation/crash recovery and restore. The [deployment procedure](docs/delivery/deployment.md) defines promotion/rollback. No operational command here authorizes provisioning.

On-call ownership initially belongs to the project maintainer; name actual primary/backup contacts and escalation destination before deployment. Page owner acknowledges in 15 minutes (proposed response target). Escalate integrity/data-access issues immediately, provider outages after error-budget burn or queue alarms, and spend anomalies immediately. Capture job/attempt/request/image IDs, recent changes, scope and timestamps; exclude prompt contents and secrets.

## Failure recovery

| Symptom | Diagnose | Recovery and validation |
|---|---|---|
| Jobs remain queued | outbox lag, dispatcher health, quotas, ECS capacity | restore dispatcher/capacity; reuse dispatch intents; confirm oldest age falls |
| RunTask response lost | persisted token, attempt/task inventory | retry identical launch within token validity; never blindly create another attempt |
| Worker lease expired | heartbeat, DB reachability, ECS task state | revoke fence, StopTask, reconcile slots/spend; retry only inside budget/deadline |
| Provider 429/timeouts | account-wide RPM/TPM, provider status, retry counts | lower concurrency, honor Retry-After; do not label outage as quality regression |
| Provider auth failure | secret version/permissions, target registry | fail nonretryably; rotate secret, then explicitly submit new job |
| S3 upload/commit failure | checksum, object version, DB transaction state | reuse immutable upload if verified; stale attempt cannot commit; orphan sweeper cleans |
| Integrity mismatch | expected vs observed hash, IAM audit | stop affected jobs and page; quarantine object; no automatic replacement of evidence |
| Cancellation hangs | revoked fence, ECS StopTask status | prevent new calls, wait finite call timeout, stop task, settle conservative usage |
| DB outage | RDS events, connections, migration compatibility | stop new admissions/calls; restore DB; fence/reconcile before dispatch resumes |
| Langfuse down | bounded export queue and dropped-event metric | recover exporter; evaluation continues; document telemetry gap |
| CI timeout | retained job ID and server deadline | exit 2; inspect/reconnect to same job; cancel if abandoned, no duplicate submission |
| Quality regression | immutable paired cases and thresholds | inspect prompt/model/retrieval change; revert or reviewed new baseline, no automatic pass-seeking retries |

## Disaster recovery and maintenance

Restore drill quarterly: isolate destination network, disable dispatch, restore RDS to chosen timestamp, validate referenced S3 versions/hashes, revoke old attempt fences, inventory and stop surviving source tasks, reconcile budget reservations, verify project authorization and a synthetic job, then reopen admission. Record actual RPO/RTO and data loss; [targets](docs/services/observability.md) are not guarantees. Missing artifacts become unavailable evidence, never reconstructed scores.

Database backups and S3 versioning have different timelines; coordinate restores. Do not restore raw production data into developer laptops. Rotate provider/DB/Langfuse secrets through secret versions, restart tasks as needed, and revoke old credentials after verification. Keep old images until all jobs using them complete and rollback window ends.

Daily: inspect spend, queue/deadline failures, storage retention and missing telemetry. Weekly: review inconclusive rates, baseline age and judge calibration. Monthly: dependency/image security review and drift plan. Before every release: confirm baseline compatibility, current full-suite evidence, migration compatibility and rollback task revisions. Alerts and SLI definitions live in [observability](docs/services/observability.md).

## Evidence discipline

For every benchmark publish date, environment, hardware/task sizes, concurrency, dataset/config IDs, baseline ID, engine digest, provider/judge revisions, repetitions, token/pricing source and failure counts. Report p50/p95 latency, confidence intervals and estimated versus billed cost separately. Until that exists, use “proposed target” everywhere; architecture diagrams are not deployment proof.
