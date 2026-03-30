# Coding Conventions

**Analysis Date:** 2026-03-30

## Naming Patterns

**Files:**
- Python: `snake_case` (e.g., `main.py`, `__pycache__`)
- JavaScript: `camelCase` or `kebab-case` for scripts (e.g., `app.js`, `server.js`, `index.html`)
- Terraform: `snake_case.tf` (e.g., `main.tf`, `variables.tf`, `outputs.tf`)
- Dockerfiles: Capitalized, single file `Dockerfile` with optional suffixes (e.g., `Dockerfile`, `Dockerfile.xxx`)

**Functions/Methods:**
- Python: `snake_case` for all functions, including helper functions (e.g., `_load_infra()`, `create_workspace_iam_role()`, `register_workspace_task_definition()`)
- JavaScript: `camelCase` for function declarations (e.g., `buildEnvoyConfig()`, `writeEnvoyConfig()`, `reloadEnvoy()`)
- Private/internal functions prefixed with `_`: `_load_infra()`, `_app_config()`, `_find_app_task_arns()`

**Variables/Constants:**
- Python constants: `UPPER_SNAKE_CASE` at module level (e.g., `INFRA_OUTPUTS_PATH`, `REGION`, `CLUSTER`, `ENVOY_PORT`, `LOG_GROUP`)
- Python variables: `snake_case` (e.g., `workspace_id`, `app_id`, `role_name`, `task_def_arn`)
- JavaScript constants: `UPPER_SNAKE_CASE` at module level (e.g., `WORKSPACE_ID`, `BASE_PATH`, `DOMAIN`, `ENVOY_ADMIN_PORT`, `PORT`, `ENVOY_CONFIG`)
- JavaScript variables: `camelCase` (e.g., `workspaceId`, `basePath`, `appId`, `routes`)
- Environment variables: `UPPER_SNAKE_CASE` (e.g., `AWS_DEFAULT_REGION`, `INFRA_OUTPUTS`, `WORKSPACE_ID`)

**Types/Models:**
- Python Pydantic models: `PascalCase` (e.g., `WorkspaceBootstrap`, `AppAction`)
- TypeScript types: Not currently in use
- AWS resource names: `snake-case` or `kebab-case` for infrastructure identifiers (e.g., `ecs-app-tester-exp-dev`, `ecs-task-security-group-id`)

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `.eslintrc`, or `black` config detected)
- Python: Standard Python style appears to follow PEP 8 implicitly
- JavaScript: Standard Express.js style with no enforced formatter
- Line length: No visible strict limit enforced; Python code maintains readability with ~100 character lines
- Indentation: 4 spaces (Python), 2 spaces (JavaScript/HTML)

**Linting:**
- No linting tools detected in configuration
- Code relies on manual review and convention adherence

## Import Organization

**Python Order:**
1. Standard library imports: `import json`, `import logging`, `import os`, `import time`
2. Third-party framework imports: `from fastapi import FastAPI, HTTPException`, `from pydantic import BaseModel`
3. AWS SDK imports: `import boto3`, `import httpx`
4. Local imports: Not applicable (single-file controller)

**JavaScript Order:**
1. Core Node modules: `const express = require('express')`, `const fs = require('fs')`, `const path = require('path')`
2. Standard library utilities: `const { execSync } = require('child_process')`
3. Local initialization: `const app = express()`, middleware setup

**Path Aliases:**
- No path aliases or custom import paths used
- Direct relative imports: `require('./index.html')`, `path.join(__dirname, ...)`

## Error Handling

**Patterns in Python (`controller-python/main.py`):**
- Try-except blocks with specific exception types where possible: `except iam.exceptions.EntityAlreadyExistsException`
- Generic `except Exception as e:` fallback with logging: `log.exception("bootstrap_workspace failed")`
- Return values for failure cases: Functions return `bool` or `None` on error (e.g., `wait_for_task_running()` returns `str | None`)
- HTTPException for API errors: `raise HTTPException(status_code=500, detail=str(exc))`
- Detailed logging of exceptions: `log.exception(msg)` for full traceback, `log.warning(msg)` for recoverable errors

Example pattern (`controller-python/main.py:709-778`):
```python
@app.post("/workspace/bootstrap")
def bootstrap_workspace(payload: WorkspaceBootstrap):
    try:
        # Main logic
        workspace_id = payload.workspaceId
        # ... multiple steps with nested try-except ...
        for app_def in payload.apps:
            try:
                # Per-app logic
                app_results[app_id] = { ... }
            except Exception as app_exc:
                log.exception("Failed to bootstrap app %s", app_id)
                app_results[app_id] = {"error": str(app_exc)}
        return { ... }
    except Exception as exc:
        log.exception("bootstrap_workspace failed")
        raise HTTPException(status_code=500, detail=str(exc))
```

**Patterns in JavaScript:**
- Simple try-catch blocks with `.json()` parsing: `try { const result = await controllerResponse.json(); } catch (error) { res.status(500).json({ error: error.message }); }`
- No HTTPException equivalent; raw HTTP status codes (e.g., `res.status(400)`, `res.status(500)`)
- Inline validation with 400 responses: `if (!appId || !appIP || !port) { return res.status(400).json({ error: 'appId, appIP, port required' }); }`
- Console logging for operational events: `console.log('[prefix] message')`

## Logging

**Framework:**
- Python: Built-in `logging` module with `basicConfig`
- JavaScript: `console.log()` for all output

**Python Logging Setup (`controller-python/main.py:10-11`):**
```python
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
```

**Patterns:**
- Prefixed console output: `[INFO]`, `[WARNING]`, `[ERROR]`
- Contextual messages with structured arguments: `log.info("Created IAM role: %s", arn)`
- Exception logging with traceback: `log.exception("bootstrap_workspace failed")` (automatically includes traceback)
- Warnings for non-fatal issues: `log.warning("Could not load infra outputs: %s — set INFRA_OUTPUTS env var", e)`

**JavaScript Logging Patterns:**
- Prefixed console output: `console.log('[landing-page] message')`, `console.log('[routes] message')`, `console.log('[envoy-config] message')`
- Category prefixes in brackets: `[envoy-reload]`, `[envoy-config]`, `[healthz]`
- Simple string concatenation: `console.log(\`[landing-page] Workspace ${WORKSPACE_ID} hub listening on port ${PORT}\`)`
- Warning output: `console.warn('[envoy-reload] Could not signal envoy:', e.message)`

## Comments

**When to Comment:**
- Architecture-level comments for complex logic flows
- Section headers for functional grouping (seen in Python: `# ---------------------------------------------------------------------------` separator blocks)
- Inline comments for non-obvious AWS API usage or configuration logic
- Docstrings for key functions with complex return values

**JSDoc/TSDoc:**
- Python docstrings used for function documentation (e.g., `"""Task family for the workspace service task (landing page + envoy)."""`)
- JavaScript: No JSDoc comments detected; functions are self-documenting through clear names
- Architecture notes in comments at top of sections (e.g., `# In-memory route table: { [appId]: { appIP, port, basePath } }`)

**Example from `controller-python/main.py:164-166`:**
```python
def workspace_task_family(workspace_id: str) -> str:
    """Task family for the workspace service task (landing page + envoy)."""
    return f"{workspace_id}-task"
```

**Example from `ui-nodejs/workspace-landing/server.js:16-19`:**
```javascript
// ---------------------------------------------------------------------------
// In-memory route table: { [appId]: { appIP, port, basePath } }
// ---------------------------------------------------------------------------
const routes = {};
```

## Function Design

**Size:**
- Python functions range from 1-2 lines (helpers like `workspace_service_name()`) to 80+ lines (orchestration functions like `bootstrap_workspace()`)
- Large functions decomposed logically with section comments but not extracted into separate modules
- JavaScript functions similarly range from small helpers to larger handlers (200+ lines for `buildEnvoyConfig()`)

**Parameters:**
- Python: Type hints used for all parameters and return types (e.g., `def _load_infra() -> dict:`, `def create_workspace_iam_role(workspace_id: str) -> str:`)
- Named parameters over positional for clarity: `iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=...)`
- Optional parameters with defaults: `def wait_for_task_running(service_name: str, retries: int = 24, delay: int = 5) -> str | None:`
- JavaScript: No type hints; parameter validation inline within function bodies

**Return Values:**
- Python: Union types for optional returns (e.g., `-> str | None`, `-> bool`)
- Python: Return dicts for complex results (e.g., bootstrap returns `{ "status": "workspace bootstrapped", "workspaceId": ..., "apps": {...} }`)
- JavaScript: Callbacks and JSON responses; async/await pattern with `.json()` parsing
- Early returns for error conditions: `if (!appId) { return res.status(400).json(...); }`

## Module Design

**Exports:**
- Python: Single-module architecture (`controller-python/main.py`) — all functions at module level
- JavaScript: Express app exported implicitly; handlers defined inline
- No barrel files or re-exports

**File Organization:**
- Python: Logically grouped by concern with separator comments:
  - Config loading
  - AWS clients
  - Models (Pydantic)
  - Naming functions
  - IAM functions
  - Task definition functions
  - Service/task orchestration
  - Target group/ALB functions
  - Wait/polling functions
  - App route management
  - API routes

- JavaScript: Express app setup → middleware → routes → start server

**Initialization Patterns:**
- Python: Module-level code executed at import time (`INFRA = _load_infra()`, `ecs = boto3.client(...)`)
- JavaScript: Module-level constants, then route definitions, then `app.listen()`
- Environment variables loaded at startup: `os.environ.get()`, `process.env.XXX`

## Pydantic Models

**Request/Response Models:**
- Simple Pydantic BaseModel subclasses for request validation
- Used only for API endpoint input validation: `WorkspaceBootstrap`, `AppAction`
- No response models defined; responses are plain dicts

Example from `controller-python/main.py:150-155`:
```python
class WorkspaceBootstrap(BaseModel):
    workspaceId: str
    apps: list[dict]

class AppAction(BaseModel):
    workspaceId: str
    appId: str
```

## Testing & Development Conventions

**Development Workflow:**
- Makefile-driven: `make api-build`, `make api-run`, `make api-rebuild`
- Docker-first: Code runs in containers, not locally
- Configuration via mounted files and environment variables
- No local development environment setup beyond Docker

**Code Reliability:**
- Defensive programming with try-catch blocks around external calls (boto3, httpx)
- Retry logic and polling for eventually-consistent operations: `wait_for_task_running()`, `wait_for_task_ip()`
- No assertions or unit tests in codebase; integration assumptions baked in
