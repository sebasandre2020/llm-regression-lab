# Reports and CI gates

Status: production target. [Local report/gate endpoints](../local-service.md) work with fake observations and always return an inconclusive release gate. Real metrics and statistical gates remain planned. [Illustrative report](../../examples/report.json) · [Illustrative gate](../../examples/gate.json) · [Schemas](../../contracts/schemas.json)

`GET /v1/jobs/{job_id}/report` requires `reports:read`. Return 200 `Report` only after the immutable report and gate commit with `SUCCEEDED`. Active jobs return 409 `REPORT_NOT_READY`; failed/cancelled jobs return 409 `REPORT_UNAVAILABLE`; deleted artifacts return 410. Response includes an ETag digest. The report summarizes aggregate evidence; raw outputs are restricted S3 artifacts accessed through operator tooling, not public URLs.

Report fields include schema/job/input IDs, baseline ID, completion time, execution manifest, coverage, metrics, cost, gate and immutable artifact digest. The manifest records candidate/config/dataset revisions, engine image and adapter versions, judge/rubric and metric policy, pricing revision, execution profile, observed provider revision, seed and repetitions. `comparison_fingerprint` hashes only the dimensions that must match; target changes are listed separately. Do not let callers supply this fingerprint.

Each metric entry records name, unit (`ratio`, `ms`, `usd`), direction, candidate value, nullable baseline value, nullable paired delta and confidence interval. USD values are six-decimal strings (delta may be signed); ratio and millisecond values are JSON numbers. Missing measurements use null, never zero; metric error details live in restricted case results. `coverage` provides expected and valid case-observation counts; every repetition counts. `cost` distinguishes measured token usage and estimated USD derived from a frozen pricing snapshot; a missing provider usage record sets `usage_complete: false`.

`GET /v1/jobs/{job_id}/gate` returns 200 `Gate` for terminal jobs, even when execution failed. Active jobs return 409 `REPORT_NOT_READY`. For failed/cancelled jobs, no report is needed to emit `INCONCLUSIVE`. Gate fields: job ID, verdict, reason codes, policy version and digest, decided timestamp, metric decisions. Decisions record thresholds and evidence, allowing a CI consumer to explain the failed dimension without parsing prose.

| Verdict | Meaning | Planned client exit |
|---|---|---|
| `PASS` | complete comparable evidence satisfies all gates | 0 |
| `REGRESSION` | complete evidence violates at least one quality, latency or cost gate | 1 |
| `INCONCLUSIVE` | execution failed/cancelled, incomparable, missing evidence, insufficient sample or baseline-only run | 2 |

Reason codes: `WITHIN_LIMITS`, `QUALITY_REGRESSION`, `LATENCY_REGRESSION`, `COST_REGRESSION`, `EXECUTION_FAILED`, `CANCELLED`, `BASELINE_REQUIRED`, `INCOMPATIBLE_BASELINE`, `INSUFFICIENT_EVIDENCE`, `MISSING_METRIC`, `UNKNOWN_COST`. `REGRESSION` is permitted only on a `SUCCEEDED` job. The service does not infer quality regression from a promptfoo process exit code. See [gate algorithm](../services/gating.md).
