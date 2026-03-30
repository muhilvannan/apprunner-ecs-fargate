# Technology Stack

**Analysis Date:** 2026-03-30

## Languages

**Primary:**
- Python 3.12 - Controller API server, Uvicorn-based FastAPI application. Used in `controller-python/` for AWS orchestration and task management.
- Node.js 20 (slim image) - Web UI and workspace landing page server. Used in `ui-nodejs/` and `ui-nodejs/workspace-landing/`.
- JavaScript/TypeScript (ES6+) - Frontend UI in `ui-nodejs/`, browser-side app routing and control.
- HCL (Terraform) - Infrastructure as code in `terraform/` for AWS resource provisioning.
- Shell (bash, sh) - Makefile targets and container entrypoints. Used in `controller-python/entrypoint.sh` and various shell commands within Docker containers.

**Secondary:**
- YAML - Envoy proxy configuration (dynamically generated and managed), Route53/CloudWatch configuration.

## Runtime

**Environment:**
- Docker - All application components run in containers. Controller uses `python:3.12-slim`, workspace landing page uses `node:20-slim`, Envoy uses `envoyproxy/envoy:v1.29-latest`.

**Package Manager:**
- npm - Node.js packages. Lockfile: `ui-nodejs/package-lock.json` present.
- pip - Python packages. Requirements defined in `controller-python/requirements.txt`.

## Frameworks

**Core:**
- FastAPI 0.x - REST API framework for controller. Used in `controller-python/main.py` for `/workspace/bootstrap`, `/workspace/{id}/apps`, `/app/start`, `/app/stop` endpoints.
- Express 4.18.2 - Web server framework for Node.js UI and workspace landing page. Used in `ui-nodejs/app.js` (proxy UI) and `ui-nodejs/workspace-landing/server.js` (Envoy config API).

**Infrastructure:**
- Terraform ~5.0 - AWS resource management. Configuration in `terraform/*.tf` files with state in `terraform/terraform.tfstate`.

**Container Orchestration:**
- ECS Fargate - Managed container orchestration on AWS. Task definitions, services, and run_task operations orchestrated via `controller-python/main.py` using boto3.

**Proxy/Networking:**
- Envoy Proxy v1.29 - L7 reverse proxy for request routing within workspace. Container runs in workspace service alongside landing-page container.

## Key Dependencies

**Critical:**
- boto3 - AWS SDK for Python. Used in `controller-python/main.py` for ECS, ELBv2 (ALB), and IAM operations.
- Pydantic - Data validation for FastAPI request models. Used in `controller-python/main.py` for `WorkspaceBootstrap` and `AppAction` models.
- httpx - Async HTTP client for Python. Used in `controller-python/main.py` to communicate with workspace landing page internal API (`/internal/routes/add`, `/internal/routes/remove`).
- Uvicorn - ASGI server for FastAPI. Used in `controller-python/Dockerfile` as entrypoint for FastAPI app.
- Express - HTTP middleware for routing. Used in both `ui-nodejs/app.js` and `ui-nodejs/workspace-landing/server.js`.
- body-parser - Middleware for parsing request bodies. Used in `ui-nodejs/app.js` for JSON and URL-encoded payloads.

**Infrastructure:**
- hashicorp/aws - Terraform AWS provider v~5.0. Defined in `terraform/main.tf`.

## Configuration

**Environment:**
- Controller API reads infrastructure outputs from mounted JSON file: `INFRA_OUTPUTS` env var points to `infrastructure-outputs.json` (mounts at `/app/infra/` in container).
- AWS credentials via standard AWS SDK methods: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, or `~/.aws` directory mount.
- Runtime region: `AWS_DEFAULT_REGION` or `AWS_REGION` env var (defaults to `eu-west-1`).
- Workspace landing page configured via env vars: `WORKSPACE_ID`, `BASE_PATH`, `DOMAIN`, `ENVOY_ADMIN_PORT`.

**Build:**
- `controller-python/Dockerfile` - Multi-stage Python 3.12-slim, pip installs requirements.txt, exposes port 8000.
- `ui-nodejs/workspace-landing/Dockerfile` - Node.js 20-slim, npm install, exposes port 3001.
- `terraform/terraform.tfvars` - Terraform variables (region, VPC CIDR, AZs, log retention, SSL certificate ARN).
- `terraform/.tfstate` - Terraform state with deployed resource IDs (tracked locally, mounted into controller container).

**Orchestration:**
- Root `Makefile` - Task runners for Docker builds/runs, Terraform init/plan/apply, UI npm commands.
- `controller-python/Makefile` - Docker build, run, stop, clean tasks with AWS credential mounting.
- `ui-nodejs/Makefile` - npm install and start tasks.
- `terraform/Makefile` - Terraform workspace management, init, validate, plan, apply, destroy with active workspace reporting.

## Platform Requirements

**Development:**
- Docker - Build and run containers locally.
- Terraform - Plan and apply infrastructure changes (v1.0+).
- AWS CLI - Utility for AWS resource inspection and cleanup (`make cleanup-aws` target).
- Node.js 18+ - For UI npm install/start locally (optional if using containers).
- Python 3.12+ - For controller development (optional if using containers).
- Local AWS credentials - `~/.aws/credentials` or environment variables for Terraform and Docker mounts.
- `infrastructure-outputs.json` - Required after `terraform apply` for controller to load deployed resource IDs.

**Production:**
- AWS Account with permissions for ECS, ECR, ALB, IAM, CloudWatch Logs, Route53, ACM, VPC, EFS.
- Deployment region: `eu-west-1` (configurable via Terraform variables).
- Domain: `builder.muhilvannan.com` with Route53 hosted zone and ACM certificate.
- VPC with private subnets for ECS tasks (created by Terraform).

## Container Images

**Public Registry (AWS ECR Public):**
- `public.ecr.aws/docker/library/python:3.12-slim` - Base image for controller and all app types.
- `public.ecr.aws/docker/library/node:20-slim` - Base image for workspace landing page and UI.
- `public.ecr.aws/envoyproxy/envoy:v1.29-latest` - L7 proxy for workspace request routing.

**Local Registry:**
- `ecs-controller-api` - Built from `controller-python/Dockerfile`, pushed to local Docker daemon during `make api-run`.

## App Type Runtime Support

Controller dynamically spawns app tasks with these supported types (defined in `APP_CONFIGS` in `controller-python/main.py`):

| Type | Image | Port | Notes |
|------|-------|------|-------|
| `streamlit` | python:3.12-slim | 8501 | `pip install streamlit` at runtime, server config includes `--server.baseUrlPath` for workspace routing |
| `fastapi` | python:3.12-slim | 8000 | `pip install fastapi uvicorn` at runtime, minimal hello-world app included |
| `reactjs` | python:3.12-slim | 3000 | React 18 via CDN, served by Python `http.server` with base path prefix rewrite |
| `mkdocs` | python:3.12-slim | 8001 | `pip install mkdocs` at runtime, builds docs site with custom Python HTTP handler |
| `custom` | python:3.12-slim | 8080 | Sleep placeholder for testing (900s timeout) |

---

*Stack analysis: 2026-03-30*
