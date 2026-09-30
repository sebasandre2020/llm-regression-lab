# Classes, state and persistence

Status: production implementation blueprint. The [local subset](docs/local-service.md) now implements request/response models, JobService, FileArtifacts and LocalWorker. Diagram names below describe target responsibilities; not every interface exists yet.

```mermaid
classDiagram
  class JobRequest {
    +Digest dataset_version
    +Digest config_version
    +UUID baseline_job_id
    +int deadline_seconds
  }
  class JobService {
    +submit(project, key, request) Job
    +cancel(project, job_id) Job
  }
  class JobRepository {
    +create_with_outbox()
    +claim_attempt()
    +complete_if_fenced()
  }
  class Dispatcher {
    +reserve_capacity()
    +launch_attempt()
    +reconcile()
  }
  class EvaluationWorker {
    +heartbeat()
    +run_attempt()
    +publish_report()
  }
  class EvaluationAdapter {
    <<interface>>
    +evaluate(cases, context) CaseResult
  }
  class PromptfooAdapter {
    +run_allowlisted_subprocess()
    +normalize_output()
  }
  class RagasAdapter {
    +evaluate_retrieval_and_answers()
    +normalize_output()
  }
  class ProviderAdapter {
    <<interface>>
    +generate(request, budget) ProviderResult
  }
  class BudgetLimiter {
    +acquire_call_slot()
    +reserve_tokens_and_cost()
  }
  class GatePolicy {
    +check_compatibility()
    +compare_paired_metrics()
  }
  class ArtifactStore {
    +put_immutable()
    +read_verified()
  }
  class TelemetryExporter {
    +emit_redacted_event()
  }
  JobService --> JobRequest
  JobService --> JobRepository
  Dispatcher --> JobRepository
  Dispatcher --> EvaluationWorker
  EvaluationWorker --> EvaluationAdapter
  EvaluationAdapter <|.. PromptfooAdapter
  EvaluationAdapter <|.. RagasAdapter
  EvaluationAdapter --> ProviderAdapter
  ProviderAdapter --> BudgetLimiter
  EvaluationWorker --> ArtifactStore
  EvaluationWorker --> GatePolicy
  EvaluationWorker --> TelemetryExporter
```

Ports/adapters isolate third-party output formats and subprocess lifecycle from domain decisions. Repository + transactional outbox make admission atomic. Strategy selects versioned metric implementations and gate policies. Dependency injection supplies provider clients, clocks and stores for failure tests; no dependency injection framework beyond FastAPI and constructors is needed. AsyncIO `TaskGroup`, bounded queues and semaphores coordinate cooperative work; subprocesses isolate blocking or incompatible evaluator engines. Cancellation must terminate subprocess groups as well as coroutines.

```mermaid
stateDiagram-v2
  [*] --> QUEUED: accepted transaction
  QUEUED --> DISPATCHING: capacity + attempt reserved
  QUEUED --> CANCELLED: cancellation wins
  QUEUED --> FAILED: job deadline elapsed
  DISPATCHING --> RUNNING: worker fenced claim
  DISPATCHING --> RETRY_WAIT: recoverable launch failure
  DISPATCHING --> FAILED: deadline or attempts exhausted
  DISPATCHING --> CANCEL_REQUESTED: cancel
  RUNNING --> SUCCEEDED: complete report + gate committed
  RUNNING --> RETRY_WAIT: transient execution failure
  RUNNING --> FAILED: nonretryable or budget/deadline exhausted
  RUNNING --> CANCEL_REQUESTED: cancel
  RETRY_WAIT --> QUEUED: retry time reached
  RETRY_WAIT --> CANCELLED: cancel
  RETRY_WAIT --> FAILED: deadline or attempts exhausted
  CANCEL_REQUESTED --> CANCELLED: fence revoked and task stopped or lease expires
  SUCCEEDED --> [*]
  FAILED --> [*]
  CANCELLED --> [*]
```

No terminal state transitions back. To rerun, submit a new job with a new idempotency key. Job retries increment the attempt and never replace completed evidence. Attempt states are `RESERVED`, `ACTIVE`, `COMPLETED`, `ABORTED`; attempt state and job state are separate. Cancellation/expiry revokes the active fence before a replacement attempt is permitted.

## Data model

| Record | Identity / relationship | Mutable fields and constraints |
|---|---|---|
| Project | UUID, token mapping | quotas and retention under audit |
| DatasetVersion / ConfigVersion | project + kind + digest | immutable canonical bytes and schema version |
| Job | project + UUID; dataset/config FKs | state, timestamps, current attempt, deadline; immutable request and baseline |
| Attempt | project + job + attempt number | task ARN, random fence, heartbeat, lease, status; one active attempt |
| Outbox | UUID + job + event type | dispatch lease and delivery time; replay safe |
| Report | project + job unique | immutable artifact locator, hash and schema version |
| Gate | stored in report transaction | verdict, reason codes, policy digest and metric decisions |
| Provider reservation | project/provider/account key | slots, tokens, estimated spend and expiry; shared across tasks |
| AuditEvent | append-only ID | actor, action, resource and outcome; no raw prompt |

The [SQL scaffold](infra/postgres/001_scaffold.sql) supplies core metadata tables and constraints for local exploration; production migrations still need row-level security policies, quota reservations, audit tables, partition/retention handling and migration tests. All cross-resource references must include project. A baseline FK is additionally checked for `SUCCEEDED` and compatible evidence in application logic.

Pydantic v2 implementation rules: request models forbid extras, validate SHA-256 and UUID shapes, use timezone-aware UTC timestamps, reject non-finite numbers, and validate cross-field invariants. Decimal USD values serialize as decimal strings. Frozen models do not make nested data immutable; canonical bytes and digest validation provide persisted immutability. Generated FastAPI OpenAPI must be checked against the [contract](contracts/openapi.json); validation failures map to the shared problem envelope rather than FastAPI's default error shape.
