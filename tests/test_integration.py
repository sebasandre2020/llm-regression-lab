import asyncio
import json
from uuid import UUID, uuid4

import pytest

from conftest import OTHER_TOKEN, READ_TOKEN, registered_job
from test_contracts import assert_schema

from llm_regression_lab.artifacts import canonical_bytes, digest_bytes
from llm_regression_lab.database import migrate
from llm_regression_lab.local_profile import config_for
from llm_regression_lab.worker import FakeProvider, LocalWorker

pytestmark = pytest.mark.integration


async def test_registration_content_identity_and_read(lab, dataset):
    client, _, _ = lab
    first = await client.post("/v1/dataset-versions", json=dataset)
    assert first.status_code == 201
    assert_schema("Version", first.json())
    second = await client.post(
        "/v1/dataset-versions", content=json.dumps(dataset, indent=4), headers={"Content-Type": "application/json"}
    )
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["version_id"] == digest_bytes(canonical_bytes(dataset))
    result = await client.get(first.headers["location"])
    assert result.status_code == 200
    assert_schema("VersionDocument", result.json())
    assert result.json()["document"] == dataset


async def test_fake_baseline_candidate_and_gate(lab, dataset):
    client, _, settings = lab
    accepted, _ = await registered_job(client, dataset)
    assert accepted.status_code == 202
    assert_schema("Job", accepted.json())
    location = accepted.headers["location"]
    assert (await client.get(location + "/report")).status_code == 409
    async with LocalWorker(settings) as worker:
        assert await worker.run_once()
        assert not await worker.run_once()
        report = await client.get(location + "/report")
        assert report.status_code == 200, report.text
        assert_schema("Report", report.json())
        assert report.json()["metrics"][0]["candidate"] == 1.0
        assert report.json()["gate"]["reasons"] == ["BASELINE_REQUIRED"]
        candidate, _ = await registered_job(client, dataset, "fake:wrong", accepted.json()["job_id"])
        assert candidate.status_code == 202
        await worker.run_once()
    report = (await client.get(candidate.headers["location"] + "/report")).json()
    assert_schema("Report", report)
    assert report["metrics"][0]["candidate"] == 0.0
    assert report["metrics"][0]["delta"] == -1.0
    assert report["gate"]["verdict"] == "INCONCLUSIVE"
    assert report["manifest"]["execution_profile"] == "local-fake-v1"
    gate = (await client.get(candidate.headers["location"] + "/gate")).json()
    assert_schema("Gate", gate)
    assert gate == report["gate"]
    digest = report.pop("artifact_digest")
    assert digest == digest_bytes(canonical_bytes(report))


async def test_provider_failure_is_not_a_regression(lab, dataset):
    client, _, settings = lab
    response, _ = await registered_job(client, dataset, "fake:error")
    async with LocalWorker(settings) as worker:
        await worker.run_once()
    location = response.headers["location"]
    status = (await client.get(location)).json()
    assert status["state"] == "FAILED"
    assert status["error"]["code"] == "PROVIDER_TIMEOUT"
    gate = (await client.get(location + "/gate")).json()
    assert gate["verdict"] == "INCONCLUSIVE"
    assert gate["reasons"] == ["EXECUTION_FAILED"]
    assert (await client.get(location + "/report")).json()["code"] == "REPORT_UNAVAILABLE"


async def test_concurrent_idempotency_and_conflict(lab, dataset):
    client, app, settings = lab
    key = uuid4().hex
    _, body = await registered_job(client, dataset)
    replies = await asyncio.gather(
        *(client.post("/v1/jobs", json=body, headers={"Idempotency-Key": key}) for _ in range(8))
    )
    assert sorted(reply.status_code for reply in replies) == [200] * 7 + [202]
    assert len({reply.json()["job_id"] for reply in replies}) == 1
    async with app.state.service.pool.acquire() as db:
        assert (
            await db.fetchval(
                "SELECT count(*) FROM outbox WHERE project_id=$1", UUID(next(iter(settings.tokens.values())).project_id)
            )
            == 2
        )
    body["source_revision"] = "b" * 40
    conflict = await client.post("/v1/jobs", json=body, headers={"Idempotency-Key": key})
    assert conflict.status_code == 409
    assert_schema("Problem", conflict.json())
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


async def test_project_isolation_and_scopes(lab, dataset):
    client, _, _ = lab
    response, body = await registered_job(client, dataset)
    for suffix in ("", "/gate", "/report"):
        assert (
            await client.get(response.headers["location"] + suffix, headers={"Authorization": f"Bearer {OTHER_TOKEN}"})
        ).status_code == 404
    assert (
        await client.get(
            "/v1/dataset-versions/" + body["dataset_version"], headers={"Authorization": f"Bearer {OTHER_TOKEN}"}
        )
    ).status_code == 404
    assert (
        await client.post(response.headers["location"] + "/cancel", headers={"Authorization": f"Bearer {READ_TOKEN}"})
    ).status_code == 403
    assert (
        await client.get(response.headers["location"], headers={"Authorization": "Bearer invalid"})
    ).status_code == 401
    assert (await client.get(response.headers["location"], headers={"Authorization": ""})).headers[
        "www-authenticate"
    ] == "Bearer"


@pytest.mark.parametrize(
    "payload,code,status",
    [
        ('{"name":"x","name":"y"}', "INVALID_JSON", 400),
        ('{"value":NaN}', "INVALID_JSON", 400),
        ('{"value":Infinity}', "INVALID_JSON", 400),
        ('{"value":"\\ud800"}', "INVALID_JSON", 400),
        ("{}", "VALIDATION_ERROR", 422),
        ('{"name":', "INVALID_JSON", 400),
    ],
)
async def test_invalid_json_envelope(lab, payload, code, status):
    client, _, _ = lab
    response = await client.post("/v1/dataset-versions", content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert_schema("Problem", response.json())


async def test_body_limit_and_config_allowlist(lab):
    client, _, _ = lab
    response = await client.post("/v1/dataset-versions", content=b"x" * 1048577)
    assert response.status_code == 413
    config = config_for()
    config["target"] = "https://untrusted.invalid"
    assert (await client.post("/v1/config-versions", json=config)).status_code == 422
    config = config_for()
    config["gate_policy"]["quality_max_drop"] = "1.000000"
    assert (await client.post("/v1/config-versions", json=config)).status_code == 422


async def test_queued_cancellation_and_idempotency(lab, dataset):
    client, _, settings = lab
    job, _ = await registered_job(client, dataset)
    location = job.headers["location"]
    assert (await client.post(location + "/cancel", json={})).status_code == 422
    for _ in range(2):
        cancelled = await client.post(location + "/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "CANCELLED"
    assert (await client.get(location + "/gate")).json()["reasons"] == ["CANCELLED"]
    async with LocalWorker(settings) as worker:
        assert not await worker.run_once()


async def test_running_cancellation_and_worker_singleton(lab, dataset):
    client, _, settings = lab
    job, _ = await registered_job(client, dataset)
    location = job.headers["location"]
    async with LocalWorker(settings, FakeProvider(delay=0.3)) as worker:
        with pytest.raises(RuntimeError, match="Another local worker"):
            async with LocalWorker(settings):
                pass
        task = asyncio.create_task(worker.run_once())
        for _ in range(100):
            if (await client.get(location)).json()["state"] == "RUNNING":
                break
            await asyncio.sleep(0.01)
        cancelled = await client.post(location + "/cancel")
        assert cancelled.status_code == 202
        await task
    assert (await client.get(location)).json()["state"] == "CANCELLED"
    assert (await client.get(location + "/report")).status_code == 409


async def test_interrupted_attempt_and_deadline_recovery(lab, dataset):
    client, app, settings = lab
    job, _ = await registered_job(client, dataset)
    async with LocalWorker(settings) as worker:
        assert await worker.claim()
    async with LocalWorker(settings) as worker:
        assert not await worker.run_once()
    status = (await client.get(job.headers["location"])).json()
    assert status["state"] == "FAILED"
    assert status["error"]["code"] == "ENGINE_CRASH"
    late, _ = await registered_job(client, dataset)
    async with app.state.service.pool.acquire() as db:
        await db.execute(
            "UPDATE jobs SET created_at=now()-interval '2 minutes',deadline_at=now()-interval '1 minute' WHERE job_id=$1",
            UUID(late.json()["job_id"]),
        )
    async with LocalWorker(settings) as worker:
        await worker.run_once()
    assert (await client.get(late.headers["location"])).json()["error"]["code"] == "DEADLINE_EXCEEDED"


async def test_artifact_integrity_failure_and_missing_version(lab, dataset):
    client, app, settings = lab
    job, body = await registered_job(client, dataset)
    project = next(iter(settings.tokens.values())).project_id
    path = app.state.service.artifacts.path(project, "dataset", body["dataset_version"])
    path.write_bytes(b"tampered")
    async with LocalWorker(settings) as worker:
        await worker.run_once()
    assert (await client.get(job.headers["location"])).json()["error"]["code"] == "ARTIFACT_INTEGRITY"
    path.unlink()
    assert (await client.get("/v1/dataset-versions/" + body["dataset_version"])).status_code == 410


async def test_incompatible_baseline_and_migration_replay(lab, dataset):
    client, _, settings = lab
    first, _ = await registered_job(client, dataset)
    async with LocalWorker(settings) as worker:
        await worker.run_once()
    changed = config_for()
    changed["seed"] = 43
    rejected, _ = await registered_job(client, dataset, baseline=first.json()["job_id"], config=changed)
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "BASELINE_INCOMPATIBLE"
    await migrate(settings)
    assert (await client.get("/health/ready")).status_code == 200
    assert (await client.get(first.headers["location"] + "/report")).status_code == 200
    assert (await client.post(first.headers["location"] + "/cancel")).status_code == 409


async def test_local_queue_quota_preserves_idempotent_replay(lab, dataset):
    client, app, settings = lab
    key = uuid4().hex
    first, body = await registered_job(client, dataset, key=key)
    for _ in range(99):
        response = await client.post("/v1/jobs", json=body, headers={"Idempotency-Key": uuid4().hex})
        assert response.status_code == 202
    rejected = await client.post("/v1/jobs", json=body, headers={"Idempotency-Key": uuid4().hex})
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "QUOTA_EXCEEDED"
    replay = await client.post("/v1/jobs", json=body, headers={"Idempotency-Key": key})
    assert replay.status_code == 200 and replay.json()["job_id"] == first.json()["job_id"]
    async with app.state.service.pool.acquire() as db:
        assert (
            await db.fetchval(
                "SELECT count(*) FROM outbox WHERE project_id=$1", UUID(next(iter(settings.tokens.values())).project_id)
            )
            == 100
        )


async def test_dependency_error_is_sanitized(lab, monkeypatch):
    client, app, _ = lab

    async def unavailable(*args):
        raise OSError("sensitive connection details must never appear")

    monkeypatch.setattr(app.state.service, "gate", unavailable)
    response = await client.get(f"/v1/jobs/{uuid4()}/gate")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "sensitive" not in response.text
    assert_schema("Problem", response.json())
