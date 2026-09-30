"""Generate reviewable Phase 2 contracts and synthetic examples; no service runtime."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties) if required is None else required,
    }


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


def text(maximum=256, **kwargs):
    return {"type": "string", "minLength": 1, "maxLength": maximum, **kwargs}


def integer(minimum=0, maximum=1_000_000):
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def array(items, minimum=0, maximum=1000):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def enum(*values):
    return {"type": "string", "enum": list(values)}


DIGEST = text(71, pattern=r"^sha256:[0-9a-f]{64}$")
UUID = text(36, format="uuid")
DATE = text(40, format="date-time")
MONEY = text(32, pattern=r"^[0-9]+\.[0-9]{6}$")
SIGNED_MONEY = text(33, pattern=r"^-?[0-9]+\.[0-9]{6}$")
NUMBER = {"type": "number"}
VERSION = {"const": "1.0", "type": "string"}
STATES = [
    "QUEUED",
    "DISPATCHING",
    "RUNNING",
    "RETRY_WAIT",
    "CANCEL_REQUESTED",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
]
REASONS = [
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

SCHEMAS = {
    "Assertion": obj({"type": enum("contains", "equals"), "value": text(8192)}),
    "Case": obj(
        {
            "case_id": text(128, pattern=r"^[A-Za-z0-9_.-]+$"),
            "input": text(16384),
            "reference": text(16384),
            "contexts": array(text(16384), maximum=20),
            "assertions": array(ref("Assertion"), maximum=20),
        }
    ),
    "Dataset": obj(
        {
            "schema_version": VERSION,
            "name": text(128),
            "cases": array(ref("Case"), minimum=1),
        }
    ),
    "Policy": obj(
        {
            "version": {"const": "paired-v1", "type": "string"},
            "min_cases": integer(100, 1000),
            "min_repetitions": integer(3, 10),
            "quality_max_drop": MONEY,
            "latency_max_increase": MONEY,
            "latency_max_ms": integer(1, 60000),
            "cost_max_increase": MONEY,
        }
    ),
    "EvaluationConfig": obj(
        {
            "schema_version": VERSION,
            "target": text(128),
            "application_revision": text(128),
            "changed_dimensions": {
                **array(enum("prompt", "model", "retrieval", "code"), maximum=4),
                "uniqueItems": True,
            },
            "prompt_digest": DIGEST,
            "model_revision": text(128),
            "retrieval_corpus_digest": nullable(DIGEST),
            "engine_image_digest": DIGEST,
            "evaluator_versions": obj({"promptfoo": text(64), "ragas": text(64)}),
            "judge_revision": text(128),
            "rubric_digest": DIGEST,
            "metrics": {
                **array(enum("assertion_pass_rate", "faithfulness", "context_recall"), minimum=1, maximum=3),
                "uniqueItems": True,
            },
            "metric_policy_version": {"const": "macro-v1", "type": "string"},
            "pricing_snapshot_digest": DIGEST,
            "execution_profile": text(128),
            "repetitions": integer(1, 10),
            "seed": integer(0, 2147483647),
            "concurrency": integer(1, 8),
            "max_output_tokens": integer(1, 8192),
            "max_total_tokens": integer(1, 10_000_000),
            "max_cost_usd": MONEY,
            "gate_policy": ref("Policy"),
        }
    ),
    "Version": obj(
        {
            "version_id": DIGEST,
            "kind": enum("dataset", "config"),
            "schema_version": VERSION,
            "created_at": DATE,
        }
    ),
    "JobRequest": obj(
        {
            "schema_version": VERSION,
            "dataset_version": DIGEST,
            "config_version": DIGEST,
            "baseline_job_id": nullable(UUID),
            "deadline_seconds": integer(60, 3600),
            "source_revision": text(40, pattern=r"^[0-9a-f]{40}$"),
        }
    ),
    "ExecutionError": obj(
        {
            "code": enum(
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
            ),
            "retryable": {"type": "boolean"},
            "message": text(512),
        }
    ),
    "Job": obj(
        {
            "job_id": UUID,
            "request": ref("JobRequest"),
            "state": enum(*STATES),
            "attempt": integer(0, 3),
            "created_at": DATE,
            "updated_at": DATE,
            "deadline_at": DATE,
            "error": nullable(ref("ExecutionError")),
            "links": obj({"self": text(), "report": text(), "gate": text()}),
        }
    ),
    "MetricDecision": obj(
        {
            "metric": text(128),
            "outcome": enum("PASS", "REGRESSION", "INCONCLUSIVE"),
            "threshold": text(256),
            "evidence": text(1024),
        }
    ),
    "Gate": obj(
        {
            "job_id": UUID,
            "verdict": enum("PASS", "REGRESSION", "INCONCLUSIVE"),
            "reasons": {**array(enum(*REASONS), minimum=1, maximum=12), "uniqueItems": True},
            "policy_version": {"const": "paired-v1", "type": "string"},
            "policy_digest": DIGEST,
            "decided_at": DATE,
            "decisions": array(ref("MetricDecision"), maximum=20),
        }
    ),
    "Metric": obj(
        {
            "name": text(128),
            "unit": enum("ratio", "ms", "usd"),
            "direction": enum("higher_is_better", "lower_is_better"),
            "candidate": nullable({"anyOf": [NUMBER, MONEY]}),
            "baseline": nullable({"anyOf": [NUMBER, MONEY]}),
            "delta": nullable({"anyOf": [NUMBER, SIGNED_MONEY]}),
            "confidence_interval": nullable(obj({"low": NUMBER, "high": NUMBER, "level": {"const": 0.95}})),
        }
    ),
    "Manifest": obj(
        {
            "engine_image_digest": DIGEST,
            "evaluator_versions": obj({"promptfoo": text(64), "ragas": text(64)}),
            "application_revision": text(128),
            "model_revision": text(128),
            "observed_provider_revision": nullable(text(128)),
            "judge_revision": text(128),
            "rubric_digest": DIGEST,
            "metric_policy_version": text(64),
            "pricing_snapshot_digest": DIGEST,
            "execution_profile": text(128),
            "seed": integer(0, 2147483647),
            "repetitions": integer(1, 10),
            "comparison_fingerprint": DIGEST,
        }
    ),
    "Report": obj(
        {
            "schema_version": VERSION,
            "job_id": UUID,
            "dataset_version": DIGEST,
            "config_version": DIGEST,
            "baseline_job_id": nullable(UUID),
            "completed_at": DATE,
            "manifest": ref("Manifest"),
            "coverage": obj({"expected": integer(1), "valid": integer()}),
            "metrics": array(ref("Metric"), minimum=1, maximum=20),
            "cost": obj(
                {
                    "estimated_usd": MONEY,
                    "input_tokens": integer(0, 10000000),
                    "output_tokens": integer(0, 10000000),
                    "usage_complete": {"type": "boolean"},
                }
            ),
            "gate": ref("Gate"),
            "artifact_digest": DIGEST,
        }
    ),
    "Problem": obj(
        {
            "type": text(256, pattern=r"^urn:llm-regression-lab:error:[A-Z_]+$"),
            "title": text(256),
            "status": integer(400, 599),
            "code": enum(
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
            ),
            "detail": text(1024),
            "request_id": text(128),
            "retryable": {"type": "boolean"},
        }
    ),
    "Health": obj({"status": enum("ok", "unavailable")}),
}
SCHEMAS["VersionDocument"] = obj(
    {
        **SCHEMAS["Version"]["properties"],
        "document": {"oneOf": [ref("Dataset"), ref("EvaluationConfig")]},
    }
)
SCHEMAS["Metric"]["allOf"] = [
    {
        "if": {"properties": {"unit": {"const": "usd"}}},
        "then": {
            "properties": {
                "candidate": nullable(MONEY),
                "baseline": nullable(MONEY),
                "delta": nullable(SIGNED_MONEY),
                "confidence_interval": {"type": "null"},
            }
        },
        "else": {
            "properties": {"candidate": nullable(NUMBER), "baseline": nullable(NUMBER), "delta": nullable(NUMBER)}
        },
    }
]


def response(description, schema, problem=False):
    return {
        "description": description,
        "headers": {"X-Request-ID": {"schema": text(128), "description": "Server request identifier"}},
        "content": {"application/problem+json" if problem else "application/json": {"schema": ref(schema)}},
    }


def operation(name, scope, output, statuses=(200,), body=None, path=None, idempotency=False):
    result = {
        "operationId": name,
        "summary": f"PLANNED: {name}",
        "security": [{"bearerAuth": []}],
        "x-required-scope": scope,
        "responses": {str(s): response("Successful response", output) for s in statuses},
    }
    result["responses"]["default"] = response("Error; see error code and retryable fields", "Problem", True)
    if body:
        result["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(body)}}}
    if path:
        result["parameters"] = [
            {"name": path, "in": "path", "required": True, "schema": UUID if path == "job_id" else DIGEST}
        ]
    if idempotency:
        result.setdefault("parameters", []).append(
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": text(128, minLength=8, pattern=r"^[\x20-\x7e]+$"),
            }
        )
    if body or name == "cancelJob":
        for status in statuses:
            result["responses"][str(status)]["headers"]["Location"] = {
                "schema": text(),
                "description": "Relative resource URL",
            }
    return result


def build():
    paths = {}
    for kind, schema in [("dataset", "Dataset"), ("config", "EvaluationConfig")]:
        paths[f"/v1/{kind}-versions"] = {
            "post": operation(f"register{schema}", "versions:write", "Version", (200, 201), schema)
        }
        paths[f"/v1/{kind}-versions/{{version_id}}"] = {
            "get": operation(f"get{schema}", "versions:read", "VersionDocument", path="version_id")
        }
    paths["/v1/jobs"] = {
        "post": operation("submitJob", "jobs:write", "Job", (200, 202), "JobRequest", idempotency=True)
    }
    paths["/v1/jobs/{job_id}"] = {"get": operation("getJob", "jobs:read", "Job", path="job_id")}
    paths["/v1/jobs/{job_id}/cancel"] = {"post": operation("cancelJob", "jobs:write", "Job", (200, 202), path="job_id")}
    for resource in ["report", "gate"]:
        paths[f"/v1/jobs/{{job_id}}/{resource}"] = {
            "get": operation(f"get{resource.title()}", "reports:read", resource.title(), path="job_id")
        }
    for probe in ["live", "ready"]:
        item = operation(f"health{probe.title()}", "private-network", "Health")
        item["security"] = []
        if probe == "ready":
            item["responses"]["503"] = response("Not ready", "Health")
        paths[f"/health/{probe}"] = {"get": item}
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "LLM Regression Lab — proposed contract",
            "version": "1.0.0",
            "description": "Phase 2 blueprint. No running server is provided.",
        },
        "servers": [{"url": "https://eval.example.invalid", "description": "Placeholder only"}],
        "paths": paths,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
            "schemas": SCHEMAS,
        },
    }
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": SCHEMAS}
    write("contracts/schemas.json", schema)
    write("contracts/openapi.json", json.loads(json.dumps(spec).replace("#/$defs/", "#/components/schemas/")))
    examples()


def write(path, value):
    output = ROOT / path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def examples():
    digest = lambda c: "sha256:" + c * 64  # noqa: E731
    job_id = "11111111-1111-4111-8111-111111111111"
    baseline_id = "22222222-2222-4222-8222-222222222222"
    now = "2026-09-27T12:00:00Z"
    dataset = {
        "schema_version": "1.0",
        "name": "synthetic-shape-example",
        "cases": [
            {
                "case_id": "capital-peru",
                "input": "What is the capital of Peru?",
                "reference": "Lima",
                "contexts": ["Lima is the capital of Peru."],
                "assertions": [{"type": "contains", "value": "Lima"}],
            }
        ],
    }
    config = {
        "schema_version": "1.0",
        "target": "approved-demo-target",
        "application_revision": "synthetic-candidate",
        "changed_dimensions": ["prompt"],
        "prompt_digest": digest("a"),
        "model_revision": "registry-resolved-model-revision",
        "retrieval_corpus_digest": None,
        "engine_image_digest": digest("b"),
        "evaluator_versions": {"promptfoo": "illustrative-version", "ragas": "illustrative-version"},
        "judge_revision": "registry-resolved-judge-revision",
        "rubric_digest": digest("c"),
        "metrics": ["assertion_pass_rate", "faithfulness"],
        "metric_policy_version": "macro-v1",
        "pricing_snapshot_digest": digest("d"),
        "execution_profile": "replay-release-v1",
        "repetitions": 3,
        "seed": 42,
        "concurrency": 4,
        "max_output_tokens": 1024,
        "max_total_tokens": 500000,
        "max_cost_usd": "5.000000",
        "gate_policy": {
            "version": "paired-v1",
            "min_cases": 100,
            "min_repetitions": 3,
            "quality_max_drop": "0.020000",
            "latency_max_increase": "0.200000",
            "latency_max_ms": 5000,
            "cost_max_increase": "0.100000",
        },
    }
    request = {
        "schema_version": "1.0",
        "dataset_version": digest("1"),
        "config_version": digest("2"),
        "baseline_job_id": baseline_id,
        "deadline_seconds": 900,
        "source_revision": "a" * 40,
    }
    gate = {
        "job_id": job_id,
        "verdict": "INCONCLUSIVE",
        "reasons": ["INSUFFICIENT_EVIDENCE"],
        "policy_version": "paired-v1",
        "policy_digest": digest("9"),
        "decided_at": now,
        "decisions": [
            {
                "metric": "sample_size",
                "outcome": "INCONCLUSIVE",
                "threshold": "at least 100 distinct cases",
                "evidence": "Synthetic fixture contains one case; not a measured evaluation.",
            }
        ],
    }
    manifest_keys = [
        "engine_image_digest",
        "evaluator_versions",
        "application_revision",
        "model_revision",
        "judge_revision",
        "rubric_digest",
        "metric_policy_version",
        "pricing_snapshot_digest",
        "execution_profile",
        "seed",
        "repetitions",
    ]
    metrics = []
    for name, unit, direction, value in [
        ("assertion_pass_rate", "ratio", "higher_is_better", 1.0),
        ("faithfulness", "ratio", "higher_is_better", 1.0),
        ("latency_p95_ms", "ms", "lower_is_better", 200.0),
        ("cost_usd_per_case", "usd", "lower_is_better", 0.001),
    ]:
        metric_value = f"{value:.6f}" if unit == "usd" else value
        metrics.append(
            {
                "name": name,
                "unit": unit,
                "direction": direction,
                "candidate": metric_value,
                "baseline": metric_value,
                "delta": "0.000000" if unit == "usd" else 0.0,
                "confidence_interval": None,
            }
        )
    report = {
        "schema_version": "1.0",
        "job_id": job_id,
        "dataset_version": request["dataset_version"],
        "config_version": request["config_version"],
        "baseline_job_id": baseline_id,
        "completed_at": now,
        "manifest": {
            **{k: config[k] for k in manifest_keys},
            "observed_provider_revision": "synthetic-revision",
            "comparison_fingerprint": digest("e"),
        },
        "coverage": {"expected": 3, "valid": 3},
        "metrics": metrics,
        "cost": {"estimated_usd": "0.003000", "input_tokens": 30, "output_tokens": 6, "usage_complete": True},
        "gate": gate,
        "artifact_digest": digest("f"),
    }
    job = {
        "job_id": job_id,
        "request": request,
        "state": "SUCCEEDED",
        "attempt": 1,
        "created_at": "2026-09-27T11:59:00Z",
        "updated_at": now,
        "deadline_at": "2026-09-27T12:14:00Z",
        "error": None,
        "links": {
            "self": f"/v1/jobs/{job_id}",
            "report": f"/v1/jobs/{job_id}/report",
            "gate": f"/v1/jobs/{job_id}/gate",
        },
    }
    for name, data in [
        ("dataset", dataset),
        ("config", config),
        ("job", request),
        ("job-status", job),
        ("report", report),
        ("gate", gate),
    ]:
        write(f"examples/{name}.json", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    ROOT = parser.parse_args().output_dir.resolve()
    build()
