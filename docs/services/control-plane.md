# Control plane

Status: production control-plane specification with a [local subset implemented](../local-service.md). The service owns HTTP admission, project authorization, version registry, job status and report reads; execution runs separately. Production JWT/RLS and spend controls below remain planned. [API contracts](../../Index.md) define the routes.

Per request: validate content type/size before body parsing, reject duplicate JSON keys, authenticate, resolve project, validate schema, authorize referenced resources, canonicalize, then use a short DB transaction. Use a bounded async connection pool (initial proposal 10 connections/API replica, two replicas; dispatcher 5, workers 2 each). Sum maximum configured pools below the RDS connection budget with headroom for migrations and incident access. Slow provider calls never hold a DB transaction.

Dependencies: PostgreSQL is required for admission/status; S3 is required for registration/report fetch; the IdP JWKS cache has a bounded TTL and cannot accept unknown keys offline. Langfuse is optional. S3 timeout does not roll back a committed accepted job. If a report fetch cannot reach S3 return 503; never synthesize a gate from partial bytes.

One transaction inserts the idempotency row, job, budget reservation and outbox. Unique-constraint conflicts read the existing request hash before returning. Transaction failures are retryable only if the key is preserved. Return 202 after commit, never after merely placing a coroutine on an event loop.

Configuration: `DATABASE_URL` from secret reference, `ARTIFACT_BUCKET`, `AWS_REGION`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `JWKS_CACHE_SECONDS`, `MAX_BODY_BYTES`, pool limits and project quotas. Validate required settings at startup. Feature flags cannot alter a submitted config's policy; changes create new config versions. `/health/ready` checks schema compatibility with the binary's supported migration range.

Required implementation tests: concurrent idempotent admission creates one job/outbox; cross-project IDs return 404; malformed JWTs fail; rejected admissions consume no quota; DB failure after S3 upload leaves only a collectible orphan; cancellation and completion race has exactly one authoritative outcome. Performance targets are in [observability](observability.md).
