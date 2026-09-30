import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

from llm_regression_lab.api import create_app
from llm_regression_lab.database import migrate
from llm_regression_lab.local_profile import config_for
from llm_regression_lab.settings import Identity, SCOPES, Settings

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "local-test-token-" + "a" * 32
OTHER_TOKEN = "local-test-token-" + "b" * 32
READ_TOKEN = "local-test-token-" + "c" * 32


@pytest.fixture
def database_url():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable local PostgreSQL admin connection")
    name = "lab_test_" + uuid4().hex
    parts = urlsplit(admin_url)
    url = urlunsplit(parts._replace(path="/" + name))

    async def create():
        db = await asyncpg.connect(admin_url)
        try:
            await db.execute(f'CREATE DATABASE "{name}"')
        finally:
            await db.close()

    async def drop():
        db = await asyncpg.connect(admin_url)
        try:
            await db.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        finally:
            await db.close()

    asyncio.run(create())
    try:
        yield url
    finally:
        asyncio.run(drop())


@pytest.fixture
def dataset():
    return json.loads((ROOT / "examples/dataset.json").read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def lab(database_url, tmp_path):
    project, other = str(uuid4()), str(uuid4())
    settings = Settings(
        database_url,
        tmp_path / "artifacts",
        {
            TOKEN: Identity(project, SCOPES),
            OTHER_TOKEN: Identity(other, SCOPES),
            READ_TOKEN: Identity(project, frozenset({"jobs:read"})),
        },
    )
    await migrate(settings)
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {TOKEN}"}
        ) as client,
    ):
        yield client, app, settings


async def registered_job(client, dataset, target="fake:reference", baseline=None, key=None, config=None):
    ds = await client.post("/v1/dataset-versions", json=dataset)
    assert ds.status_code in {200, 201}, ds.text
    cfg = await client.post("/v1/config-versions", json=config or config_for(target))
    assert cfg.status_code in {200, 201}, cfg.text
    body = {
        "schema_version": "1.0",
        "dataset_version": ds.json()["version_id"],
        "config_version": cfg.json()["version_id"],
        "baseline_job_id": baseline,
        "deadline_seconds": 900,
        "source_revision": "a" * 40,
    }
    return await client.post("/v1/jobs", json=body, headers={"Idempotency-Key": key or uuid4().hex}), body
