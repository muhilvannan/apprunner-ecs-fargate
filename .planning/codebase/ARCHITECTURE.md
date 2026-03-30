# Architecture

**Analysis Date:** 2026-03-30

## Pattern Overview

**Overall:** Proxy-based Multi-Workspace Orchestration with Per-Workspace L7 Load Balancing

**Key Characteristics:**
- **One ECS Service per workspace** containing a multi-container task (landing page + Envoy proxy)
- **Standalone app tasks** launched via `run_task` (not service-managed) for independent app lifecycle
- **Envoy proxy** handles L7 routing and dynamic app route management via internal API
- **Three-tier API** — ALB → Envoy → app tasks, with hot-reloadable configuration
- **Per-workspace IAM role** with strict lateral movement denial for security isolation

## Layers

**Presentation Layer:**
- Purpose: Web-based workspace management and app status dashboard
- Location: `ui-nodejs/`
- Contains: Express.js proxy server, HTML/CSS UI frontend
- Depends on: Controller API (FastAPI backend)
- Used by: Browser clients requesting workspace bootstrap, app start/stop operations

**Control/Orchestration Layer:**
- Purpose: AWS ECS resource orchestration — task definitions, services, target groups, ALB rules, IAM
- Location: `controller-python/main.py`
- Contains: FastAPI endpoints for workspace bootstrap, app lifecycle, health checks
- Depends on: Boto3 (AWS SDK), httpx for internal Envoy routes API calls
- Used by: UI layer and external API clients for workspace management

**Proxy/Routing Layer:**
- Purpose: Dynamic L7 HTTP routing and load balancing to app tasks
- Location: `ui-nodejs/workspace-landing/server.js` (routes API), Envoy container (proxy engine)
- Contains: Routes in-memory map, Envoy YAML config generation, SIGHUP reload mechanism
- Depends on: ECS task IP discovery from control layer
- Used by: ALB (forwards all workspace traffic to Envoy port 8080), app tasks (receive routed traffic)

**Infrastructure Layer:**
- Purpose: Base AWS resources — VPC, ECS cluster, ALB, IAM roles, CloudWatch logging
- Location: `terraform/` (IaC)
- Contains: VPC, subnets, security groups, ECS cluster definition, ALB, CloudWatch log groups
- Depends on: AWS provider configuration, variable inputs
- Used by: Controller and workspace services

## Data Flow

**Bootstrap Workspace Flow:**

1. User submits workspace bootstrap form (UI layer)
2. `POST /api/workspace/bootstrap` → Node.js proxy → `POST /workspace/bootstrap` (controller)
3. Controller creates:
   - Per-workspace IAM role (`{workspaceId}-app-role`) with ECS describe + lateral movement deny
   - Multi-container task definition (`{workspaceId}-task`): landing-page + envoy
   - ECS Service (`{workspaceId}`) with desiredCount=1
   - Target group (`{workspaceId}-tg`)
   - ALB listener rule (`/workspace{id}/*` → TG)
4. Controller waits for workspace service task to reach RUNNING state
5. Controller registers workspace task IP to target group
6. For each app:
   - Register single-container task definition (`{workspaceId}-{appId}-task`)
   - Launch task via `run_task` with workspace IAM role
   - Wait for task RUNNING and extract private IP
   - `POST /internal/routes/add` to landing page → Envoy config write + SIGHUP reload
7. Returns workspace URL and per-app URLs

**Traffic Flow (Running State):**

1. Browser requests `https://builder.muhilvannan.com/workspace{id}/{appId}`
2. ALB listener rule matches `/workspace{id}/*` → forwards to target group
3. Target group contains workspace task IP (landing-page + envoy)
4. Envoy receives request on port 8080
5. Envoy routes based in-memory config:
   - `/workspace{id}/{appId}/*` → app task IP:port (with prefix rewrite to `/`)
   - `/workspace{id}` → `127.0.0.1:3001` (landing page hub)
6. Landing page serves workspace hub UI with iframe embeds to app routes

**Start/Stop App Flow:**

1. User clicks start/stop button on workspace hub
2. `POST /api/app/start` or `/api/app/stop` → Node.js proxy → controller
3. Controller:
   - For start: `POST /internal/routes/add` to landing page IP
   - For stop: `POST /internal/routes/remove` to landing page IP
4. Landing page updates in-memory routes, regenerates Envoy YAML, signals SIGHUP
5. Envoy reloads config (graceful, no traffic drop)

**State Management:**

- **Workspace state**: ECS Service (always running, desired=1) + CloudWatch logs
- **App state**: Task definitions (immutable) + running task instances (terminated on stop)
- **Route state**: In-memory map in landing-page container + Envoy YAML on shared emptyDir volume
- **IAM state**: Per-workspace role (created once, reused for all app tasks in workspace)

## Key Abstractions

**Workspace:**
- Purpose: Multi-tenant isolation unit — one service, one task, one Envoy proxy per workspace
- Examples: `controller-python/main.py` lines 161-187 (naming functions), 695-778 (bootstrap_workspace)
- Pattern: Workspace ID acts as namespace — prefixed into all resource names (service, task family, TG, IAM role)

**App:**
- Purpose: Individual containerized application within a workspace — registered as container or standalone task
- Examples: `controller-python/main.py` lines 338-385 (register_app_task_definition), 431-465 (run_app_task)
- Pattern: App ID uniquely identifies app within workspace; each app gets own task definition + running task instance

**Target Group:**
- Purpose: ALB integration point — registers workspace task IP for accepting inbound traffic
- Examples: `controller-python/main.py` lines 506-535 (ensure_workspace_target_group), 627-638 (register_workspace_to_tg)
- Pattern: Single TG per workspace, forwards all workspace paths to Envoy port 8080

**Envoy Route:**
- Purpose: Runtime-configurable L7 routing rule — maps workspace path prefix to app task IP:port
- Examples: `ui-nodejs/workspace-landing/server.js` lines 28-52 (route/cluster generation), 143-153 (add route API)
- Pattern: Routes map stored in-memory, persisted to YAML on shared volume, hot-reloaded via SIGHUP

**IAM Role:**
- Purpose: Workspace-scoped permissions boundary — all app tasks assume same role with minimal privileges
- Examples: `controller-python/main.py` lines 191-248 (create_workspace_iam_role)
- Pattern: Deny ECS task control (StopTask, RunTask) to prevent lateral movement; allow only DescribeTasks

## Entry Points

**Web UI Entry:**
- Location: `ui-nodejs/index.html`
- Triggers: Browser navigation to `http://localhost:3000`
- Responsibilities: Render workspace bootstrap form, app list, start/stop controls; proxy API requests to controller

**Web API Entry:**
- Location: `ui-nodejs/app.js`
- Triggers: HTTP requests to `/api/*` endpoints
- Responsibilities: Forward requests to controller on `http://localhost:8000`; return JSON responses

**Controller API Entry:**
- Location: `controller-python/main.py` (FastAPI app)
- Triggers: HTTP requests to `/workspace/bootstrap`, `/workspace/{id}/apps`, `/app/start`, `/app/stop`, `/health`
- Responsibilities: Orchestrate AWS resources; call Boto3 APIs; wait for task readiness; coordinate with landing page

**Landing Page Entry:**
- Location: `ui-nodejs/workspace-landing/server.js`
- Triggers: ECS task startup (part of workspace service)
- Responsibilities: Generate Envoy YAML; serve workspace hub UI; expose `/internal/routes/*` API for controller

**Envoy Entry:**
- Location: Envoy container (public.ecr.aws/envoyproxy/envoy:v1.29-latest)
- Triggers: ECS task startup (part of workspace service); SIGHUP signal on route changes
- Responsibilities: Listen on port 8080 (from ALB) + port 9901 (admin API); route HTTP requests to backends

## Error Handling

**Strategy:** Explicit exception handling with logging; controller returns 500 + error detail on failure; operations are retried with exponential backoff for task readiness

**Patterns:**

- **Task readiness**: `wait_for_task_running()` polls ECS DescribeTasks every 5 seconds (max 24 retries) before proceeding to IP registration
- **Task IP discovery**: `wait_for_task_ip()` polls for ENI private IP attachment every 5 seconds (max 12 retries)
- **IAM role exists**: `create_workspace_iam_role()` catches `EntityAlreadyExistsException` and reuses existing role (idempotent)
- **Route registration failure**: If app route fails to register with landing page, endpoint logs error but continues (partial success allowed)
- **Landing page unreachable**: `get_landing_page_ip()` returns None; controller logs warning and continues with workspace URL only
- **Envoy config write**: Landing page catches execSync errors on SIGHUP and logs warning (graceful degradation)

## Cross-Cutting Concerns

**Logging:**
- Controller: Python logging to stdout (captured by CloudWatch logs via Dockerfile)
- Landing page: Node.js console.log to stdout (captured by CloudWatch logs)
- Envoy: Proxy log level set to `warn` in start command; admin API logs to CloudWatch
- Format: Prefixed [TAG] (e.g., `[envoy-config]`, `[routes]`, `[landing-page]`)

**Validation:**
- Bootstrap payload: Pydantic `WorkspaceBootstrap` + `AppAction` models enforce required fields (workspaceId, apps)
- App config: `_app_config()` maps app type to image/port/command; defaults to `custom` if unknown
- Naming: Helper functions enforce constraints (TG name max 32 chars via `[:32]` slice)

**Authentication:**
- No per-request auth between UI and controller (same host, local development)
- AWS API auth: Boto3 uses IAM credentials from mounted `~/.aws` in controller Docker
- Landing page ↔ controller: HTTP only (internal network, no TLS)
- ALB → Envoy: HTTP only (internal, no cross-internet)

---

*Architecture analysis: 2026-03-30*
