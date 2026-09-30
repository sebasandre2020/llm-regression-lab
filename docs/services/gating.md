# Comparability and gate policy

Status: proposed production policy `paired-v1`; statistical computation is not implemented. The [local service](../local-service.md) always emits `INCONCLUSIVE` for fake results. Planned gate computation never makes provider calls; its inputs are two complete reports and an immutable candidate policy, and identical bytes must yield identical verdicts/reasons.

Validate before comparing: candidate execution succeeded; baseline exists and succeeded; same project, dataset digest, case/repetition IDs, evaluator/judge/rubric versions, metric policy, pricing snapshot, seed policy, repetitions and execution profile. Match the recorded provider revision for the judge; application model may differ if declared as a changed dimension. Both reports must have complete usage for a cost gate. Unknown provider revision stability is disclosed and may force `INCONCLUSIVE` under the release profile.

Fingerprint is the canonical digest of those shared dimensions, excluding target prompt/model/retrieval/source revisions and thresholds. Candidate thresholds still come from an administrator-approved configuration policy: a PR cannot weaken its own gate. Baseline creation (`baseline_job_id: null`) can finish `SUCCEEDED` with gate `INCONCLUSIVE / BASELINE_REQUIRED`; an operator may designate that job as a baseline after inspecting the evidence. There is no automatic baseline promotion in v1.

Default release policy proposal: at least 100 distinct cases, 3 repetitions each, 100% metric coverage. For each quality metric, compute candidate-minus-baseline differences, macro-average each case's repetitions, then paired bootstrap resample cases 10,000 times with seed 42. This preserves within-case repetition dependence. Use the percentile 95% interval. `QUALITY_REGRESSION` if the interval upper bound is below negative allowed drop (default 0.02 absolute); `PASS` for that dimension if the lower bound is at or above negative allowed drop; otherwise `INSUFFICIENT_EVIDENCE` and inconclusive. Equality at the permitted boundary passes. Below minimum sample size, do not manufacture confidence. Thresholds and bootstrap version belong to the policy digest.

For target-call latency, compare nearest-rank p95 candidate versus baseline. Default threshold: at most 20% relative increase **and** candidate p95 at most 5000 ms. Cost per expected observation must be at most 10% higher and total job estimate must stay within configured maximum USD. Zero baseline latency/cost makes the relative test undefined: use explicitly configured absolute limits only, otherwise inconclusive. These resource thresholds are direct policy gates, not statistical claims. Collect equal workloads in the same region/profile with cold-start policy held constant.

Decision order is deliberately conservative:

1. Failed/cancelled execution gives `INCONCLUSIVE` immediately.
2. Missing baseline, incompatible evidence, missing metric/usage, inadequate sample or a quality confidence interval crossing its boundary gives `INCONCLUSIVE`, even if another metric appears worse. Include all diagnostic reasons; do not label partial evidence a regression.
3. If all evidence is actionable, any breached quality, latency or cost threshold gives `REGRESSION`; store a reason for each breached dimension.
4. Otherwise return `PASS / WITHIN_LIMITS`.

PR smoke suite (20 cases, 1 repetition) is intentionally diagnostic and cannot satisfy the release gate. Full protected-branch suite is required before promotion. Do not weaken release minimums to turn a cheap smoke run green. The future CI client distinguishes exit 1 (valid regression) from exit 2 (evaluation/infrastructure/evidence issue), but both block release. Operators may retry infrastructure failures; they may not automatically rerun regressions until one passes.

Required golden tests: exact threshold equality, zero baseline, confidence interval crossing, missing cost, NaN, changed judge/dataset, unequal repetitions, baseline-only run, failed worker with partial good results, policy relaxation by an untrusted caller, and complete valid regression. The example report is synthetic and exercises shape only, not the statistical engine.
