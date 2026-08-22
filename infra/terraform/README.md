# ECS infrastructure (Terraform)

The IaC that `aws_ecs_deployment.md` described by hand: VPC (2 AZ,
public/private + NAT), ALB (HTTP, HTTPS when `certificate_arn` is set),
ECS Fargate services (backend + worker + nginx frontend with Cloud Map
service discovery for the same-origin proxy), EFS for the KB volume,
ElastiCache Redis (multi-AZ) for the case store + job queue, RDS Postgres
for the durable case timeline, ECR, IAM (task role scoped to
`medisense/*` secrets + EFS), CPU target-tracking autoscaling, and
rolling deploys with the circuit breaker (automatic rollback on failed
health checks).

## Owner prerequisites

1. S3 + DynamoDB state backend (uncomment in `versions.tf`).
2. Secrets in AWS Secrets Manager under `medisense/`:
   `AUTH_SECRET_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
   optionally `SENTRY_DSN` (resolved by `core/secrets.py`).
3. `TF_VAR_db_password` from a secret store; images pushed by CI.

## Apply

    terraform init
    terraform plan  -var backend_image=...  -var frontend_image=...
    terraform apply -var backend_image=...  -var frontend_image=...

Validated with `terraform fmt -check` and `terraform validate` in the
development environment (provider plugins fetched at init); `plan`/`apply`
require AWS credentials and are owner-run.

Deliberate scope notes: blue/green via CodeDeploy is deferred until a
second listener/target-group pair is justified - the deployment circuit
breaker already gives automatic rollback; in-cluster TLS (mTLS/mesh)
remains on the readiness register.
