# CI/CD and evaluation triggers

Status: the [validation workflow](../../.github/workflows/scaffold.yml) checks docs/contracts, local runtime lint/tests, Docker HTTP demo and Terraform schema without AWS credentials. The [local service](../local-service.md) is implemented; this folder is still not initialized as a Git repository and no hosted workflow execution is claimed. The [future production workflow](deploy.workflow.yml.example) is inert outside `.github/workflows` and requires deployment/evaluation scripts that do not exist yet.

## Future pipeline

| Stage | Concrete intended command/tool | Failure action |
|---|---|---|
| Lint / static | `ruff check src tests`; `mypy src`; `python scripts/validate_scaffold.py` | block PR |
| Unit | `pytest tests/unit` | block PR; use frozen clocks and fake provider |
| Integration | `pytest tests/integration` with ephemeral PostgreSQL/S3-compatible fixture | verify transactions, leases, tenant isolation, artifacts |
| Adapter contract | `pytest tests/adapters` on pinned promptfoo JSON and Ragas fixtures | block version upgrade on normalized-schema drift |
| Offline evaluation | `pytest tests/evaluation --provider=fake` | quality/gate golden cases, no keys or paid calls |
| Security | dependency audit + image scan + IaC policy check | block critical exploitable findings; document explicit exceptions |
| Build | locked Docker build, SBOM, image push and digest output | protected main only; retain digest evidence |
| Stage | AWS OIDC, additive migration, ECS service rollout | migration exit/service stability required |
| Full evaluation | future `lab-ci submit-and-wait --request release-job.json` | exit 1 regression; exit 2 infrastructure/evidence; either blocks promotion |
| Production | environment approval, same digests, alarm observation | circuit-breaker rollback and operator notification |

The `src` and `tests` directories now implement the local slice; future commands referencing the unit/adapter/evaluation subdirectories in the table, `lab-ci`, `mypy` or deployment scripts remain planned. Local dependencies are in `requirements-local.lock`; production hash locks are still required. Current actions use major tags for development validation; production activation requires immutable SHA pins, Dependabot updates and minimal permissions per job.

## Triggers and policy

PRs changing prompts/model/retrieval/code run offline tests and the diagnostic smoke suite if explicitly authorized. Fork PRs receive no provider/API/AWS secrets and run only offline. Never use `pull_request_target` to execute untrusted checkout code with secrets. Full release evaluation runs on protected main against an approved immutable baseline. A nightly schedule (proposal 02:00 UTC) checks drift/provider revision changes on a frozen suite. Weekly human review calibrates judgments and reviews false pass/fail examples. Dataset, judge, rubric or metric upgrades trigger baseline rebuild and manual review. Incident replay is operator-triggered with a new job ID and preserved old evidence.

This document does not create schedules or automations. Paid evaluation calls require configured project budgets and activation during implementation.

## Planned client algorithm

Canonicalize source/config refs; create one idempotency key for `(repository, source SHA, suite, intentional run ordinal)`; POST once and retain the returned ID. Retry ambiguous admission with that key. Poll status with bounded jitter and deadline. On terminal state fetch gate and, if succeeded, report. Validate schema, job ID, expected dataset/config/baseline and policy digest before trusting verdict. Unknown verdict, malformed body, token refresh failure, network timeout or local timeout exits 2. Request cancellation on explicit CI cancellation when possible; server deadline bounds abandoned jobs. Never treat HTTP 200 or job `SUCCEEDED` as a passing gate.

Write the job/report links and sanitized metric decisions to GitHub step summary. Store only authorized redacted artifacts, with 30-day retention. Uploads containing raw data require private artifact access policy. A planned client exits with the verdict code; do not use `continue-on-error` to bypass it. Optional diagnostic jobs can use it only when a separate required release gate still runs.

Deployment credentials: `AWS_DEPLOY_ROLE_ARN`, region, ECR repository, ECS cluster and service names as environment variables; service evaluation bearer token obtained from organization IdP through workload federation, not reused AWS credentials. Provider keys remain server-side. Langfuse key is telemetry-only. Required environment reviewers, branch protection, role trust and policy approval are setup tasks, not completed controls.
