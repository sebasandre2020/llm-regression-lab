import asyncio
import hashlib
import json
from datetime import datetime
from uuid import UUID

import asyncpg

from .settings import ROOT, Settings

MIGRATION_LOCK = 73681941
WORKER_LOCK = 73681942
EXPECTED_MIGRATION = "002_local_runtime.sql"


async def configure_connection(connection):
    for typename in ("json", "jsonb"):
        await connection.set_type_codec(
            typename, schema="pg_catalog", encoder=json.dumps, decoder=json.loads, format="text"
        )


async def pool_for(settings):
    return await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=5, command_timeout=10, init=configure_connection
    )


async def migrate(settings):
    connection = await asyncpg.connect(settings.database_url, command_timeout=30)
    try:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", MIGRATION_LOCK)
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            for path in sorted((ROOT / "infra/postgres").glob("*.sql")):
                sql = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                previous = await connection.fetchval("SELECT checksum FROM schema_migrations WHERE name=$1", path.name)
                if previous:
                    if checksum != previous:
                        raise RuntimeError(f"Applied migration changed: {path.name}")
                    continue
                # Phase 2 Compose already applied 001 without a migration ledger.
                exists = await connection.fetchval("SELECT to_regclass('public.jobs') IS NOT NULL")
                if path.name == "001_scaffold.sql" and exists:
                    tables = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    if not {"projects", "versions", "jobs", "attempts", "outbox", "reports"} <= {
                        row["tablename"] for row in tables
                    }:
                        raise RuntimeError("Incomplete Phase 2 bootstrap; restore or repair before migration")
                else:
                    # One outer transaction owns the migration ledger and DDL.
                    sql = "\n".join(line for line in sql.splitlines() if line.strip() not in {"BEGIN;", "COMMIT;"})
                    await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)", path.name, checksum
                )
            for project in {identity.project_id for identity in settings.tokens.values()}:
                await connection.execute(
                    "INSERT INTO projects(project_id,name) VALUES($1,$2) ON CONFLICT DO NOTHING",
                    UUID(project),
                    "local-project",
                )
    finally:
        await connection.close()


async def check_schema(connection):
    try:
        return bool(
            await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1)", EXPECTED_MIGRATION
            )
        )
    except asyncpg.UndefinedTableError:
        return False


def timestamp(value: datetime):
    return value.isoformat().replace("+00:00", "Z")


def job_document(row):
    job_id = str(row["job_id"])
    return {
        "job_id": job_id,
        "request": row["request"],
        "state": row["state"],
        "attempt": row["current_attempt"],
        "created_at": timestamp(row["created_at"]),
        "updated_at": timestamp(row["updated_at"]),
        "deadline_at": timestamp(row["deadline_at"]),
        "error": row["error"],
        "links": {
            "self": f"/v1/jobs/{job_id}",
            "report": f"/v1/jobs/{job_id}/report",
            "gate": f"/v1/jobs/{job_id}/gate",
        },
    }


if __name__ == "__main__":
    asyncio.run(migrate(Settings.from_env()))
