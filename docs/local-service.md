# Phase 3.1 local service

Implemented on 2026-09-28. This is a local development vertical slice, not a production deployment. The [production contracts](../Index.md) remain the target; the differences below are explicit. All 11 documented paths have local handlers, plus FastAPI-generated `/docs`, `/redoc` and `/openapi.json`.

## Implemented behavior

Registration validates strict Pydantic v2 models, rejects duplicate keys/non-finite JSON and unknown fields, canonicalizes UTF-8 JSON, hashes it, and writes immutable local content. Registration deduplicates by project/kind/digest. Files use a flushed temporary file followed by atomic create-only hard link; reads verify SHA-256. Arbitrary filesystem paths and provider URLs are not accepted.

Admission locks the project row and atomically inserts the job and outbox. Same-key replays return the same job; changed input returns 409. Admission checks same-project references, baseline completion/profile compatibility and a 100-nonterminal-job local quota. A separate worker processes the DB queue, so stopping the API does not erase queued work. Evaluation never runs in FastAPI background tasks.

The worker processes one job at a time and at most `min(config.concurrency, 4)` fake calls concurrently, with a bounded input queue. A session advisory lock admits only one local worker per database. Startup terminalizes interrupted attempts as `FAILED / ENGINE_CRASH`; there are no automatic retries. An attempt fence and row-locked finalization prevent completion after cancellation or stale-attempt replacement. DB-clock deadlines are checked on claim, every 50 ms during evaluation, and at commit. A stopped worker cannot expire queued jobs until it resumes.

Queued cancellation is immediate; active cancellation becomes `CANCEL_REQUESTED` and is settled by the worker. Report upload precedes the transaction committing report metadata, gate and terminal state. Crashes may leave orphan files; garbage collection is deferred.

## Authentication and supported registry

Set `LAB_LOCAL_ONLY=1`. `LAB_LOCAL_TOKENS` maps a token (at least 32 ASCII non-whitespace characters) to `{project_id, scopes}`. Tokens use constant-time comparison; project comes from the mapping, not the body. Cross-project lookups return 404; missing scopes return 403. There is **no JWT validation, token expiry or RLS yet**. Bind only to loopback. Compose uses the local DB owner role and is not production-ready.

Only `fake:reference`, `fake:wrong` and `fake:error` targets are supported. `config_for()` in [local_profile.py](../src/llm_regression_lab/local_profile.py) supplies the approved fixed policy and provenance. Only `assertion_pass_rate` is admitted; promptfoo and Ragas are neither installed nor invoked. Provenance explicitly identifies fake/non-installed components. `engine_image_digest` hashes the local profile marker, **not a container image**, until the real registry is implemented.

The fake provider echoes the reference, returns a canned wrong answer, or raises a simulated timeout. Latency measures that local function, not an LLM. Cost and provider tokens are zero because no LLM ran. Reports show deterministic assertion outcomes on synthetic answers but always return `INCONCLUSIVE`. Statistical gates, real retrieval/judge metrics, token/spend reservations and production registry publishing are deferred. The demo's exit 0 validates the diagnostic flow; it cannot approve a release.

## Docker runbook

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-local.lock -r requirements-dev.txt
# First run only; preserve an existing .env:
Copy-Item .env.example .env
docker compose --profile local config --quiet
docker compose --profile local up -d --build --wait
$env:LAB_TOKEN='local-dev-token-change-me-0123456789abcdef'
.venv\Scripts\python scripts/local_demo.py
docker compose --profile local logs --tail 50 api worker migrate
docker compose --profile local down
```

The public development token is for loopback testing only. `LAB_TOKEN` must match a configured key if changed. The API binds host `127.0.0.1:18080`; PostgreSQL binds `127.0.0.1:55432`. Change `LAB_PORT` or `POSTGRES_PORT` if occupied. Compose runs migrations before API/worker startup and shares `local_artifacts` between them. The migration container exits successfully. `down` retains both volumes. Changing `.env` does not rotate an initialized database password. See [Operations](../Operations.md) before resetting data.

To validate without creating `.env`, use `docker compose --env-file .env.example ...`. These credentials are known public development values. Real secrets must stay out of shell logs and version control.

## Native Python runbook

Start only PostgreSQL with `docker compose --env-file .env.example up -d --wait postgres`. Install the local lock plus dev requirements, then configure each terminal:

```powershell
$env:PYTHONPATH='src'
$env:LAB_LOCAL_ONLY='1'
$env:DATABASE_URL='postgresql://lab:local-only-change-me@127.0.0.1:55432/lab'
$env:LAB_ARTIFACT_ROOT="$PWD/artifacts/local"
$env:LAB_LOCAL_TOKENS='{"local-dev-token-change-me-0123456789abcdef":{"project_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","scopes":["versions:read","versions:write","jobs:read","jobs:write","reports:read"]}}'
.venv\Scripts\python -m llm_regression_lab.database
.venv\Scripts\python -m uvicorn llm_regression_lab.api:create_app --factory --host 127.0.0.1 --port 18080
# In another terminal with the same environment:
.venv\Scripts\python -m llm_regression_lab.worker
```

Use one worker and the same artifact root for API/worker. Do not mix a native API filesystem with a worker's Docker-only volume. Migrations have a checksum ledger, transaction lock and additive local migration; replay is safe. The runner adopts the known six-table Phase 2 bootstrap and rejects missing bootstrap tables. It is not an arbitrary-schema importer.

## Verification and limits

```powershell
.venv\Scripts\python -m ruff check src tests scripts
.venv\Scripts\python scripts/validate_scaffold.py
$env:TEST_DATABASE_URL='postgresql://lab:local-only-change-me@127.0.0.1:55432/lab'
.venv\Scripts\python -m pytest -q
```

Tests create a UUID-named database per integration test through the supplied local admin connection, then remove that test database. They do not truncate the supplied database. Without `TEST_DATABASE_URL`, integration tests explicitly skip; unit/contract tests still run. Python 3.12 is the Docker/CI baseline; Windows Python 3.14 is also used for local checks.

Generated OpenAPI is validated against route IDs, scopes, request bodies, success statuses and normalized core request/response schemas. Actual HTTP report/error payloads are independently checked against published JSON Schemas. Conditional metric-unit rules use Pydantic validators and response checks; generated and planned OpenAPI need not be byte-identical. Validation errors use the shared `application/problem+json` envelope.

The runtime dependency versions are recorded in [requirements-local.lock](../requirements-local.lock); this is not a production hash lock. Production work still includes distributed leases, provider quotas/spend, retries, raw case persistence, OIDC/RLS, S3/ECS, real engines, calibration/confidence intervals, Langfuse, retention, static type coverage, security audits and measured SLOs. See the [roadmap](roadmap.md).


## MiniMax provider

`config_for_minimax()` creates the approved `local-minimax-v1` configuration for `minimax:MiniMax-M3`. The worker calls the fixed official endpoint; it sends the question and contexts, never references or assertions. Thinking is disabled, temperature is 0.1, and the default smoke test uses one repetition with 256 maximum completion tokens. Provider model IDs and reported input/output token counts are recorded in successful reports. Missing usage, truncated answers and malformed responses fail closed. Authentication, rate limits and timeouts have distinct stable error codes; requests are not retried.

The adapter reserves conservative byte-based input estimates plus maximum output tokens before each call and checks actual reported usage afterward. These are local job safeguards, not a provider billing hard cap: failed/cancelled requests may still be charged, failed-job spend is not durably accounted, and aggregate account spend is not enforced. Use provider account limits for a financial cap. Inputs over the adapter's 32,000 estimated-token limit or outputs over 4,096 tokens are rejected.

Cost uses a frozen September 30, 2026 M3 standard PAYG estimate: $0.30 per million input tokens and $1.20 per million output tokens. Cached input discounts are deliberately not applied, so this can overestimate actual charges; subscription billing may differ. The pricing snapshot is hashed into the configuration. Sources: [official API](https://platform.minimax.io/docs/api-reference/text-openai-api), [official pricing](https://platform.minimax.io/docs/guides/pricing-paygo).

Run `scripts/minimax_demo.py` with `LAB_TOKEN` set after adding `MINIMAX_API_KEY` to `.env` and restarting Compose. A successful smoke test has assertion pass rate 1.0 and an INCONCLUSIVE gate: real generation is implemented, while calibrated quality judgments and statistical release decisions remain planned.
