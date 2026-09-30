# Evaluation jobs

Status: production target. [Local submission, polling and cancellation](../local-service.md) are implemented; cloud quotas, spend reservations and retries below remain planned. [Job request example](../../examples/job.json) · [Schemas](../../contracts/schemas.json)

## Submit

`POST /v1/jobs` with `jobs:write` and `Idempotency-Key` accepts `JobRequest`:

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | literal `1.0` | submission representation |
| `dataset_version` | content digest | existing project dataset |
| `config_version` | content digest | existing project configuration |
| `baseline_job_id` | UUID or null | completed comparable job; null means baseline creation |
| `deadline_seconds` | integer 60–3600 | total wall time from admission, including queue and retries |
| `source_revision` | 40 lowercase hex | source commit for CI provenance |

Admission checks scope, existing versions, config limits, baseline compatibility and project quota. Project is token-derived. Default quota proposal: 100 queued jobs and 4 active attempts/project; global active task cap 16. Queue-full admission returns 429 without creating a job. Reserve a maximum job spend from the project's daily budget before admission; release unused funds at terminal settlement. Unknown actual provider usage remains conservatively charged.

Return 202 `Job` and `Location`; a duplicate submission returns 200 with the existing current `Job`. Idempotency scope is `(project_id, route, key)`. Store the canonical request hash and job atomically under a unique constraint. Same key/body returns the same ID; different body returns 409 even if the first job is terminal. Concurrent conflicts wait for/observe the winning transaction. Retain keys for the job metadata lifetime (365 days); delete atomically with the job and document this replay window. An ambiguous network response is retried with the original key. A deliberate rerun requires a new key.

`Job` includes ID, input refs, baseline, state, current attempt number, admitted/updated/deadline timestamps, optional execution error, and links. `attempt` is zero while initially queued and increases only upon a reserved launch. Status is not a metric. No result is derived from counters while the job is active.

## Inspect and cancel

`GET /v1/jobs/{job_id}` requires `jobs:read`, returns 200 for every state, 404 across project boundaries. The [state diagram](../../Class.md) is normative. Clients poll terminal states `SUCCEEDED`, `FAILED`, `CANCELLED`; a valid report exists only for `SUCCEEDED`.

`POST /v1/jobs/{job_id}/cancel` takes no body. Queued or retry-wait jobs become `CANCELLED` immediately (200); active/dispatching jobs enter `CANCEL_REQUESTED` (202). Repeated pending cancellation returns 202; repeated cancelled cancellation returns 200. Other terminal jobs return 409 `INVALID_STATE`. Under a row lock, whichever transaction commits first—completion or cancellation—wins. The worker cannot publish once cancellation has won. Reconciler fences the attempt, stops the ECS task, and settles already-incurred spend. Cancellation does not promise to undo an external provider request.

## Service constraints

Job retries are automatic only for classified transient failures, maximum 3 attempts inside the original deadline and budget. Configuration, provider authorization and artifact-integrity errors are not retried. A quality regression is never auto-retried to obtain a pass. See [orchestration](../services/orchestration.md) for retry ownership and [reports](reports.md) for terminal output behavior.
