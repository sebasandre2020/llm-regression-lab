# AWS infrastructure and deployment blueprint

Status: planned production topology with a [partial Terraform resource scaffold](../../infra/terraform/README.md). No account, DNS, credentials, paid resources or deployed service is created by this phase. Default region proposal is `us-east-1`; data residency approval precedes activation.

## Environment topology and module interfaces

Use separate staging and production AWS accounts and state keys. Two AZs per environment; API replicas spread across AZs. Fargate workers use on-demand capacity initially; interruption-prone Spot is deferred until recovery is demonstrated.

| Module to implement | Inputs | Outputs / required controls |
|---|---|---|
| `network` | CIDR, two AZs, egress allowlist | public ALB subnets; private app and isolated DB subnets; private tasks with public IP disabled; NAT/proxy per AZ; S3 gateway and ECR/logs/secrets interface endpoints |
| `identity` | account/project IDs, GitHub org/repo/environments | API/dispatcher/project-worker/execution/migration roles; tightly scoped `PassRole`; OIDC deploy roles |
| `data` | subnet group, security groups, KMS key | encrypted RDS PostgreSQL Multi-AZ, deletion protection, PITR 14 days, managed master password in Secrets Manager; separate app role |
| `artifacts` | unique bucket name, KMS key | versioning, block-public-access, TLS-only policy, conditional writes, deletion role and lifecycle backstops |
| `registry` | image repositories | immutable ECR tags, scanning, retained rollback digests, lifecycle excluding deployed revisions |
| `compute` | image digests, network, roles, DB secret, bucket | ECS cluster; API service min 2/max 6; dispatcher min 1/max 2; on-demand worker task definition; no worker service |
| `edge` | approved domain and certificate | Route 53 + ACM + HTTPS ALB, HTTP redirect, WAF/rate limits, `/health/*` private routing |
| `observability` | log groups, alarm destinations | KMS logs, dashboard, availability/backlog/spend alarms, CloudTrail audit |
| `budget` | approved monthly cap, recipients | AWS Budgets alerts and anomaly detection; application quota still enforces provider spend |

Security groups: internet -> ALB 443; ALB -> API 8000; API/dispatcher/worker -> DB 5432; tasks -> VPC endpoints/proxy 443 as applicable; no inbound worker/dispatcher listener from ALB. Security groups alone do not enforce domain allowlists; configure the egress proxy and DNS/IP validation. The worker provider bridge is loopback-only. RunTask must use private subnets and `assignPublicIp=DISABLED`.

RDS sizing starts with a small production-appropriate instance selected from measured connection/memory demand, not a claimed capacity figure. Enable storage autoscaling with a budget cap, TLS certificate verification and slow-query monitoring. Tune connection caps against the maximum API and worker count. Only migrations use schema-owner credentials.

## IAM and credentials

| Identity | Allowed responsibilities | Explicit restriction |
|---|---|---|
| API task | registry object writes/reads and report reads, application DB secret | no ECS launches or raw provider secret access |
| Dispatcher task | RunTask on approved worker task family, Describe/StopTask on environment cluster, PassRole for approved project roles | cannot register arbitrary task definitions or pass arbitrary roles |
| Worker task | read project versions; write attempt/report prefix; provider secrets through approved bridge | no bucket deletion, deployment privileges or cross-project prefixes |
| Execution role | ECR pulls, log streams, referenced startup secrets/KMS decrypt | separate from application task role |
| Migration role | schema migration and application grants | short-lived one-shot task, not API credential |
| GitHub deploy role | approved ECR push/task/service updates and migration launch | environment-bound trust and approved PassRole only |
| Terraform role | environment resource changes | separate from runtime deployment; reviewed saved plan |

Secrets Manager contains provider credentials, database connection material, IdP configuration where secret, and Langfuse keys. Terraform creates references or managed secrets, not secret plaintext in variables. KMS key policy must permit each AWS service principal where needed (including CloudWatch logs with encryption-context restriction). The example's supplied roles/key require this wiring before use.

GitHub OIDC trust requires audience `sts.amazonaws.com` and exact subject `repo:ORG/REPO:environment:production` (and separate staging role). Configure environment branch restrictions and reviewers; subject restrictions alone do not prove branch identity when using environment subjects. GitHub describes the audience/subject trust configuration in its [AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws). No persistent AWS access keys.

State bootstrap is separate: encrypted private S3 bucket with versioning, least-privilege state reader/writer and lockfile permissions, access logs/audit, environment-specific keys. Use S3 native `use_lockfile`; DynamoDB locking is deprecated in the current [Terraform S3 backend documentation](https://developer.hashicorp.com/terraform/language/backend/s3). State/plan artifacts can expose secrets; encrypt and restrict retention/access. Never share a production state file in PR logs.

## Release procedure

1. Validate contracts, code, dependencies and fake-provider integration suite on every PR. Review evaluation/config/baseline changes separately; protect workflow and policy paths with CODEOWNERS once maintainers are known.
2. On protected main, build one image per component (initially a common locked image with command overrides is acceptable). Generate SBOM, scan vulnerabilities and sign/provenance-attest images; pin deployment by digest. Lock all Python and npm dependencies and base/action digests before activation.
3. Deploy to staging: run additive migration task first and require exit 0. Update API/dispatcher services using ECS deployment circuit breaker and rollback. Register worker revision; new attempts get the new revision while existing attempts finish on their recorded digest.
4. Run authenticated smoke, cross-project denial, full evaluation gate against approved baseline, cancellation and crash recovery tests. Observe alarm window (proposal 15 minutes). Any gate exit 1 or 2 blocks promotion with distinct diagnostics.
5. After production environment approval, promote the same image digests. API rolling deployment uses minimumHealthyPercent 100 and maximumPercent 200 with two baseline replicas, readiness and graceful connection draining. Dispatcher stops claiming new work on SIGTERM; leases permit takeover. New worker launches switch revisions only after staging evidence is accepted.
6. Verify service stability, API SLI, backlog, provider spend and a post-deploy synthetic evaluation. Record deployment SHA/image/schema/baseline evidence. Keep previous image/task revisions through rollback window.

Rollback: redeploy previous API/dispatcher/task revisions; new attempts use old worker image. Do not mutate an in-flight job's config or image. Additive DB migrations remain; avoid automatic destructive down migrations. Use expand/contract across at least two releases; remove old columns only after all old tasks are drained. A migration incompatible with previous binaries prevents automatic rollback and requires a forward repair/restore decision by the operator.

Terraform changes are separate from application rollout: format/validate, lint/security policy scan, refresh-aware plan under scoped credentials, saved encrypted plan attached to protected run, reviewer approval, apply the exact plan, then drift check. Do not run `apply -auto-approve` on an unreviewed branch. Initial infrastructure cost components include ALB, RDS Multi-AZ, NAT/proxy, endpoints, Fargate, logs, S3 and model APIs; produce a current priced estimate before provisioning. No dollar estimate is claimed here.
