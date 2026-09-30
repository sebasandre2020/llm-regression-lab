"""A deliberately synthetic registry. These identifiers cannot denote real models."""

from .artifacts import canonical_bytes, digest_bytes
from .errors import ProblemError

LOCAL_DIGEST = digest_bytes(b"llm-regression-lab-local-fake-v1")
LOCAL_POLICY = {
    "version": "paired-v1",
    "min_cases": 100,
    "min_repetitions": 3,
    "quality_max_drop": "0.020000",
    "latency_max_increase": "0.200000",
    "latency_max_ms": 5000,
    "cost_max_increase": "0.100000",
}


def config_for(target="fake:reference"):
    return {
        "schema_version": "1.0",
        "target": target,
        "application_revision": "local-demo-v1",
        "changed_dimensions": ["code"],
        "prompt_digest": LOCAL_DIGEST,
        "model_revision": "fake-v1",
        "retrieval_corpus_digest": None,
        "engine_image_digest": LOCAL_DIGEST,
        "evaluator_versions": {"promptfoo": "not-installed-local-v1", "ragas": "not-installed-local-v1"},
        "judge_revision": "none-local-v1",
        "rubric_digest": LOCAL_DIGEST,
        "metrics": ["assertion_pass_rate"],
        "metric_policy_version": "macro-v1",
        "pricing_snapshot_digest": LOCAL_DIGEST,
        "execution_profile": "local-fake-v1",
        "repetitions": 3,
        "seed": 42,
        "concurrency": 4,
        "max_output_tokens": 1024,
        "max_total_tokens": 500000,
        "max_cost_usd": "1.000000",
        "gate_policy": dict(LOCAL_POLICY),
    }


def approve_local_config(config):
    from .minimax import config_for_minimax

    real = config["target"] == "minimax:MiniMax-M3"
    expected = config_for_minimax() if real else config_for()
    controlled = [
        "prompt_digest",
        "model_revision",
        "retrieval_corpus_digest",
        "engine_image_digest",
        "evaluator_versions",
        "judge_revision",
        "rubric_digest",
        "metrics",
        "metric_policy_version",
        "pricing_snapshot_digest",
        "execution_profile",
        "gate_policy",
    ]
    if config["target"] not in {"fake:reference", "fake:wrong", "fake:error", "minimax:MiniMax-M3"} or any(
        config[key] != expected[key] for key in controlled
    ):
        raise ProblemError(
            422, "VALIDATION_ERROR", "Only the documented fake and MiniMax registries and fixed policy are supported."
        )


def fingerprint(dataset, config):
    keys = [
        "engine_image_digest",
        "evaluator_versions",
        "judge_revision",
        "rubric_digest",
        "metrics",
        "metric_policy_version",
        "pricing_snapshot_digest",
        "execution_profile",
        "repetitions",
        "seed",
        "concurrency",
    ]
    return digest_bytes(canonical_bytes({"dataset": dataset, **{key: config[key] for key in keys}}))


def inconclusive_gate(job_id, config, decided_at, reason):
    return {
        "job_id": str(job_id),
        "verdict": "INCONCLUSIVE",
        "reasons": [reason],
        "policy_version": config["gate_policy"]["version"],
        "policy_digest": digest_bytes(canonical_bytes(config["gate_policy"])),
        "decided_at": decided_at,
        "decisions": [
            {
                "metric": "release_eligibility",
                "outcome": "INCONCLUSIVE",
                "threshold": "real calibrated evaluators and comparable complete evidence required",
                "evidence": "Local evaluation is diagnostic only; calibrated release gates are not implemented.",
            }
        ],
    }
