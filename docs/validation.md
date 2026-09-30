# Validation evidence

## Phase 3.1 — 2026-09-28

Implemented and verified a local fake-provider vertical slice; production evaluation and infrastructure remain planned.

| Check | Result | Evidence |
|---|---|---|
| Unit/contract/PostgreSQL integration suite | PASS | `python -m pytest -q`: 29 passed; isolated temporary PostgreSQL databases |
| Runtime and tooling lint | PASS | `python -m ruff check src tests scripts` |
| Documentation/contracts | PASS | 24 Markdown files, 140 local links, 6 fixtures, 11 API paths, 3 YAML files |
| Generated OpenAPI | PASS | route/operation IDs, scopes, request bodies, success statuses and core normalized model parity; problem media types checked |
| Local Docker build | PASS | Python 3.12.14 image with resolved local dependency versions |
| Docker startup/migration | PASS | additive migration exits 0; API and PostgreSQL healthy; separate worker running |
| End-to-end HTTP demo | PASS | actual registration -> job -> worker -> report/gate for reference, wrong-answer and simulated timeout |

The HTTP demo produced `SUCCEEDED` with assertion pass rate 1.0 for the reference echo, `SUCCEEDED` with 0.0 for the canned wrong answer, and `FAILED / PROVIDER_TIMEOUT` for the fake provider error. All gates were `INCONCLUSIVE`. These numbers characterize synthetic fixtures, not model accuracy or production performance. Reports recorded zero provider tokens/cost because no provider ran.

Coverage includes strict validation, duplicate JSON keys, invalid Unicode, body limits, immutable hashes/corruption, concurrent first-time idempotent admission, project/scope isolation, baseline mismatch, queue quota/replay, queued/running cancellation, singleton worker exclusion, interrupted-attempt recovery, deadlines, migration replay, sanitized dependency failures and a bounded fake-call concurrency check.

Local tests used Windows Python 3.14.5 and Docker Engine 29.8.0; the HTTP service ran in Linux/Python 3.12.14 with PostgreSQL 17.6. Port 8000 was occupied, so the service uses loopback port 18080. Local Compose services and demo data are retained for review; stop them with `docker compose --env-file .env.example --profile local down`. No AWS provisioning, paid calls or production metrics are claimed. The GitHub workflow was updated but has not run remotely.

## Phase 2 historical record — 2026-09-27

The following historical record covers the original documentation/scaffolding phase, before the local runtime above was implemented. Performance, cloud deployment and real evaluation accuracy remain unmeasured.

### Executed scaffold checks

| Check | Result | Evidence / environment |
|---|---|---|
| Python scaffold lint | PASS | Ruff 0.12.12; `python -m ruff check scripts` |
| Documentation and contracts | PASS | 23 Markdown files, 106 local links, 6 schema fixtures, 11 API paths, 3 YAML files; regeneration matches saved JSON |
| OpenAPI | PASS | OpenAPI 3.1 structural validation with openapi-spec-validator 0.7.2 |
| JSON Schema | PASS | Draft 2020-12 and format validation with jsonschema 4.25.1 |
| Compose configuration | PASS | `docker compose --env-file .env.example config --quiet` |
| PostgreSQL bootstrap | PASS | `postgres:17.6-bookworm` became healthy; six public tables and one local project row verified through psql with `ON_ERROR_STOP=1` |
| Terraform formatting | PASS | Terraform 1.13.3 in official Docker image, `fmt -check` |
| Terraform provider/schema | PASS | `init -backend=false -input=false`; signed AWS provider 6.66.0 locked; `validate` returned valid |

Host: Windows, Python 3.14.5, Docker Engine 29.8.0 with Linux containers. Intended CI Python baseline is 3.12; GitHub-hosted workflow execution is not yet verified. Terraform ran in a Linux container because no native Terraform executable was installed. Provider initialization downloaded dependencies only; no remote backend, AWS plan/apply, cloud credentials, service deployment or paid model calls were used.

The temporary local PostgreSQL container and network were stopped after inspection. The test-created database volume was removed after confirming it belonged to this scaffold. The Python virtual environment and Terraform plugin cache remain ignored local tooling; the provider lockfile is a deliverable.

### Scaffold check limits

The validator checks local Markdown link targets, contract regeneration drift, OpenAPI structure, JSON Schema example conformance, API/index parity and YAML syntax. It does not render Mermaid, prove statistical gate correctness, implement authorization, or test a live API. External links were consulted as sources, not exhaustively availability-tested. Example digests are syntactic placeholders. Terraform formatting/validation, where available, cannot prove IAM correctness or deployment success.


## MiniMax integration — September 30, 2026

The live Docker HTTP smoke test completed job `e27f2f61-546a-4176-a080-84aea81dd83c` with MiniMax-M3, assertion pass rate 1.0, 183 reported input tokens and 3 output tokens. Frozen-rate estimated cost rounded to $0.000058. The gate correctly remained INCONCLUSIVE (BASELINE_REQUIRED). This is a single connectivity/usage test, not model-quality or production-performance evidence. Adapter mock tests cover request isolation, usage accounting, provider error classification and pre-request budget rejection.
