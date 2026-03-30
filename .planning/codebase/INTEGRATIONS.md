# External Integrations

**Analysis Date:** 2026-03-30

## APIs & External Services

**AWS Compute:**
- **ECS (Elastic Container Service)** - Container orchestration and task scheduling
  - SDK/Client: boto3 `ecs` client
  - Operations: `register_task_definition`, `create_service`, `update_service`, `delete_service`, `run_task`, `stop_task`, `list_tasks`, `describe_tasks`, `describe_services`
  - Used in: `controller-python/main.py`

**AWS Networking:**
- **ELBv2 (Elastic Load Balancer v2)** - Application Load Balancer management
  - SDK/Client: boto3 `elbv2` client
  - Operations: `describe_load_balancers`, `describe_listeners`, `describe_rules`, `describe_target_groups`, `create_target_group`, `delete_target_group`, `register_targets`, `deregister_targets`, `create_listener_rule`, `modify_listener_rule`, `delete_rule`
  - Used in: `controller-python/main.py` for ALB listener rule management and target group registration

**AWS Identity & Access Management:**
- **IAM (Identity & Access Management)** - Role and policy management
  - SDK/Client: boto3 `iam` client
  - Operations: `create_role`, `get_role`, `put_role_policy`, `attach_role_policy`
  - Used in: `controller-python/main.py` for workspace-scoped task role creation and S3 policy attachment
  - Policies created: Per-workspace app role with scoped ECS describe permissions and deny lateral movement

**AWS Monitoring:**
- **CloudWatch Logs** - Container and application logging
  - Service: AWS CloudWatch Logs
  - Log group: `/ecs/app-tester` (configurable via `LOG_GROUP` in controller)
  - Used by: ECS task containers for stdout/stderr streaming via `awslogs` log driver
  - Retention: `container_log_retention_days` variable (default 30 days)
  - Configuration in: `terraform/variables.tf`

**AWS Domain & DNS:**
- **Route53** - DNS hosting and management
  - Service: AWS Route53 hosted zone for `builder.muhilvannan.com`
  - Resources: Hosted zone created in `terraform/domain.tf`
  - A Record: Aliases ALB DNS name to custom domain `builder.muhilvannan.com`
  - Certificate validation: DNS validation records for ACM certificate
  - Used in: Domain routing for workspace URLs: `https://builder.muhilvannan.com/workspace{id}/{appId}`

**AWS Certificate Management:**
- **ACM (AWS Certificate Manager)** - SSL/TLS certificate provisioning
  - Certificate: `builder.muhilvannan.com` with wildcard `*.builder.muhilvannan.com`
  - Validation: DNS-based (Route53 records auto-created)
  - Used in: ALB HTTPS listener (port 443) for encrypted workspace connections
  - Configuration in: `terraform/domain.tf`

## Data Storage

**Databases:**
- None — Project uses stateless, ephemeral ECS tasks. No persistent database integration.

**File Storage:**
- **EFS (Elastic File System)** - Shared NFS volume for workspace persistence
  - Mount point: `/mnt/efs` within ECS tasks
  - Encryption: Enabled
  - Performance: General Purpose mode with bursting throughput
  - Availability: Multi-AZ (mount targets in each private subnet)
  - Access point: POSIX user (uid: 1000, gid: 1000) with 755 permissions on `/`
  - Security: NFS (port 2049) ingress from ECS task security group
  - Used in: Shared storage for workspace apps (e.g., data persistence, logs)
  - Configuration in: `terraform/efs.tf`

**Caching:**
- None detected. In-memory route table in `ui-nodejs/workspace-landing/server.js` for Envoy config routing state.

## Authentication & Identity

**Auth Provider:**
- Custom (AWS IAM-based) — No external OAuth/SAML provider.
- Workspace-scoped IAM roles dynamically created per workspace: `{workspaceId}-app-role`
- Role trust policy: Allow `ecs-tasks.amazonaws.com` service principal
- Inline policies: Limited ECS describe operations scoped to cluster, explicit deny on task management operations (prevent lateral movement)
- Implementation in: `controller-python/main.py` function `ensure_workspace_app_role()`

**Caller Identity Verification:**
- `/health` endpoint performs `sts.get_caller_identity()` to verify AWS credentials and return account/ARN information
- Used for debugging and permission validation

## Monitoring & Observability

**Error Tracking:**
- None detected. Errors logged to CloudWatch Logs via container `awslogs` driver.

**Logs:**
- CloudWatch Logs via `awslogs` driver (built into ECS)
- Log group: `/ecs/app-tester`
- Log streams per container: `{workspaceId}/{containerName}` (e.g., `ws-xyz/landing-page`, `ws-xyz/envoy`, `ws-xyz/app-abc`)
- Retention: 30 days (configurable)
- Configuration: In container definitions within `register_task_definition()` and `register_app_task_definition()` in `controller-python/main.py`

**Health Checks:**
- `/health` endpoint returns: status, region, cluster, domain, caller identity, VPC config, architecture
- No external health monitoring service (self-contained checks)

## CI/CD & Deployment

**Hosting:**
- AWS ECS Fargate (serverless container orchestration)
- Cluster name: `ecs-app-tester-exp-dev` (configurable)
- Region: `eu-west-1` (configurable)
- VPC: `10.0.0.0/16` CIDR (configurable)
- Availability zones: `eu-west-1a`, `eu-west-1b` (multi-AZ)

**Infrastructure as Code:**
- Terraform v5.0
- State management: Local `terraform/terraform.tfstate` (can be migrated to S3 backend)
- Workspace isolation: Terraform workspaces for separate dev/prod environments
- Modules: Single root module in `terraform/`

**CI Pipeline:**
- None detected. Manual deployment via `make tf-apply` and `make api-run`.

**Deployment Flow:**
1. Infrastructure: `make tf-init` → `make tf-plan` → `make tf-apply` → `make tf-output` (generates `infrastructure-outputs.json`)
2. Controller API: `make api-build` → `make api-run` (Docker container on local machine)
3. UI: `make ui-install` → `make ui-start` (Node.js on local machine)
4. Workspace bootstrap: POST `/workspace/bootstrap` (controller API creates ECS service, tasks, target groups, listener rules)

## Environment Configuration

**Required env vars (Controller):**
- `AWS_DEFAULT_REGION` or `AWS_REGION` - AWS region (defaults to `eu-west-1`)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (or `~/.aws/credentials`)
- `INFRA_OUTPUTS` - Path to infrastructure-outputs.json (defaults to `/app/infra/infrastructure-outputs.json`)

**Required env vars (Workspace Landing Page):**
- `WORKSPACE_ID` - Workspace identifier
- `BASE_PATH` - URL path prefix for workspace (`/workspace{id}`)
- `DOMAIN` - Domain name for workspace URLs (`builder.muhilvannan.com`)
- `ENVOY_ADMIN_PORT` - Envoy admin API port (9901)

**AWS Credentials Location:**
- Development: `~/.aws/credentials` file (mounted into Docker container via `controller-python/Makefile`)
- Container env vars: `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
- Production: IAM role assumed by ECS task (execution role and workspace app role)

**Secrets location:**
- None externally managed (AWS IAM handles authentication)
- ACM certificate stored in AWS Certificate Manager
- No `.env` files committed to repository

## Webhooks & Callbacks

**Incoming:**
- None from external services
- Internal: Landing page receives route add/remove requests from controller
  - `POST /internal/routes/add` - Register app route with Envoy
  - `POST /internal/routes/remove` - Deregister app route from Envoy
  - Implementation: `ui-nodejs/workspace-landing/server.js`

**Outgoing:**
- None to external services
- Controller makes internal HTTP calls to landing page (same ECS task)
  - `register_app_route()` → `POST http://{workspace_ip}:3001/internal/routes/add`
  - `deregister_app_route()` → `POST http://{workspace_ip}:3001/internal/routes/remove`
  - Implementation: `controller-python/main.py` using httpx client

## Data Flow

**Workspace Bootstrap:**
```
UI POST /api/workspace/bootstrap
  ↓
Express proxy (ui-nodejs/app.js)
  ↓
Controller POST /workspace/bootstrap
  ↓
1. Create IAM role ({workspaceId}-app-role) — IAM service
2. Register workspace task def (landing-page + envoy) — ECS service
3. Create/update ECS service ({workspaceId}) — ECS service
4. Create target group ({workspaceId}-tg) — ELBv2
5. Create disabled ALB listener rule (503 response) — ELBv2
6. Launch workspace service task — ECS Fargate
7. Get task IP from ENI attachment — ECS service
8. Register task IP to target group — ELBv2
  ↓
Return: service name, workspace URL, per-app URLs
```

**App Start Flow:**
```
UI POST /api/app/start
  ↓
Controller POST /app/start
  ↓
1. Enable ALB listener rule (forward to target group) — ELBv2
2. Get workspace task IP — ECS service
3. Register app route with Envoy — Landing page internal API (httpx)
  ↓
User can access app at: https://builder.muhilvannan.com/workspace{id}/{appId}
```

**Request Routing (App Running):**
```
HTTPS Request to builder.muhilvannan.com/workspace{id}/{appId}
  ↓
Route53 resolves to ALB IP
  ↓
ALB listener rule 443 matches /workspace{id}/* → forwards to {workspaceId}-tg
  ↓
Target group routes to workspace service task IP:8080 (Envoy)
  ↓
Envoy reads in-memory config for /workspace{id}/{appId}/* → routes to {appTaskIP}:{port}
  ↓
App container (streamlit, fastapi, reactjs, mkdocs, or custom) handles request
```

## Integration Summary Table

| Service | Type | Purpose | Status |
|---------|------|---------|--------|
| AWS ECS | Compute | Container orchestration | Active |
| AWS ALB (ELBv2) | Load Balancer | Request routing | Active |
| AWS IAM | Identity | Role and policy management | Active |
| AWS CloudWatch Logs | Logging | Application logs | Active |
| AWS Route53 | DNS | Domain management | Active |
| AWS ACM | Certificate | SSL/TLS | Active |
| AWS EFS | Storage | Shared workspace storage | Active |
| AWS STS | Security | Caller identity verification | Active (health check) |
| Envoy Proxy | Proxy | L7 request routing within workspace | Active |

---

*Integration audit: 2026-03-30*
