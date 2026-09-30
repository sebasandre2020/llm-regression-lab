"""Single local worker process. ECS dispatch, retries and distributed leases are deferred."""

import asyncio
import logging
import math
import time
from contextlib import suppress
from decimal import Decimal
from uuid import uuid4

import asyncpg

from .artifacts import FileArtifacts
from .database import WORKER_LOCK, check_schema, pool_for, timestamp
from .errors import ExecutionFailure, IntegrityError
from .local_profile import approve_local_config, fingerprint, inconclusive_gate
from .models import Report
from .minimax import MiniMaxProvider
from .settings import Settings

log = logging.getLogger(__name__)


class FakeProvider:
    """No network. Reference echo, known wrong answer, or explicit failure."""

    def __init__(self, delay=0):
        self.delay = delay

    async def generate(self, case, target):
        await asyncio.sleep(self.delay)
        if target == "fake:error":
            raise ExecutionFailure("PROVIDER_TIMEOUT")
        return case["reference"] if target == "fake:reference" else "[synthetic wrong answer]"


async def observations(dataset, config, provider):
    concurrency = min(config["concurrency"], 4)
    queue = asyncio.Queue(maxsize=concurrency * 2)
    results = []

    async def produce():
        for case in dataset["cases"]:
            for repetition in range(config["repetitions"]):
                await queue.put((case, repetition))
        for _ in range(concurrency):
            await queue.put(None)

    async def consume():
        while (item := await queue.get()) is not None:
            case, repetition = item
            start = time.perf_counter()
            answer = await provider.generate(case, config["target"])
            latency = (time.perf_counter() - start) * 1000
            passed = all(
                a["value"] in answer if a["type"] == "contains" else a["value"] == answer for a in case["assertions"]
            )
            results.append((case["case_id"], repetition, float(passed), latency))

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(produce())
            for _ in range(concurrency):
                group.create_task(consume())
    except ExceptionGroup as group:

        def execution_error(error):
            if isinstance(error, ExecutionFailure):
                return error
            if isinstance(error, BaseExceptionGroup):
                for child in error.exceptions:
                    if found := execution_error(child):
                        return found
            return None

        if found := execution_error(group):
            raise found from None
        raise
    return sorted(results)


class LocalWorker:
    def __init__(self, settings, provider=None):
        self.settings = settings
        self.artifacts = FileArtifacts(settings.artifact_root)
        self.provider = provider or FakeProvider()
        self.pool = None
        self.lock = None
        self.lost_lock = asyncio.Event()

    async def __aenter__(self):
        self.pool = await pool_for(self.settings)
        self.lock = await asyncpg.connect(self.settings.database_url)
        try:
            if not await check_schema(self.lock):
                raise RuntimeError("Apply local migrations before starting worker")
            if not await self.lock.fetchval("SELECT pg_try_advisory_lock($1)", WORKER_LOCK):
                raise RuntimeError("Another local worker holds the database lock")
            self.lock.add_termination_listener(lambda _: self.lost_lock.set())
            # Owning the singleton lock permits terminalizing interrupted local attempts.
            async with self.pool.acquire() as db, db.transaction():
                rows = await db.fetch(
                    "SELECT * FROM jobs WHERE state IN ('RUNNING','DISPATCHING','CANCEL_REQUESTED') FOR UPDATE"
                )
                for row in rows:
                    await self.fail(db, row, "CANCELLED" if row["state"] == "CANCEL_REQUESTED" else "ENGINE_CRASH")
            return self
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *_):
        if self.lock:
            await self.lock.close()
        if self.pool:
            await self.pool.close()

    async def fail(self, db, row, code):
        now = await db.fetchval("SELECT clock_timestamp()")
        cancelled = code == "CANCELLED"
        gate = inconclusive_gate(
            row["job_id"],
            {"gate_policy": row["gate_policy"]},
            timestamp(now),
            "CANCELLED" if cancelled else "EXECUTION_FAILED",
        )
        error = {
            "code": code,
            "retryable": False,
            "message": "Local evaluation cancelled."
            if cancelled
            else "Local evaluation failed; see the stable error code.",
        }
        await db.execute(
            "UPDATE jobs SET state=$3,error=$4,gate=$5,updated_at=$6 WHERE project_id=$1 AND job_id=$2",
            row["project_id"],
            row["job_id"],
            "CANCELLED" if cancelled else "FAILED",
            error,
            gate,
            now,
        )
        await db.execute(
            "UPDATE attempts SET state='ABORTED' WHERE project_id=$1 AND job_id=$2 AND state IN ('RESERVED','ACTIVE')",
            row["project_id"],
            row["job_id"],
        )
        await db.execute(
            "UPDATE outbox SET delivered_at=$3 WHERE project_id=$1 AND job_id=$2", row["project_id"], row["job_id"], now
        )

    async def claim(self):
        if self.lost_lock.is_set() or self.lock.is_closed():
            raise RuntimeError("Local worker lock was lost; restart worker")
        async with self.pool.acquire() as db, db.transaction():
            row = await db.fetchrow(
                "SELECT j.* FROM jobs j JOIN outbox o USING(project_id,job_id) WHERE j.state='QUEUED' AND o.delivered_at IS NULL ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1"
            )
            if row is None:
                return None
            if row["deadline_at"] <= await db.fetchval("SELECT clock_timestamp()"):
                await self.fail(db, row, "DEADLINE_EXCEEDED")
                return False
            fence = uuid4()
            await db.execute(
                "UPDATE jobs SET state='DISPATCHING',current_attempt=1,updated_at=clock_timestamp() WHERE project_id=$1 AND job_id=$2",
                row["project_id"],
                row["job_id"],
            )
            await db.execute(
                "INSERT INTO attempts(project_id,job_id,attempt_number,fence,launch_token,state,lease_expires_at) VALUES($1,$2,1,$3,$4,'ACTIVE',$5)",
                row["project_id"],
                row["job_id"],
                fence,
                str(uuid4()),
                row["deadline_at"],
            )
            await db.execute(
                "UPDATE outbox SET delivered_at=clock_timestamp() WHERE project_id=$1 AND job_id=$2",
                row["project_id"],
                row["job_id"],
            )
            updated = await db.fetchrow(
                "UPDATE jobs SET state='RUNNING',updated_at=clock_timestamp() WHERE project_id=$1 AND job_id=$2 RETURNING *",
                row["project_id"],
                row["job_id"],
            )
            return dict(updated), fence

    async def monitor(self, row):
        while True:
            if self.lost_lock.is_set():
                raise ExecutionFailure("LEASE_EXPIRED")
            async with self.pool.acquire() as db:
                current = await db.fetchrow(
                    "SELECT state,deadline_at,clock_timestamp() AS db_now FROM jobs WHERE project_id=$1 AND job_id=$2",
                    row["project_id"],
                    row["job_id"],
                )
            if current["state"] != "RUNNING":
                raise ExecutionFailure("CANCELLED" if current["state"] == "CANCEL_REQUESTED" else "LEASE_EXPIRED")
            if current["deadline_at"] <= current["db_now"]:
                raise ExecutionFailure("DEADLINE_EXCEEDED")
            await asyncio.sleep(0.05)

    async def evaluate(self, row):
        project = str(row["project_id"])
        config = await asyncio.to_thread(self.artifacts.get, project, "config", row["config_version"])
        dataset = await asyncio.to_thread(self.artifacts.get, project, "dataset", row["dataset_version"])
        approve_local_config(config)
        provider = MiniMaxProvider(config) if config["target"].startswith("minimax:") else self.provider
        results = await observations(dataset, config, provider)
        cost = provider.cost if isinstance(provider, MiniMaxProvider) else Decimal(0)
        baseline = {}
        if row["baseline_job_id"]:
            async with self.pool.acquire() as db:
                digest = await db.fetchval(
                    "SELECT artifact_digest FROM reports WHERE project_id=$1 AND job_id=$2",
                    row["project_id"],
                    row["baseline_job_id"],
                )
            previous = await asyncio.to_thread(self.artifacts.get, project, "report", digest)
            baseline = {item["name"]: item["candidate"] for item in previous["metrics"]}
        count = len(results)
        latencies = sorted(item[3] for item in results)
        metrics = []
        for name, unit, direction, value in [
            ("assertion_pass_rate", "ratio", "higher_is_better", sum(item[2] for item in results) / count),
            ("latency_p95_ms", "ms", "lower_is_better", latencies[math.ceil(count * 0.95) - 1]),
            ("cost_usd_per_case", "usd", "lower_is_better", f"{cost / count:.6f}"),
        ]:
            old = baseline.get(name)
            delta = (
                (f"{Decimal(value) - Decimal(old):.6f}" if unit == "usd" else value - old) if old is not None else None
            )
            metrics.append(
                {
                    "name": name,
                    "unit": unit,
                    "direction": direction,
                    "candidate": value,
                    "baseline": old,
                    "delta": delta,
                    "confidence_interval": None,
                }
            )
        async with self.pool.acquire() as db:
            now = timestamp(await db.fetchval("SELECT clock_timestamp()"))
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
        gate = inconclusive_gate(
            row["job_id"],
            config,
            now,
            "BASELINE_REQUIRED" if row["baseline_job_id"] is None else "INSUFFICIENT_EVIDENCE",
        )
        document = {
            "schema_version": "1.0",
            "job_id": str(row["job_id"]),
            "dataset_version": row["dataset_version"],
            "config_version": row["config_version"],
            "baseline_job_id": str(row["baseline_job_id"]) if row["baseline_job_id"] else None,
            "completed_at": now,
            "manifest": {
                **{key: config[key] for key in manifest_keys},
                "observed_provider_revision": provider.observed_revision
                if isinstance(provider, MiniMaxProvider)
                else "fake-v1",
                "comparison_fingerprint": fingerprint(row["dataset_version"], config),
            },
            "coverage": {"expected": len(dataset["cases"]) * config["repetitions"], "valid": count},
            "metrics": metrics,
            "cost": {
                "estimated_usd": f"{cost:.6f}",
                "input_tokens": getattr(provider, "input_tokens", 0),
                "output_tokens": getattr(provider, "output_tokens", 0),
                "usage_complete": True,
            },
            "gate": gate,
        }
        # Validate before storing; the digest is an external envelope field.
        Report.model_validate({**document, "artifact_digest": "sha256:" + "0" * 64})
        digest, key = await asyncio.to_thread(self.artifacts.put, project, "report", document)
        return document, digest, key

    async def run_once(self):
        claimed = await self.claim()
        if claimed is None:
            return False
        if claimed is False:
            return True
        row, fence = claimed
        evaluation = asyncio.create_task(self.evaluate(row))
        monitor = asyncio.create_task(self.monitor(row))
        failure = None
        result = None
        try:
            done, _ = await asyncio.wait({evaluation, monitor}, return_when=asyncio.FIRST_COMPLETED)
            if monitor in done:
                await monitor
            result = await evaluation
        except ExecutionFailure as error:
            failure = error.code
        except (IntegrityError, FileNotFoundError):
            failure = "ARTIFACT_INTEGRITY"
        except asyncio.CancelledError:
            failure = "ENGINE_CRASH"
            raise
        except Exception as error:
            log.error("Local worker failed: job_id=%s type=%s", row["job_id"], type(error).__name__)
            failure = "ENGINE_CRASH"
        finally:
            for task in (evaluation, monitor):
                task.cancel()
            await asyncio.gather(evaluation, monitor, return_exceptions=True)
            async with self.pool.acquire() as db, db.transaction():
                current = await db.fetchrow(
                    "SELECT j.* FROM jobs j JOIN attempts a ON a.project_id=j.project_id AND a.job_id=j.job_id AND a.attempt_number=j.current_attempt WHERE j.project_id=$1 AND j.job_id=$2 AND a.fence=$3 AND a.state='ACTIVE' AND j.state IN ('RUNNING','CANCEL_REQUESTED') FOR UPDATE OF j",
                    row["project_id"],
                    row["job_id"],
                    fence,
                )
                if current:
                    if current["state"] == "CANCEL_REQUESTED":
                        failure = "CANCELLED"
                    elif current["deadline_at"] <= await db.fetchval("SELECT clock_timestamp()"):
                        failure = "DEADLINE_EXCEEDED"
                    elif self.lost_lock.is_set():
                        failure = "LEASE_EXPIRED"
                    if failure or result is None:
                        await self.fail(db, current, failure or "ENGINE_CRASH")
                    else:
                        document, digest, key = result
                        await db.execute(
                            "INSERT INTO reports(project_id,job_id,attempt_number,artifact_digest,object_key,object_version_id,gate) VALUES($1,$2,1,$3,$4,$3,$5)",
                            row["project_id"],
                            row["job_id"],
                            digest,
                            key,
                            document["gate"],
                        )
                        await db.execute("UPDATE attempts SET state='COMPLETED' WHERE fence=$1", fence)
                        await db.execute(
                            "UPDATE jobs SET state='SUCCEEDED',gate=$3,updated_at=clock_timestamp() WHERE project_id=$1 AND job_id=$2",
                            row["project_id"],
                            row["job_id"],
                            document["gate"],
                        )
        return True


async def main():
    async with LocalWorker(Settings.from_env()) as worker:
        while True:
            if not await worker.run_once():
                await asyncio.sleep(0.25)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
