# Official technology references

Consulted 2026-09-27. These sources inform API choices; they do not establish that this repository implements them. Library versions must be resolved, locked and tested during implementation rather than copying `latest` into a release image.

| Technology | Official source | Design use |
|---|---|---|
| FastAPI | [Release notes](https://fastapi.tiangolo.com/release-notes/) | check OpenAPI/Pydantic compatibility while pinning runtime |
| Pydantic v2 | [Models](https://docs.pydantic.dev/latest/concepts/models/) | boundary validation and model configuration |
| promptfoo | [CLI](https://www.promptfoo.dev/docs/usage/command-line/) | explicit engine concurrency and JSON artifact invocation |
| promptfoo | [Output formats](https://www.promptfoo.dev/docs/configuration/outputs/) | versioned adapter normalization |
| promptfoo | [Assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/) | deterministic assertions against captured outputs |
| Ragas | [RunConfig](https://docs.ragas.io/en/stable/references/run_config/) | explicitly constrain worker/retry settings |
| PostgreSQL | [SELECT / locking](https://www.postgresql.org/docs/current/sql-select.html) | transactional queue claims with SKIP LOCKED; not a general consistent read |
| AWS ECS | [Idempotency](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_Idempotency.html) | persisted launch token plus DB fencing |
| Langfuse | [Dataset experiments](https://langfuse.com/docs/evaluation/experiments/datasets) | import upstream dataset snapshots into local registry |
| Langfuse | [Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose) | current self-hosting requires its own full stack |
| Langfuse | [Compatibility](https://langfuse.com/docs/compatibility) | pin SDK/server pairs during implementation |
| GitHub Actions | [AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) | narrow workload trust, short-lived AWS credentials |
| Terraform | [S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3) | encrypted versioned state and native lockfile |

Architecture decisions, thresholds, retry counts and SLOs are this project's proposals, not recommendations or guarantees attributed to vendors. No market claims beyond the preserved [brief](../PROJECT_BRIEF.md) were independently re-audited in this phase.

Phase 3.1 sources consulted 2026-09-28: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) for connection-pool lifecycle, [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) for request boundaries, and [asyncpg usage](https://magicstack.github.io/asyncpg/current/usage.html) for async PostgreSQL transactions and pools.
