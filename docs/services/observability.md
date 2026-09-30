# Telemetry, SLIs and proposed SLOs

Status: unmeasured targets. A 30-day staging/production observation window is required before claiming achievement. CloudWatch/structured logs carry infrastructure truth; Langfuse carries optional redacted evaluation traces and dataset provenance.

| SLI | Proposed target | Measurement / exclusions |
|---|---|---|
| API availability | 99.9% / rolling 30 days | non-5xx/non-timeout responses to valid authenticated API requests; exclude caller 4xx, include service 429 due to capacity |
| Admission latency | p95 <500 ms | accepted/replayed job requests at <=20 req/s; excludes registration/upload |
| Metadata read latency | p95 <200 ms | successful job/gate reads; report object retrieval tracked separately |
| Queue delay | p95 <120 s | accepted to first RUNNING under provisioned quota; includes Fargate startup |
| Standard job completion | 95% <10 min | 100 cases x3, specified two quality metrics, approved provider, concurrency 4; includes queue, retries and provider outages |
| Terminal integrity | 100% | no duplicate authoritative report or unfenced completion; correctness invariant, not best-effort SLO |
| Recovery objectives | RPO <=15 min, RTO <=60 min | restore drill targets including DB/artifact reconciliation; not validated |

At 99.9% the 30-day time-equivalent budget is 43.2 minutes, but availability is request-based. Page for 14.4x budget burn on both 1-hour and 5-minute windows, or 6x on both 6-hour and 30-minute windows; low-traffic services also need black-box probes. Freeze deployments after budget exhaustion until causes are understood. Queue age >5 min for 10 min, any integrity violation, or sustained lease-recovery failures pages the operator. Budget exhaustion is a product event; unexpected unbounded spend is an incident.

Metrics: `api_requests_total{route,status_class}`, admission/read histograms, oldest queue age, jobs by state/outcome, launch failures, lease expiries, active tasks, provider in-flight calls/RPM/TPM, remaining budget, retry counts, input/output tokens, estimated USD, report upload failures, DB pool wait, outbox lag and telemetry dropped events. Keep IDs/prompts out of metric labels. Log request/job/attempt/project IDs and trace IDs with secrets and content redacted; project IDs in logs remain access-controlled.

Trace tree: job -> attempt -> target generation -> deterministic assertions -> retrieval/judge metrics -> artifact commit -> gate. Propagate W3C trace context through job metadata; store external provider request ID only if safe. Langfuse export runs through a bounded queue (proposal 1000 events) with finite retries; after exhaustion drop telemetry and increment a metric without failing the evaluation. Raw prompt/output export is disabled by default. Dataset imports are explicit operator triggers, not a live dependency of execution. Follow the current [Langfuse deployment guide](https://langfuse.com/self-hosting/deployment/docker-compose) if self-hosting; the local Compose here does not include Langfuse's separate dependencies.

Dashboard panels: availability and latency, backlog/task capacity, provider failure/cost, quality distributions by immutable suite, baseline age, comparison inconclusive rate, telemetry health. Quality panels must distinguish model regressions from failed executions. Every alert links to [Operations](../../Operations.md), relevant IDs, recent deployment digest and recovery action.
