# Testing Patterns

**Analysis Date:** 2026-03-30

## Test Framework

**Runner:**
- Not detected: No test runner configured (pytest, jest, vitest)
- No test configuration files found (no `pytest.ini`, `jest.config.js`, `vitest.config.ts`)

**Assertion Library:**
- Not applicable: No testing framework in use

**Run Commands:**
```bash
# No automated test commands
# Code relies on manual integration testing
```

## Test File Organization

**Location:**
- No test files exist in the codebase
- No `__tests__`, `test/`, `spec/` directories
- No `*.test.py`, `*.test.js`, `*.spec.py`, `*.spec.js` files

**Naming:**
- Not applicable

**Structure:**
- Not applicable

## Testing Approach

**Current State:**
- Zero automated tests detected
- No unit tests
- No integration tests
- No test fixtures or factories
- All testing appears manual via:
  - `make api-run` — starts controller in Docker
  - `make ui-start` — starts UI locally
  - Manual HTTP requests via browser or `curl`
  - AWS CLI inspection of live resources

**Development Validation:**
- Makefile provides reproducible setup: `make api-rebuild && make api-run`
- Code health relies on:
  - Type hints in Python (Pydantic models validate request structure)
  - Try-catch blocks around external API calls
  - Logging for operational visibility
  - Manual QA against live AWS infrastructure

## Code Testing Patterns

**No formal test patterns exist in codebase.**

However, defensive patterns are used throughout production code:

**Pattern 1: Retry/Polling with Timeouts**

`controller-python/main.py:577-589`:
```python
def wait_for_task_running(service_name: str, retries: int = 24, delay: int = 5) -> str | None:
    """Poll ECS service for running task (max 2 minutes)."""
    for i in range(retries):
        resp = ecs.list_tasks(
            cluster=CLUSTER,
            serviceName=service_name,
            desiredStatus="RUNNING",
        )
        if task_arns := resp.get("taskArns"):
            return task_arns[0]
        log.info("Attempt %d/%d: waiting for task...", i + 1, retries)
        time.sleep(delay)
    return None
```

This pattern validates AWS state through polling, with exponential backoff (fixed 5s intervals) and configurable max attempts.

**Pattern 2: Graceful Degradation with Exception Handling**

`controller-python/main.py:676-680`:
```python
sts = boto3.client("sts", region_name=REGION)
try:
    identity = sts.get_caller_identity()
    caller = {"account": identity["Account"], "arn": identity["Arn"]}
except Exception as e:
    caller = {"error": str(e)}
```

Non-critical operations return error info in response rather than failing the entire request.

**Pattern 3: Nested Try-Catch for Partial Success**

`controller-python/main.py:737-767`:
```python
app_results = {}
for app_def in payload.apps:
    app_id = app_def.get("name", "app")
    # ...
    try:
        app_task_def_arn = register_app_task_definition(workspace_id, app_def, app_role_arn)
        app_task_arn = run_app_task(workspace_id, app_def, app_task_def_arn, app_role_arn)
        # ...
        app_results[app_id] = {
            "url": app_url(workspace_id, app_id),
            "taskArn": app_task_arn,
            # ...
        }
    except Exception as app_exc:
        log.exception("Failed to bootstrap app %s", app_id)
        app_results[app_id] = {"error": str(app_exc)}
```

Per-app failures don't block other apps; results accumulate with success/error status per app.

**Pattern 4: Validation-First Error Handling**

`ui-nodejs/workspace-landing/server.js:143-148`:
```javascript
app.post('/internal/routes/add', (req, res) => {
  const { appId, appIP, port, basePath } = req.body;
  if (!appId || !appIP || !port) {
    return res.status(400).json({ error: 'appId, appIP, port required' });
  }
  routes[appId] = { appIP, port, basePath: basePath || `${BASE_PATH}/${appId}` };
  // ...
});
```

Request validation happens before state mutation.

## Mocking

**Framework:**
- Not used: No mocking library detected (no `unittest.mock`, `jest.mock()`, `sinon`)

**Patterns:**
- Not applicable

**What to Mock (if tests were added):**
- AWS clients (boto3.client calls for ecs, elbv2, iam, sts)
- httpx requests to landing page or external services
- File I/O for infrastructure-outputs.json
- Time.sleep() for faster test execution

**What NOT to Mock:**
- Pydantic model validation (real request structure validation)
- Environment variable loading
- Configuration parsing
- Core orchestration logic (should use integration tests against real or mocked AWS)

## Fixtures and Factories

**Test Data:**
- Not used

**Location:**
- Not applicable

## Coverage

**Requirements:**
- Not enforced: No coverage tools configured

**View Coverage:**
- Not applicable

## Test Types

**Unit Tests:**
- Not present: No isolated function testing

**Integration Tests:**
- Not present: All testing is manual against live AWS infrastructure
- Expected scope if added:
  - Bootstrap workflow: IAM role creation → task definition → service → TG → ALB rule → task startup → route registration
  - App lifecycle: start → verify running → stop → verify stopped
  - Error scenarios: Invalid payloads, AWS permission failures, task startup timeouts

**E2E Tests:**
- Not present
- Manual E2E validation through UI:
  1. User fills bootstrap form in browser
  2. POST to `/api/workspace/bootstrap` (Express proxy)
  3. Controller creates workspace resources (AWS APIs)
  4. Landing page becomes accessible via ALB
  5. Apps appear in landing page UI
  6. User can start/stop individual apps

## Validation Patterns

**Request Validation:**

Python (FastAPI + Pydantic):
```python
@app.post("/workspace/bootstrap")
def bootstrap_workspace(payload: WorkspaceBootstrap):
```
- Pydantic automatically validates `workspaceId` and `apps` structure
- Returns 422 if validation fails (FastAPI standard)

JavaScript (Manual validation):
```javascript
const { appId, appIP, port, basePath } = req.body;
if (!appId || !appIP || !port) {
  return res.status(400).json({ error: 'appId, appIP, port required' });
}
```

**AWS State Validation:**
- Polling with timeout: `wait_for_task_running()`, `wait_for_task_ip()`
- Exception handling on boto3 calls with specific exception types: `iam.exceptions.EntityAlreadyExistsException`
- Response code checks: `if resp.status_code == 200:`

## Manual Testing Workflow

**Local Development:**

1. **Setup Infrastructure:**
   ```bash
   make tf-init && make tf-plan && make tf-apply && make tf-output
   ```

2. **Start Controller API:**
   ```bash
   make api-rebuild && make api-run
   ```

3. **Start UI:**
   ```bash
   make ui-install && make ui-start
   ```

4. **Manual Testing via Browser:**
   - Navigate to `http://localhost:3000`
   - Fill workspace bootstrap form
   - Verify controller logs: `make api-logs`
   - Check AWS resources created: `aws ecs describe-services --cluster ... --services ...`

5. **Direct API Testing:**
   ```bash
   curl -X POST http://localhost:8000/workspace/bootstrap \
     -H 'Content-Type: application/json' \
     -d '{ "workspaceId": "test-1", "apps": [...] }'
   ```

## Missing Test Patterns

**Critical Gaps:**
- No regression tests: Changes to AWS orchestration logic untested
- No error scenario tests: AWS permission failures, task startup timeouts, network errors not validated
- No load testing: Performance under multiple concurrent bootstrap requests unknown
- No integration test suite: Bootstrap → start/stop → status checks not automated
- No contract tests: Controller API contracts with UI not enforced

**Recommended Testing to Add:**
1. Unit tests for naming/URL generation functions
2. Integration tests against mocked AWS (boto3 mocking)
3. E2E tests against AWS sandbox environment
4. Performance tests for long-running operations (wait_for_task_ip polling)
5. Error injection tests (simulate IAM failures, ECS API timeouts)

## Code Reliability Measures in Production

**Instead of automated tests, codebase uses:**

1. **Defensive Try-Catch:** All external API calls wrapped
2. **Logging:** Detailed logs for debugging production issues
3. **Polling with Timeout:** Eventually-consistent operations validated
4. **Graceful Degradation:** Per-app failures don't block workspace
5. **Type Safety:** Pydantic models ensure request structure
6. **Idempotency:** Most operations safe to retry (create_role catches EntityAlreadyExistsException)
7. **Manual QA:** Live AWS testing before deployment

**Risk Level:** High
- No automated regression testing
- Changes to orchestration logic untested
- AWS permission issues only caught at runtime
