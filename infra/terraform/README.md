# Terraform scaffold and activation boundary

Status: **partial resource slice, not a production deployment**. HCL describes an encrypted artifact bucket, log group, ECS cluster, and a worker task definition wired to externally supplied IAM roles. It deliberately does not supply an API service, ALB, VPC, RDS, IAM implementation, secrets, autoscaling or alarms. [Deployment blueprint](../../docs/delivery/deployment.md) specifies those components and their acceptance criteria.

`allow_provisioning` defaults to false; a lifecycle precondition blocks planning/applying resources until an operator explicitly enables it. This is an accidental-use guard, not a security boundary. No Terraform apply or paid cloud provisioning is authorized or performed in Phase 2.

Prerequisites for future activation: approved AWS account/region and cost budget, isolated environment, completed module wiring, validated immutable image digest, IAM/egress review, AWS OIDC deploy role, encrypted S3 state backend with locking, reviewed plan and environment approval. Never put secret values in tfvars or backend config. State itself is sensitive even if outputs are marked sensitive.

Offline structural commands (Terraform must be installed; provider initialization downloads dependencies):

```bash
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```

These commands do not demonstrate production readiness. The included [provider lockfile](.terraform.lock.hcl) records AWS provider 6.66.0 resolved during offline configuration validation with Terraform 1.13.3; preserve and review it with version upgrades. `terraform plan` is deferred until the resource slice is completed. A future environment root should use the [backend example](backend.tf.example) and the [input example](terraform.tfvars.example); both contain placeholders.

No automatic destroy workflow. Bucket `prevent_destroy` and retained S3 objects protect against accidental teardown but are insufficient alone; use IAM restrictions and audited operator change controls.
