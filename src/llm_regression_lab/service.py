import asyncio
from uuid import UUID, uuid4

from .artifacts import canonical_bytes, digest_bytes
from .database import job_document, timestamp
from .errors import ProblemError
from .local_profile import approve_local_config, fingerprint, inconclusive_gate

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class JobService:
    def __init__(self, pool, artifacts):
        self.pool, self.artifacts = pool, artifacts

    async def register(self, project, kind, document):
        if kind == "config":
            approve_local_config(document)
        digest, key = await asyncio.to_thread(self.artifacts.put, project, kind, document)
        async with self.pool.acquire() as db:
            row = await db.fetchrow(
                "INSERT INTO versions(project_id,kind,digest,schema_version,object_key,object_version_id) VALUES($1,$2,$3,'1.0',$4,$3) ON CONFLICT DO NOTHING RETURNING *",
                UUID(project),
                kind,
                digest,
                key,
            )
            created = row is not None
            if row is None:
                row = await db.fetchrow(
                    "SELECT * FROM versions WHERE project_id=$1 AND kind=$2 AND digest=$3", UUID(project), kind, digest
                )
        return self.version_document(row), created

    @staticmethod
    def version_document(row):
        return {
            "version_id": row["digest"],
            "kind": row["kind"],
            "schema_version": row["schema_version"],
            "created_at": timestamp(row["created_at"]),
        }

    async def version(self, project, kind, digest):
        async with self.pool.acquire() as db:
            row = await db.fetchrow(
                "SELECT * FROM versions WHERE project_id=$1 AND kind=$2 AND digest=$3", UUID(project), kind, digest
            )
        if row is None:
            raise ProblemError(404, "NOT_FOUND", "Version not found.")
        document = await self.read_artifact(project, kind, digest)
        return {**self.version_document(row), "document": document}

    async def read_artifact(self, project, kind, digest):
        try:
            return await asyncio.to_thread(self.artifacts.get, project, kind, digest)
        except FileNotFoundError:
            raise ProblemError(410, "ARTIFACT_EXPIRED", "Artifact bytes are unavailable.") from None

    async def submit(self, project, key, request):
        request_hash = digest_bytes(canonical_bytes(request))
        pid = UUID(project)
        async with self.pool.acquire() as db, db.transaction():
            # Local project lock serializes admission and enforces queued-job quota.
            if not await db.fetchrow("SELECT project_id FROM projects WHERE project_id=$1 FOR UPDATE", pid):
                raise ProblemError(404, "NOT_FOUND", "Project not provisioned; run the migration command.")
            previous = await db.fetchrow("SELECT * FROM jobs WHERE project_id=$1 AND idempotency_key=$2", pid, key)
            if previous:
                if previous["request_hash"] != request_hash:
                    raise ProblemError(409, "IDEMPOTENCY_CONFLICT", "Use a new key for a changed request.")
                return job_document(previous), False
            docs = {}
            for kind in ("dataset", "config"):
                digest = request[f"{kind}_version"]
                if not await db.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM versions WHERE project_id=$1 AND kind=$2 AND digest=$3)",
                    pid,
                    kind,
                    digest,
                ):
                    raise ProblemError(404, "NOT_FOUND", "Referenced version not found.")
                docs[kind] = await self.read_artifact(project, kind, digest)
            approve_local_config(docs["config"])
            if any(not case["assertions"] for case in docs["dataset"]["cases"]):
                raise ProblemError(
                    422, "VALIDATION_ERROR", "The local assertion metric requires assertions on every case."
                )
            baseline_id = request["baseline_job_id"]
            if baseline_id:
                baseline = await db.fetchrow(
                    "SELECT * FROM jobs WHERE project_id=$1 AND job_id=$2", pid, UUID(baseline_id)
                )
                if baseline is None:
                    raise ProblemError(404, "NOT_FOUND", "Baseline not found.")
                if baseline["state"] != "SUCCEEDED":
                    raise ProblemError(409, "BASELINE_INCOMPATIBLE", "Baseline must have succeeded.")
                previous_config = await self.read_artifact(project, "config", baseline["config_version"])
                if fingerprint(request["dataset_version"], docs["config"]) != fingerprint(
                    baseline["dataset_version"], previous_config
                ):
                    raise ProblemError(
                        409, "BASELINE_INCOMPATIBLE", "Dataset or evaluation profile differs from baseline."
                    )
                baseline_report = await db.fetchval(
                    "SELECT artifact_digest FROM reports WHERE project_id=$1 AND job_id=$2", pid, UUID(baseline_id)
                )
                if baseline_report is None:
                    raise ProblemError(409, "BASELINE_INCOMPATIBLE", "Baseline report is unavailable.")
                await self.read_artifact(project, "report", baseline_report)
            count = await db.fetchval(
                "SELECT count(*) FROM jobs WHERE project_id=$1 AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED')", pid
            )
            if count >= 100:
                raise ProblemError(429, "QUOTA_EXCEEDED", "Local project queue is full.", True)
            job_id = uuid4()
            row = await db.fetchrow(
                "INSERT INTO jobs(project_id,job_id,dataset_version,config_version,baseline_job_id,idempotency_key,request_hash,request,state,deadline_at,gate_policy) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'QUEUED',now()+$9*interval '1 second',$10) RETURNING *",
                pid,
                job_id,
                request["dataset_version"],
                request["config_version"],
                UUID(baseline_id) if baseline_id else None,
                key,
                request_hash,
                request,
                request["deadline_seconds"],
                docs["config"]["gate_policy"],
            )
            await db.execute(
                "INSERT INTO outbox(event_id,project_id,job_id,event_type) VALUES($1,$2,$3,'JOB_READY')",
                uuid4(),
                pid,
                job_id,
            )
            return job_document(row), True

    async def row(self, project, job_id):
        async with self.pool.acquire() as db:
            row = await db.fetchrow("SELECT * FROM jobs WHERE project_id=$1 AND job_id=$2", UUID(project), UUID(job_id))
        if row is None:
            raise ProblemError(404, "NOT_FOUND", "Job not found.")
        return row

    async def cancel(self, project, job_id):
        async with self.pool.acquire() as db, db.transaction():
            row = await db.fetchrow(
                "SELECT * FROM jobs WHERE project_id=$1 AND job_id=$2 FOR UPDATE", UUID(project), UUID(job_id)
            )
            if row is None:
                raise ProblemError(404, "NOT_FOUND", "Job not found.")
            if row["state"] == "CANCELLED":
                return job_document(row), 200
            if row["state"] in TERMINAL:
                raise ProblemError(409, "INVALID_STATE", "A completed job cannot be cancelled.")
            state = "CANCELLED" if row["state"] in {"QUEUED", "RETRY_WAIT"} else "CANCEL_REQUESTED"
            now = await db.fetchval("SELECT clock_timestamp()")
            gate = (
                inconclusive_gate(job_id, {"gate_policy": row["gate_policy"]}, timestamp(now), "CANCELLED")
                if state == "CANCELLED"
                else None
            )
            updated = await db.fetchrow(
                "UPDATE jobs SET state=$3,gate=$4,updated_at=$5 WHERE project_id=$1 AND job_id=$2 RETURNING *",
                UUID(project),
                UUID(job_id),
                state,
                gate,
                now,
            )
            if state == "CANCELLED":
                await db.execute(
                    "UPDATE outbox SET delivered_at=$3 WHERE project_id=$1 AND job_id=$2",
                    UUID(project),
                    UUID(job_id),
                    now,
                )
            return job_document(updated), 200 if state == "CANCELLED" else 202

    async def report(self, project, job_id):
        row = await self.row(project, job_id)
        if row["state"] not in TERMINAL:
            raise ProblemError(409, "REPORT_NOT_READY", "Evaluation has not completed.", True)
        if row["state"] != "SUCCEEDED":
            raise ProblemError(409, "REPORT_UNAVAILABLE", "Execution did not produce an authoritative report.")
        async with self.pool.acquire() as db:
            digest = await db.fetchval(
                "SELECT artifact_digest FROM reports WHERE project_id=$1 AND job_id=$2", UUID(project), UUID(job_id)
            )
        if digest is None:
            raise ProblemError(500, "INTERNAL_ERROR", "Authoritative report metadata is missing.")
        return {**await self.read_artifact(project, "report", digest), "artifact_digest": digest}

    async def gate(self, project, job_id):
        row = await self.row(project, job_id)
        if row["state"] not in TERMINAL:
            raise ProblemError(409, "REPORT_NOT_READY", "Evaluation has not completed.", True)
        if row["gate"] is None:
            raise ProblemError(500, "INTERNAL_ERROR", "Terminal gate metadata is missing.")
        return row["gate"]
