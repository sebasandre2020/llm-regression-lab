# Documentation index

The [Phase 3.1 local service](docs/local-service.md) implements all listed routes with a fake provider. Detailed production contracts remain targets where that guide identifies differences.

| Area | Entry point |
|---|---|
| Implemented local service and setup | [Local service](docs/local-service.md) |
| Recruiter introduction and examples | [README](README.md) |
| Boundaries, topology and lifecycle | [Architecture](Architecture.md) |
| Interfaces, state and persistence | [Class](Class.md) |
| Local operations and incident response | [Operations](Operations.md) |
| Requirements and scope | [Project brief](PROJECT_BRIEF.md) |
| Phase 3 acceptance criteria | [Roadmap](docs/roadmap.md) |
| Validation actually performed | [Validation](docs/validation.md) |
| Official source references | [References](docs/references.md) |

## API map

| Method and path | Scope | Contract |
|---|---|---|
| POST `/v1/dataset-versions` | `versions:write` | [Immutable versions](docs/api/versions.md) |
| POST `/v1/config-versions` | `versions:write` | [Immutable versions](docs/api/versions.md) |
| GET `/v1/dataset-versions/{version_id}` | `versions:read` | [Immutable versions](docs/api/versions.md) |
| GET `/v1/config-versions/{version_id}` | `versions:read` | [Immutable versions](docs/api/versions.md) |
| POST `/v1/jobs` | `jobs:write` | [Jobs](docs/api/jobs.md) |
| GET `/v1/jobs/{job_id}` | `jobs:read` | [Jobs](docs/api/jobs.md) |
| POST `/v1/jobs/{job_id}/cancel` | `jobs:write` | [Jobs](docs/api/jobs.md) |
| GET `/v1/jobs/{job_id}/report` | `reports:read` | [Reports and gates](docs/api/reports.md) |
| GET `/v1/jobs/{job_id}/gate` | `reports:read` | [Reports and gates](docs/api/reports.md) |
| GET `/health/live` | private probe, no bearer | [Conventions](docs/api/conventions.md) |
| GET `/health/ready` | private probe, no bearer | [Conventions](docs/api/conventions.md) |

[OpenAPI 3.1](contracts/openapi.json) · [Shared schemas](contracts/schemas.json) · [Errors and conventions](docs/api/conventions.md)

## Service and background process map

| Component | Responsibility | Specification |
|---|---|---|
| API admission | auth, validation, idempotency | [Control plane](docs/services/control-plane.md) |
| Dispatcher | outbox polling and RunTask | [Orchestration](docs/services/orchestration.md) |
| Reconciler | leases, lost tasks, retry, cancel | [Orchestration](docs/services/orchestration.md) |
| Evaluation worker | bounded provider calls, evidence | [Evaluation](docs/services/evaluation.md) |
| promptfoo adapter | deterministic and prompt assertions | [Evaluation](docs/services/evaluation.md) |
| Ragas adapter | retrieval and answer metrics | [Evaluation](docs/services/evaluation.md) |
| Gate engine | comparability and release decisions | [Gating](docs/services/gating.md) |
| Artifact registry / sweeper | hashes, retention and orphan cleanup | [Storage](docs/services/storage.md) |
| Telemetry exporter | Langfuse traces and system metrics | [Observability](docs/services/observability.md) |
| CI client | submit, poll and classify exit | [CI/CD](docs/delivery/ci-cd.md) |
| Infrastructure | networks, IAM, RDS, ECS, S3 | [Deployment](docs/delivery/deployment.md) |

## Scaffolding files

[Compose](compose.yaml) · [Environment example](.env.example) · [SQL](infra/postgres/001_scaffold.sql) · [Terraform](infra/terraform/README.md) · [Docker blueprint](infra/docker/Dockerfile.blueprint) · [Active scaffold CI](.github/workflows/scaffold.yml) · [Future deployment workflow](docs/delivery/deploy.workflow.yml.example) · [Validator](scripts/validate_scaffold.py) · [Contract generator](scripts/build_contract.py)

## Implemented source

[API](src/llm_regression_lab/api.py) · [Pydantic models](src/llm_regression_lab/models.py) · [Job service](src/llm_regression_lab/service.py) · [Local worker](src/llm_regression_lab/worker.py) · [Artifact adapter](src/llm_regression_lab/artifacts.py) · [Migration runner](src/llm_regression_lab/database.py) · [Local migration](infra/postgres/002_local_runtime.sql) · [Dockerfile](Dockerfile) · [HTTP demo](scripts/local_demo.py) · [Integration tests](tests/test_integration.py) · [Contract tests](tests/test_contracts.py)
