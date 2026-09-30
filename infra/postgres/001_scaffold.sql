-- Local bootstrap scaffold only; production migrations/RLS/quota tables are pending.
BEGIN;
CREATE TABLE projects (
    project_id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE versions (
    project_id uuid NOT NULL REFERENCES projects,
    kind text NOT NULL CHECK (kind IN ('dataset', 'config')),
    digest text NOT NULL CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    schema_version text NOT NULL CHECK (schema_version = '1.0'),
    object_key text NOT NULL,
    object_version_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, kind, digest)
);
CREATE TABLE jobs (
    project_id uuid NOT NULL REFERENCES projects,
    job_id uuid NOT NULL,
    dataset_kind text NOT NULL DEFAULT 'dataset' CHECK (dataset_kind = 'dataset'),
    dataset_version text NOT NULL,
    config_kind text NOT NULL DEFAULT 'config' CHECK (config_kind = 'config'),
    config_version text NOT NULL,
    baseline_job_id uuid,
    idempotency_key varchar(128) NOT NULL CHECK (length(idempotency_key) >= 8),
    request_hash text NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    request jsonb NOT NULL,
    state text NOT NULL CHECK (state IN ('QUEUED','DISPATCHING','RUNNING','RETRY_WAIT','CANCEL_REQUESTED','SUCCEEDED','FAILED','CANCELLED')),
    current_attempt integer NOT NULL DEFAULT 0 CHECK (current_attempt BETWEEN 0 AND 3),
    deadline_at timestamptz NOT NULL,
    next_attempt_at timestamptz,
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, job_id),
    UNIQUE (project_id, idempotency_key),
    FOREIGN KEY (project_id, dataset_kind, dataset_version) REFERENCES versions,
    FOREIGN KEY (project_id, config_kind, config_version) REFERENCES versions,
    FOREIGN KEY (project_id, baseline_job_id) REFERENCES jobs (project_id, job_id),
    CHECK (deadline_at > created_at),
    CHECK (baseline_job_id IS DISTINCT FROM job_id)
);
CREATE TABLE attempts (
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
    fence uuid NOT NULL UNIQUE,
    launch_token varchar(64) NOT NULL UNIQUE,
    task_arn text,
    state text NOT NULL CHECK (state IN ('RESERVED','ACTIVE','COMPLETED','ABORTED')),
    heartbeat_at timestamptz,
    lease_expires_at timestamptz NOT NULL,
    PRIMARY KEY (project_id, job_id, attempt_number),
    FOREIGN KEY (project_id, job_id) REFERENCES jobs
);
CREATE UNIQUE INDEX one_live_attempt ON attempts (project_id, job_id)
    WHERE state IN ('RESERVED','ACTIVE');
CREATE TABLE outbox (
    event_id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    event_type text NOT NULL CHECK (event_type = 'JOB_READY'),
    created_at timestamptz NOT NULL DEFAULT now(),
    claim_expires_at timestamptz,
    delivered_at timestamptz,
    FOREIGN KEY (project_id, job_id) REFERENCES jobs,
    UNIQUE (project_id, job_id, event_type)
);
CREATE TABLE reports (
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    attempt_number integer NOT NULL,
    artifact_digest text NOT NULL CHECK (artifact_digest ~ '^sha256:[0-9a-f]{64}$'),
    object_key text NOT NULL,
    object_version_id text NOT NULL,
    gate jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, job_id),
    FOREIGN KEY (project_id, job_id, attempt_number) REFERENCES attempts
);
CREATE INDEX jobs_eligible ON jobs (state, next_attempt_at);
CREATE INDEX jobs_project_created ON jobs (project_id, created_at);
CREATE INDEX attempts_lease ON attempts (lease_expires_at) WHERE state IN ('RESERVED','ACTIVE');
CREATE INDEX outbox_pending ON outbox (created_at) WHERE delivered_at IS NULL;
INSERT INTO projects (project_id, name) VALUES ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'local-scaffold');
COMMIT;
