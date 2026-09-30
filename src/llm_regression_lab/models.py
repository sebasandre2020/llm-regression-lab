"""Strict boundary models. The published contract is tested independently."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Digest = Annotated[str, Field(min_length=1, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")]
Money = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[0-9]+\.[0-9]{6}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=128)]
Timestamp = Annotated[str, Field(min_length=1, max_length=40, json_schema_extra={"format": "date-time"})]
Identifier = Annotated[str, Field(min_length=1, max_length=36, json_schema_extra={"format": "uuid"})]
MetricName = Literal["assertion_pass_rate", "faithfulness", "context_recall"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Assertion(Model):
    type: Literal["contains", "equals"]
    value: Annotated[str, Field(min_length=1, max_length=8192)]


class Case(Model):
    case_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]
    input: Annotated[str, Field(min_length=1, max_length=16384)]
    reference: Annotated[str, Field(min_length=1, max_length=16384)]
    contexts: Annotated[list[Annotated[str, Field(min_length=1, max_length=16384)]], Field(max_length=20)]
    assertions: Annotated[list[Assertion], Field(max_length=20)]


class Dataset(Model):
    schema_version: Literal["1.0"]
    name: ShortText
    cases: Annotated[list[Case], Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def unique_cases(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        return self


class Policy(Model):
    version: Literal["paired-v1"]
    min_cases: Annotated[int, Field(ge=100, le=1000)]
    min_repetitions: Annotated[int, Field(ge=3, le=10)]
    quality_max_drop: Money
    latency_max_increase: Money
    latency_max_ms: Annotated[int, Field(ge=1, le=60000)]
    cost_max_increase: Money

    @field_validator("quality_max_drop", "latency_max_increase", "cost_max_increase")
    @classmethod
    def ratio(cls, value):
        if Decimal(value) > 1:
            raise ValueError("ratio must be in [0, 1]")
        return value


class EvaluatorVersions(Model):
    promptfoo: Annotated[str, Field(min_length=1, max_length=64)]
    ragas: Annotated[str, Field(min_length=1, max_length=64)]


class EvaluationConfig(Model):
    schema_version: Literal["1.0"]
    target: ShortText
    application_revision: ShortText
    changed_dimensions: Annotated[
        list[Literal["prompt", "model", "retrieval", "code"]],
        Field(max_length=4, json_schema_extra={"uniqueItems": True}),
    ]
    prompt_digest: Digest
    model_revision: ShortText
    retrieval_corpus_digest: Digest | None
    engine_image_digest: Digest
    evaluator_versions: EvaluatorVersions
    judge_revision: ShortText
    rubric_digest: Digest
    metrics: Annotated[list[MetricName], Field(min_length=1, max_length=3, json_schema_extra={"uniqueItems": True})]
    metric_policy_version: Literal["macro-v1"]
    pricing_snapshot_digest: Digest
    execution_profile: ShortText
    repetitions: Annotated[int, Field(ge=1, le=10)]
    seed: Annotated[int, Field(ge=0, le=2147483647)]
    concurrency: Annotated[int, Field(ge=1, le=8)]
    max_output_tokens: Annotated[int, Field(ge=1, le=8192)]
    max_total_tokens: Annotated[int, Field(ge=1, le=10000000)]
    max_cost_usd: Money
    gate_policy: Policy

    @field_validator("metrics", "changed_dimensions")
    @classmethod
    def unique_values(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("values must be unique")
        return values

    @field_validator("max_cost_usd")
    @classmethod
    def positive_budget(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("budget must be positive")
        return value


class JobRequest(Model):
    schema_version: Literal["1.0"]
    dataset_version: Digest
    config_version: Digest
    baseline_job_id: Identifier | None
    deadline_seconds: Annotated[int, Field(ge=60, le=3600)]
    source_revision: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[0-9a-f]{40}$")]

    @field_validator("baseline_job_id")
    @classmethod
    def valid_uuid(cls, value):
        if value is not None:
            return str(UUID(value))
        return value


class Version(Model):
    version_id: Digest
    kind: Literal["dataset", "config"]
    schema_version: Literal["1.0"]
    created_at: Timestamp


class VersionDocument(Version):
    document: Dataset | EvaluationConfig


class ExecutionError(Model):
    code: Literal[
        "PROVIDER_TIMEOUT",
        "PROVIDER_RATE_LIMIT",
        "PROVIDER_AUTH",
        "ENGINE_CRASH",
        "INVALID_ENGINE_OUTPUT",
        "ARTIFACT_INTEGRITY",
        "DISPATCH_FAILED",
        "LEASE_EXPIRED",
        "DEADLINE_EXCEEDED",
        "BUDGET_EXCEEDED",
        "CANCELLED",
    ]
    retryable: bool
    message: Annotated[str, Field(min_length=1, max_length=512)]


class Links(Model):
    self: Annotated[str, Field(min_length=1, max_length=256)]
    report: Annotated[str, Field(min_length=1, max_length=256)]
    gate: Annotated[str, Field(min_length=1, max_length=256)]


class Job(Model):
    job_id: Identifier
    request: JobRequest
    state: Literal[
        "QUEUED", "DISPATCHING", "RUNNING", "RETRY_WAIT", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED"
    ]
    attempt: Annotated[int, Field(ge=0, le=3)]
    created_at: Timestamp
    updated_at: Timestamp
    deadline_at: Timestamp
    error: ExecutionError | None
    links: Links


class MetricDecision(Model):
    metric: ShortText
    outcome: Literal["PASS", "REGRESSION", "INCONCLUSIVE"]
    threshold: Annotated[str, Field(min_length=1, max_length=256)]
    evidence: Annotated[str, Field(min_length=1, max_length=1024)]


class Gate(Model):
    job_id: Identifier
    verdict: Literal["PASS", "REGRESSION", "INCONCLUSIVE"]
    reasons: Annotated[
        list[
            Literal[
                "WITHIN_LIMITS",
                "QUALITY_REGRESSION",
                "LATENCY_REGRESSION",
                "COST_REGRESSION",
                "EXECUTION_FAILED",
                "CANCELLED",
                "BASELINE_REQUIRED",
                "INCOMPATIBLE_BASELINE",
                "INSUFFICIENT_EVIDENCE",
                "MISSING_METRIC",
                "UNKNOWN_COST",
            ]
        ],
        Field(min_length=1, max_length=12, json_schema_extra={"uniqueItems": True}),
    ]
    policy_version: Literal["paired-v1"]
    policy_digest: Digest
    decided_at: Timestamp
    decisions: Annotated[list[MetricDecision], Field(max_length=20)]


class ConfidenceInterval(Model):
    low: float
    high: float
    level: Literal[0.95]


class Metric(Model):
    name: ShortText
    unit: Literal["ratio", "ms", "usd"]
    direction: Literal["higher_is_better", "lower_is_better"]
    candidate: float | Money | None
    baseline: float | Money | None
    delta: float | Annotated[str, Field(min_length=1, max_length=33, pattern=r"^-?[0-9]+\.[0-9]{6}$")] | None
    confidence_interval: ConfidenceInterval | None

    @model_validator(mode="after")
    def unit_types(self):
        for value in (self.candidate, self.baseline, self.delta):
            if value is not None and (isinstance(value, str) != (self.unit == "usd")):
                raise ValueError("USD values must be decimal strings; other units must be numeric")
        if self.unit == "usd" and self.confidence_interval is not None:
            raise ValueError("USD confidence intervals are not supported")
        return self


class Manifest(Model):
    engine_image_digest: Digest
    evaluator_versions: EvaluatorVersions
    application_revision: ShortText
    model_revision: ShortText
    observed_provider_revision: ShortText | None
    judge_revision: ShortText
    rubric_digest: Digest
    metric_policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    pricing_snapshot_digest: Digest
    execution_profile: ShortText
    seed: Annotated[int, Field(ge=0, le=2147483647)]
    repetitions: Annotated[int, Field(ge=1, le=10)]
    comparison_fingerprint: Digest


class Coverage(Model):
    expected: Annotated[int, Field(ge=1, le=1000000)]
    valid: Annotated[int, Field(ge=0, le=1000000)]


class Cost(Model):
    estimated_usd: Money
    input_tokens: Annotated[int, Field(ge=0, le=10000000)]
    output_tokens: Annotated[int, Field(ge=0, le=10000000)]
    usage_complete: bool


class Report(Model):
    schema_version: Literal["1.0"]
    job_id: Identifier
    dataset_version: Digest
    config_version: Digest
    baseline_job_id: Identifier | None
    completed_at: Timestamp
    manifest: Manifest
    coverage: Coverage
    metrics: Annotated[list[Metric], Field(min_length=1, max_length=20)]
    cost: Cost
    gate: Gate
    artifact_digest: Digest


class Problem(Model):
    type: Annotated[str, Field(min_length=1, max_length=256, pattern=r"^urn:llm-regression-lab:error:[A-Z_]+$")]
    title: Annotated[str, Field(min_length=1, max_length=256)]
    status: Annotated[int, Field(ge=400, le=599)]
    code: Literal[
        "INVALID_JSON",
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "NOT_FOUND",
        "IDEMPOTENCY_CONFLICT",
        "INVALID_STATE",
        "BASELINE_INCOMPATIBLE",
        "REPORT_NOT_READY",
        "REPORT_UNAVAILABLE",
        "ARTIFACT_EXPIRED",
        "PAYLOAD_TOO_LARGE",
        "VALIDATION_ERROR",
        "QUOTA_EXCEEDED",
        "INTERNAL_ERROR",
        "DEPENDENCY_UNAVAILABLE",
    ]
    detail: Annotated[str, Field(min_length=1, max_length=1024)]
    request_id: ShortText
    retryable: bool


class Health(Model):
    status: Literal["ok", "unavailable"]
