import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from pydantic import ValidationError

from llm_regression_lab.api import create_app
from llm_regression_lab.artifacts import FileArtifacts, canonical_bytes, digest_bytes
from llm_regression_lab.errors import IntegrityError
from llm_regression_lab.local_profile import config_for
from llm_regression_lab.models import Dataset, EvaluationConfig, JobRequest
from llm_regression_lab.settings import Settings
from llm_regression_lab.worker import FakeProvider, observations

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
SCHEMAS = json.loads((ROOT / "contracts/schemas.json").read_text(encoding="utf-8"))


def assert_schema(name, value):
    Draft202012Validator({**SCHEMAS, "$ref": f"#/$defs/{name}"}, format_checker=FormatChecker()).validate(value)


def test_generated_openapi_routes_scopes_and_inputs(tmp_path):
    app = create_app(Settings("unused", tmp_path, {}))
    generated = app.openapi()
    validate(generated)
    assert generated["openapi"] == "3.1.0"
    assert generated["paths"].keys() == CONTRACT["paths"].keys()
    for path, methods in CONTRACT["paths"].items():
        assert generated["paths"][path].keys() == methods.keys()
        for verb, operation in methods.items():
            actual = generated["paths"][path][verb]
            assert actual["operationId"] == operation["operationId"]
            if path.startswith("/v1"):
                assert actual["x-required-scope"] == operation["x-required-scope"]
                assert actual["security"] == operation["security"]
            if "requestBody" in operation:
                assert actual["requestBody"] == operation["requestBody"]
            expected_statuses = set(operation["responses"])
            assert expected_statuses <= set(actual["responses"])
            assert actual["responses"]["default"]["content"] == operation["responses"]["default"]["content"]
            if "422" in actual["responses"]:
                assert "application/problem+json" in actual["responses"]["422"]["content"]

    def normalize(value, components):
        if isinstance(value, list):
            return [normalize(item, components) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return normalize(components[value["$ref"].split("/")[-1]], components)
        return {
            key: sorted(item) if key == "required" else normalize(item, components)
            for key, item in value.items()
            if key != "title" and not (key == "minItems" and item == 0)
        }

    for name in (
        "Dataset",
        "EvaluationConfig",
        "JobRequest",
        "Version",
        "Job",
        "Gate",
        "Manifest",
        "Cost",
        "Health",
        "Problem",
    ):
        expected = (
            CONTRACT["components"]["schemas"][name]
            if name != "Cost"
            else CONTRACT["components"]["schemas"]["Report"]["properties"]["cost"]
        )
        assert normalize(generated["components"]["schemas"][name], generated["components"]["schemas"]) == normalize(
            expected, CONTRACT["components"]["schemas"]
        ), name


@pytest.mark.parametrize(
    "field,value",
    [
        ("concurrency", "4"),
        ("seed", True),
        ("metrics", ["assertion_pass_rate", "assertion_pass_rate"]),
        ("max_cost_usd", "0.000000"),
    ],
)
def test_strict_config_rejections(field, value):
    config = config_for()
    config[field] = value
    with pytest.raises(ValidationError):
        EvaluationConfig.model_validate(config)


def test_dataset_duplicate_ids_rejected(dataset):
    dataset["cases"].append(deepcopy(dataset["cases"][0]))
    with pytest.raises(ValidationError):
        Dataset.model_validate(dataset)


def test_invalid_baseline_uuid_rejected():
    body = json.loads((ROOT / "examples/job.json").read_text())
    body["baseline_job_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        JobRequest.model_validate(body)


def test_local_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("LAB_LOCAL_ONLY", raising=False)
    with pytest.raises(RuntimeError, match="LAB_LOCAL_ONLY"):
        Settings.from_env()


def test_canonical_immutable_artifacts(tmp_path):
    store = FileArtifacts(tmp_path)
    project = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    document = {"z": [2, 1], "á": "Lima", "a": {"z": 1, "a": 2}}
    digest, key = store.put(project, "dataset", document)
    assert digest == digest_bytes(canonical_bytes(document))
    assert store.put(project, "dataset", dict(reversed(list(document.items())))) == (digest, key)
    assert store.get(project, "dataset", digest) == document
    (tmp_path / key).write_bytes(b"tampered")
    with pytest.raises(IntegrityError):
        store.get(project, "dataset", digest)
    with pytest.raises(IntegrityError):
        store.put(project, "dataset", document)
    with pytest.raises(ValueError):
        store.path(project, "../escape", digest)


async def test_provider_calls_are_bounded(dataset):
    class CountingProvider(FakeProvider):
        active = 0
        peak = 0

        async def generate(self, case, target):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                return await super().generate(case, target)
            finally:
                self.active -= 1

    provider = CountingProvider(delay=0.001)
    config = config_for()
    config.update(concurrency=8, repetitions=10)
    results = await observations(dataset, config, provider)
    assert len(results) == 10
    assert 1 < provider.peak <= 4
    assert provider.active == 0
