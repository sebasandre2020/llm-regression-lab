# Implementation roadmap and acceptance criteria

Phase 2 supplied the blueprint. **Phase 3.1 is implemented locally** with a fake provider; see [local behavior and limitations](local-service.md) and [validation evidence](validation.md). Production service completion remains ahead.

| Milestone | Deliverable | Exit evidence |
|---|---|---|
| 3.1 Complete: local service | FastAPI/Pydantic models, local project/scope auth, PostgreSQL migrations, filesystem artifacts and separate fake-provider worker | HTTP registration -> job -> report/gate demo; contract checks and PostgreSQL integration tests; no real model spend |
| 3.2 Durable worker | outbox, dispatcher, attempt leases, cancellation, quota reservations, fenced commit | crash/duplicate/race suite proves one authoritative report and bounded calls |
| 3.3 Evaluator adapters | locked promptfoo/Ragas, shared provider bridge, golden normalized fixtures | assertion failures separated from engine errors; missing usage/NaN fail closed |
| 3.4 Evaluation validity | consented 100-case human calibration set, paired baseline, confidence interval implementation | calibration report, deterministic gate golden cases, complete provenance |
| 3.5 Staging delivery | completed Terraform modules, image pipeline, RLS/IAM/egress, telemetry | approved plan, staging end-to-end evaluation, fork PR isolation, rollback and restore drills |
| 3.6 Production readiness | load/cost measurements, SLO dashboards, runbooks and policy ownership | measured workload report, data approval, operational sign-off and reviewed spend budget |

No frontend milestone is required. An optional developer testbench may submit requests and show reports using the same authorization, but must not become a separate product or hold provider credentials.

Portfolio proof should eventually include a reproducible CI failure caused by a controlled prompt regression, a separate infrastructure-error example, a bounded-concurrency trace, immutable IDs across reruns, and a measured release report. Do not put anticipated production metrics on a résumé as achieved results.
