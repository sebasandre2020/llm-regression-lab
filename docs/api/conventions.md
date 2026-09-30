# API conventions and errors

Status: production v1 target contract. All listed routes have [local handlers](../local-service.md); local auth, engine and storage differences are documented there. Machine-readable definitions: [OpenAPI](../../contracts/openapi.json) and [schemas](../../contracts/schemas.json).

HTTPS only. JSON UTF-8; maximum request size 1 MiB including inline registration. Unknown fields are rejected. UUIDs identify jobs; `sha256:` plus 64 lowercase hex characters identifies content. Dates are RFC 3339 UTC. Money is a nonnegative decimal string in USD, latency is milliseconds, token counts are integers, quality scores are in [0,1]. NaN and infinity are invalid. There is no list endpoint or pagination in v1; callers retain returned IDs. A future list contract will use opaque project-bound cursors.

Bearer access tokens carry `project_id` and scopes. Tokens issued by the organization IdP are checked for issuer, audience `llm-regression-lab`, signature and expiry; maximum accepted lifetime is 15 minutes. There is no token issuance endpoint here. HTTPS reverse proxy authenticates network access, but application code still authorizes resources. `/health/live` and `/health/ready` are restricted by network/routing policy; neither exposes details or secrets. Liveness returns 200 if the process/event loop responds; readiness returns 200 if DB schema is compatible and a DB query succeeds, otherwise 503. Provider and Langfuse outages do not fail API readiness.

Every response includes `X-Request-ID`. POST jobs requires `Idempotency-Key` of 8–128 printable ASCII characters. Server-generated request IDs avoid trusting arbitrary caller log content. GET is side-effect free; cancel is naturally idempotent. Registration deduplicates by canonical content digest. Error responses use `application/problem+json`:

```json
{"type":"urn:llm-regression-lab:error:IDEMPOTENCY_CONFLICT","title":"Idempotency key reused with different content","status":409,"code":"IDEMPOTENCY_CONFLICT","detail":"Use a new key for a changed request.","request_id":"req-example","retryable":false}
```

| HTTP | Code | Client action |
|---|---|---|
| 400 | `INVALID_JSON` | repair malformed encoding/body |
| 401 | `UNAUTHENTICATED` | refresh token once; response includes Bearer challenge |
| 403 | `FORBIDDEN` | request missing scope from project owner |
| 404 | `NOT_FOUND` | check ID and project; includes inaccessible resources |
| 409 | `IDEMPOTENCY_CONFLICT` | new key only for an intended new request |
| 409 | `INVALID_STATE` | terminal cancellation is not allowed |
| 409 | `BASELINE_INCOMPATIBLE` | select matching completed baseline |
| 409 | `REPORT_NOT_READY` | poll job; `Retry-After: 5` |
| 409 | `REPORT_UNAVAILABLE` | failed/cancelled job has no authoritative report |
| 410 | `ARTIFACT_EXPIRED` | report/registered bytes removed under retention |
| 413 | `PAYLOAD_TOO_LARGE` | reduce payload; bulk registration deferred |
| 422 | `VALIDATION_ERROR` | repair fields; safe field paths only |
| 429 | `QUOTA_EXCEEDED` | honor `Retry-After`; job was not accepted |
| 500 | `INTERNAL_ERROR` | retry admission with same key |
| 503 | `DEPENDENCY_UNAVAILABLE` | retry with same key and jitter |

Execution errors are stored on the job, not returned as HTTP 500 for a successful GET. Stable execution codes: `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMIT`, `PROVIDER_AUTH`, `ENGINE_CRASH`, `INVALID_ENGINE_OUTPUT`, `ARTIFACT_INTEGRITY`, `DISPATCH_FAILED`, `LEASE_EXPIRED`, `DEADLINE_EXCEEDED`, `BUDGET_EXCEEDED`, `CANCELLED`. Failures set gate `INCONCLUSIVE` with `EXECUTION_FAILED` or `CANCELLED`. HTTP success never implies gate success.

Polling: initial 2 seconds, exponential backoff to 15 seconds, full jitter, honor larger Retry-After. Stop at caller timeout and emit exit 2; do not silently resubmit. Reconnect using the same job ID. Status responses use `Cache-Control: no-store`; immutable report responses carry ETag equal to report digest, but authenticated access remains required.

Proposed API targets at 20 admission requests/second, 1 MiB maximum input and healthy dependencies: admission p95 <500 ms, metadata reads p95 <200 ms, version registration p95 <2 s. These are unmeasured; SLO definitions are in [observability](../services/observability.md).
