from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
import json
import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()

# ---------------------------------------------------------------------------
# Config — loaded from mounted infrastructure-outputs.json
# ---------------------------------------------------------------------------
INFRA_OUTPUTS_PATH = os.environ.get("INFRA_OUTPUTS", "/app/infra/infrastructure-outputs.json")

def _load_infra() -> dict:
    with open(INFRA_OUTPUTS_PATH) as f:
        raw = json.load(f)
    return {k: v["value"] for k, v in raw.items()}

try:
    INFRA = _load_infra()
    log.info("Loaded infrastructure outputs from %s", INFRA_OUTPUTS_PATH)
except Exception as e:
    log.warning("Could not load infra outputs: %s — set INFRA_OUTPUTS env var", e)
    INFRA = {}

REGION          = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "eu-west-1")
CLUSTER         = INFRA.get("cluster_name", "ecs-app-tester-dev")
PRIVATE_SUBNETS = INFRA.get("private_subnet_ids", [])
TASK_SG         = INFRA.get("ecs_task_security_group_id", "")
EXEC_ROLE_ARN   = INFRA.get("ecs_task_execution_role_arn", "")
TASK_ROLE_ARN   = INFRA.get("ecs_workspace_task_role_arn", "")
LOG_GROUP       = INFRA.get("cloudwatch_log_group_name", "/ecs/app-tester")
VPC_ID          = INFRA.get("vpc_id", "")
DOMAIN          = "brewer.muhilvannan.com"

# App type → (image, port, startup command)
# public.ecr.aws mirror — no auth required on Fargate
_PY = "public.ecr.aws/docker/library/python:3.12-slim"

APP_CONFIGS = {
    "streamlit": (_PY, 8501, None),  # command built dynamically with base URL path
    "fastapi":   (_PY, 8000,
                  ["sh", "-c",
                   "pip install --quiet fastapi uvicorn && "
                   "python -c \""
                   "from fastapi import FastAPI; import uvicorn; "
                   "app=FastAPI(); app.get('/')(lambda: {'status':'ok'}); "
                   "uvicorn.run(app, host='0.0.0.0', port=8000)"
                   "\""]),
    "reactjs":   (_PY, 3000, None),   # command built dynamically with base URL path
    "mkdocs":    (_PY, 8001, None),   # command built dynamically with base URL path
    "custom":    (_PY, 8080,
                  ["python", "-c", "import time; time.sleep(86400)"]),
}

def _app_config(app_type: str, workspace_id: str = "", app_id: str = ""):
    image, port, command = APP_CONFIGS.get(app_type, APP_CONFIGS["custom"])
    if not (workspace_id and app_id):
        return image, port, command

    base_path = f"/workspace{workspace_id}/{app_id}"

    if app_type == "streamlit":
        command = ["sh", "-c",
                   f"pip install --quiet streamlit && "
                   f"python -m streamlit hello "
                   f"--server.port=8501 --server.headless=true --server.address=0.0.0.0 "
                   f"--server.baseUrlPath={base_path}"]

    elif app_type == "reactjs":
        command = ["sh", "-c",
                   f"mkdir -p /app/web && "
                   f"cat > /app/web/index.html << 'HTMLEOF'\n"
                   f"<!DOCTYPE html><html><head><title>React App</title>"
                   f"<script src=\"https://unpkg.com/react@18/umd/react.development.js\"></script>"
                   f"<script src=\"https://unpkg.com/react-dom@18/umd/react-dom.development.js\"></script>"
                   f"<style>body{{font-family:sans-serif;display:flex;align-items:center;"
                   f"justify-content:center;min-height:100vh;margin:0;"
                   f"background:#0f1117;color:#e2e8f0;}}</style>"
                   f"</head><body><div id='root'></div>"
                   f"<script>ReactDOM.createRoot(document.getElementById('root')).render("
                   f"React.createElement('div',null,"
                   f"React.createElement('h1',null,'React App'),"
                   f"React.createElement('p',null,'Running on ECS Fargate')"
                   f"));</script></body></html>\n"
                   f"HTMLEOF\n"
                   f"python - << 'PYEOF'\n"
                   f"import http.server, os\n"
                   f"os.chdir('/app/web')\n"
                   f"BASE = '{base_path}'\n"
                   f"class H(http.server.SimpleHTTPRequestHandler):\n"
                   f"    def translate_path(self, path):\n"
                   f"        if path.startswith(BASE + '/'): path = path[len(BASE):]\n"
                   f"        elif path == BASE: path = '/'\n"
                   f"        return super().translate_path(path)\n"
                   f"    def log_message(self, *a): pass\n"
                   f"http.server.HTTPServer(('0.0.0.0', 3000), H).serve_forever()\n"
                   f"PYEOF"]

    elif app_type == "mkdocs":
        # Build site with correct site_url so links resolve, serve with prefix stripping
        command = ["sh", "-c",
                   f"pip install --quiet mkdocs && "
                   f"mkdir -p /app/docs/docs && "
                   f"cat > /app/docs/mkdocs.yml << 'EOF'\n"
                   f"site_name: My Docs\n"
                   f"site_url: https://{DOMAIN}{base_path}/\n"
                   f"use_directory_urls: true\n"
                   f"EOF\n"
                   f"cat > /app/docs/docs/index.md << 'EOF'\n"
                   f"# Welcome\n\nMkDocs is running on ECS Fargate.\n"
                   f"EOF\n"
                   f"cd /app/docs && mkdocs build --quiet && "
                   f"python - << 'PYEOF'\n"
                   f"import http.server, os\n"
                   f"os.chdir('/app/docs/site')\n"
                   f"BASE = '{base_path}'\n"
                   f"class H(http.server.SimpleHTTPRequestHandler):\n"
                   f"    def translate_path(self, path):\n"
                   f"        if path.startswith(BASE + '/'): path = path[len(BASE):]\n"
                   f"        elif path == BASE: path = '/'\n"
                   f"        return super().translate_path(path)\n"
                   f"    def log_message(self, *a): pass\n"
                   f"http.server.HTTPServer(('0.0.0.0', 8001), H).serve_forever()\n"
                   f"PYEOF"]

    return image, port, command

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------
ecs   = boto3.client("ecs",   region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)
iam   = boto3.client("iam",   region_name=REGION)
s3    = boto3.client("s3",    region_name=REGION)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class WorkspaceBootstrap(BaseModel):
    workspaceId: str
    s3Bucket: str | None = None
    apps: list[dict]

class AppAction(BaseModel):
    workspaceId: str
    appId: str

class AppSync(BaseModel):
    workspaceId: str
    appId: str
    s3Bucket: str
    s3Prefix: str | None = None

# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------
def workspace_service_name(workspace_id: str) -> str:
    """ECS service name = workspace ID (1 service per workspace)."""
    return workspace_id

def workspace_task_family(workspace_id: str) -> str:
    """ECS task definition family for the workspace multi-container task."""
    return f"{workspace_id}-task"

def app_tg_name(workspace_id: str, app_id: str) -> str:
    return f"{workspace_id}-{app_id}-tg"[:32]

def app_url(workspace_id: str, app_id: str) -> str:
    return f"https://{DOMAIN}/workspace{workspace_id}/{app_id}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_https_listener_arn() -> str | None:
    try:
        lbs = elbv2.describe_load_balancers()["LoadBalancers"]
        alb = next((lb for lb in lbs if "ecs-app-tester" in lb["LoadBalancerName"]), None)
        if not alb:
            return None
        listeners = elbv2.describe_listeners(LoadBalancerArn=alb["LoadBalancerArn"])["Listeners"]
        https = next((l for l in listeners if l["Port"] == 443), None)
        return https["ListenerArn"] if https else None
    except Exception as e:
        log.warning("Could not resolve HTTPS listener: %s", e)
        return None

def register_workspace_task_definition(workspace_id: str, apps: list[dict]) -> str:
    """Register a multi-container task definition — one container per app.
    All containers share the same task (same ENI/IP). Each app has its own port.
    This is required so all apps appear under a single ECS service in the console.
    """
    family = workspace_task_family(workspace_id)
    container_defs = []
    for app_def in apps:
        app_id   = app_def.get("name", "app")
        app_type = app_def.get("type", "custom")
        image, port, command = _app_config(app_type, workspace_id, app_id)
        cdef: dict = {
            "name": app_id,
            "image": image,
            "portMappings": [{"containerPort": port, "protocol": "tcp"}],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group":         LOG_GROUP,
                    "awslogs-region":        REGION,
                    "awslogs-stream-prefix": f"{workspace_id}/{app_id}",
                },
            },
            "essential": True,
        }
        if command:
            cdef["command"] = command
        container_defs.append(cdef)

    log.info("Registering task definition: family=%s containers=%s", family, [c["name"] for c in container_defs])
    resp = ecs.register_task_definition(
        family=family,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="512",
        memory="1024",
        executionRoleArn=EXEC_ROLE_ARN,
        taskRoleArn=TASK_ROLE_ARN,
        containerDefinitions=container_defs,
        tags=[{"key": "WorkspaceId", "value": workspace_id}],
    )
    arn = resp["taskDefinition"]["taskDefinitionArn"]
    log.info("Task definition registered: %s", arn)
    return arn

def ensure_workspace_service(workspace_id: str, task_def_arn: str) -> str:
    """Create or update the workspace ECS service (desiredCount=1, always running).
    The service scheduler launches the task — this is what makes it visible in the
    ECS console under the service, not as a standalone task.
    """
    name = workspace_service_name(workspace_id)

    resp = ecs.describe_services(cluster=CLUSTER, services=[name])
    for svc in resp.get("services", []):
        if svc["status"] == "ACTIVE":
            log.info("Updating workspace service %s with new task def", name)
            ecs.update_service(cluster=CLUSTER, service=name, taskDefinition=task_def_arn, desiredCount=1)
            return name
        elif svc["status"] in ("DRAINING", "INACTIVE"):
            log.info("Service %s is %s — deleting and recreating", name, svc["status"])
            try:
                ecs.update_service(cluster=CLUSTER, service=name, desiredCount=0)
            except Exception:
                pass
            ecs.delete_service(cluster=CLUSTER, service=name, force=True)
            time.sleep(3)

    log.info("Creating workspace service: %s (desiredCount=1)", name)
    ecs.create_service(
        cluster=CLUSTER,
        serviceName=name,
        taskDefinition=task_def_arn,
        desiredCount=1,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": PRIVATE_SUBNETS,
                "securityGroups": [TASK_SG],
                "assignPublicIp": "DISABLED",
            }
        },
        tags=[{"key": "WorkspaceId", "value": workspace_id}],
        enableECSManagedTags=True,
    )
    log.info("Workspace service created: %s", name)
    return name

def ensure_target_group(workspace_id: str, app_id: str, port: int) -> str:
    tg_name = app_tg_name(workspace_id, app_id)
    try:
        existing = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
        if existing:
            arn = existing[0]["TargetGroupArn"]
            log.info("Target group already exists: %s", arn)
            return arn
    except elbv2.exceptions.TargetGroupNotFoundException:
        pass

    log.info("Creating target group: %s port=%d", tg_name, port)
    resp = elbv2.create_target_group(
        Name=tg_name,
        Protocol="HTTP",
        Port=port,
        VpcId=VPC_ID,
        TargetType="ip",
        HealthCheckProtocol="HTTP",
        HealthCheckPath="/",
        HealthCheckIntervalSeconds=30,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=3,
        Matcher={"HttpCode": "200-499"},
    )
    arn = resp["TargetGroups"][0]["TargetGroupArn"]
    log.info("Target group created: %s", arn)
    return arn

def find_listener_rule(listener_arn: str, workspace_id: str, app_id: str) -> dict | None:
    path = f"/workspace{workspace_id}/{app_id}*"
    rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
    for rule in rules:
        for cond in rule.get("Conditions", []):
            if cond.get("Field") == "path-pattern" and path in cond.get("Values", []):
                return rule
    return None

def ensure_listener_rule(workspace_id: str, app_id: str, tg_arn: str, enabled: bool = False) -> str:
    """Create listener rule as fixed-response 503 (disabled) by default."""
    listener_arn = get_https_listener_arn()
    if not listener_arn:
        log.warning("No HTTPS listener found — skipping listener rule")
        return ""

    existing = find_listener_rule(listener_arn, workspace_id, app_id)
    if existing:
        log.info("Listener rule already exists: %s", existing["RuleArn"])
        return existing["RuleArn"]

    path = f"/workspace{workspace_id}/{app_id}*"
    used = {int(r["Priority"]) for r in elbv2.describe_rules(ListenerArn=listener_arn)["Rules"] if r["Priority"].isdigit()}
    priority = next(p for p in range(100, 400) if p not in used)

    action = _forward_action(tg_arn) if enabled else _disabled_action()
    log.info("Creating listener rule: path=%s priority=%d enabled=%s", path, priority, enabled)
    resp = elbv2.create_rule(
        ListenerArn=listener_arn,
        Priority=priority,
        Conditions=[{"Field": "path-pattern", "Values": [path]}],
        Actions=[action],
    )
    rule_arn = resp["Rules"][0]["RuleArn"]
    log.info("Listener rule created: %s", rule_arn)
    return rule_arn

def _forward_action(tg_arn: str) -> dict:
    return {"Type": "forward", "TargetGroupArn": tg_arn}

def _disabled_action() -> dict:
    return {
        "Type": "fixed-response",
        "FixedResponseConfig": {
            "StatusCode": "503",
            "ContentType": "text/plain",
            "MessageBody": "App is stopped",
        },
    }

def set_app_rule_enabled(workspace_id: str, app_id: str, enabled: bool) -> bool:
    listener_arn = get_https_listener_arn()
    if not listener_arn:
        log.warning("No HTTPS listener — cannot toggle rule")
        return False

    rule = find_listener_rule(listener_arn, workspace_id, app_id)
    if not rule:
        log.warning("No listener rule found for workspace=%s app=%s", workspace_id, app_id)
        return False

    tg_arn = None
    try:
        tg_name = app_tg_name(workspace_id, app_id)
        tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
        if tgs:
            tg_arn = tgs[0]["TargetGroupArn"]
    except Exception:
        pass

    action = _forward_action(tg_arn) if (enabled and tg_arn) else _disabled_action()
    log.info("Setting rule %s enabled=%s", rule["RuleArn"], enabled)
    elbv2.modify_rule(RuleArn=rule["RuleArn"], Actions=[action])
    return True

def wait_for_task_running(service_name: str, retries: int = 24, delay: int = 5) -> str | None:
    """Wait for the service scheduler to start a task. Returns task ARN."""
    for attempt in range(retries):
        try:
            task_arns = ecs.list_tasks(cluster=CLUSTER, serviceName=service_name, desiredStatus="RUNNING").get("taskArns", [])
            if task_arns:
                log.info("Task running: %s", task_arns[0])
                return task_arns[0]
        except Exception as e:
            log.warning("Waiting for task (attempt %d/%d): %s", attempt + 1, retries, e)
        time.sleep(delay)
    log.warning("Timed out waiting for task for service %s", service_name)
    return None

def wait_for_task_ip(task_arn: str, retries: int = 12, delay: int = 5) -> str | None:
    for attempt in range(retries):
        try:
            task = ecs.describe_tasks(cluster=CLUSTER, tasks=[task_arn])["tasks"][0]
            if task.get("lastStatus") == "STOPPED":
                log.warning("Task stopped: %s", task.get("stoppedReason"))
                return None
            for attachment in task.get("attachments", []):
                if attachment["type"] == "ElasticNetworkInterface":
                    for detail in attachment["details"]:
                        if detail["name"] == "privateIPv4Address":
                            return detail["value"]
        except Exception as e:
            log.warning("Waiting for task IP (attempt %d/%d): %s", attempt + 1, retries, e)
        time.sleep(delay)
    log.warning("Timed out waiting for IP for task %s", task_arn)
    return None

def register_task_to_tgs(task_arn: str, workspace_id: str, apps: list[dict]) -> None:
    """Get task's private IP and register it to each app's target group."""
    ip = wait_for_task_ip(task_arn)
    if not ip:
        log.warning("Could not get task IP — skipping TG registration")
        return
    for app_def in apps:
        app_id   = app_def.get("name", "app")
        app_type = app_def.get("type", "custom")
        _, port, _ = _app_config(app_type)
        try:
            tg_arn = ensure_target_group(workspace_id, app_id, port)
            log.info("Registering %s:%d → %s", ip, port, app_id)
            elbv2.register_targets(TargetGroupArn=tg_arn, Targets=[{"Id": ip, "Port": port}])
        except Exception as e:
            log.warning("Failed to register target for %s: %s", app_id, e)

def attach_s3_policy(workspace_id: str, bucket: str) -> None:
    policy_name = f"{workspace_id}-s3-access"
    policy_doc = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetObjectVersion"],
            "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
        }],
    })
    role_name = TASK_ROLE_ARN.split("/")[-1]
    log.info("Attaching S3 policy %s to role %s", policy_name, role_name)
    try:
        iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=policy_doc)
    except Exception as e:
        log.warning("Could not attach S3 policy: %s", e)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    sts = boto3.client("sts", region_name=REGION)
    try:
        identity = sts.get_caller_identity()
        caller = {"account": identity["Account"], "arn": identity["Arn"]}
    except Exception as e:
        caller = {"error": str(e)}
    return {
        "status": "ok",
        "region": REGION,
        "caller_identity": caller,
        "cluster": CLUSTER,
        "vpc_id": VPC_ID,
        "private_subnets": PRIVATE_SUBNETS,
        "task_sg": TASK_SG,
        "exec_role_arn": EXEC_ROLE_ARN,
        "infra_loaded": bool(INFRA),
    }

@app.post("/workspace/bootstrap")
def bootstrap_workspace(payload: WorkspaceBootstrap):
    """
    1. Register a multi-container task def — one container per app, one task total.
       All containers share the same ENI so they appear under one service in ECS console.
    2. Create/update workspace ECS service (desiredCount=1, always running).
       The service scheduler launches the task — mandatory for console visibility.
    3. Create target groups + disabled ALB listener rules per app.
    4. Wait for task running, register task IP to all TGs.
    """
    try:
        if payload.s3Bucket:
            attach_s3_policy(payload.workspaceId, payload.s3Bucket)

        task_def_arn = register_workspace_task_definition(payload.workspaceId, payload.apps)
        svc_name = ensure_workspace_service(payload.workspaceId, task_def_arn)

        for app_def in payload.apps:
            app_id   = app_def.get("name", "app")
            app_type = app_def.get("type", "custom")
            _, port, _ = _app_config(app_type)
            tg_arn = ensure_target_group(payload.workspaceId, app_id, port)
            ensure_listener_rule(payload.workspaceId, app_id, tg_arn, enabled=False)

        log.info("Waiting for workspace service task to be running...")
        task_arn = wait_for_task_running(svc_name)
        if task_arn:
            register_task_to_tgs(task_arn, payload.workspaceId, payload.apps)
        else:
            log.warning("Task did not reach RUNNING — TG registration skipped")

        return {
            "status": "workspace bootstrapped",
            "workspaceId": payload.workspaceId,
            "service": svc_name,
            "apps": {
                app_def.get("name", "app"): {
                    "url": app_url(payload.workspaceId, app_def.get("name", "app")),
                    "status": "stopped (call /app/start to enable)",
                }
                for app_def in payload.apps
            },
        }
    except Exception as exc:
        log.exception("bootstrap_workspace failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/workspace/{workspace_id}/apps")
def list_workspace_apps(workspace_id: str):
    """List apps by inspecting the running service task's containers and ALB rule states."""
    try:
        task_arns = ecs.list_tasks(
            cluster=CLUSTER, serviceName=workspace_id, desiredStatus="RUNNING"
        ).get("taskArns", [])

        if not task_arns:
            return {"workspaceId": workspace_id, "apps": []}

        tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=task_arns[:1])["tasks"]
        if not tasks:
            return {"workspaceId": workspace_id, "apps": []}

        task = tasks[0]
        container_names = [c["name"] for c in task.get("containers", [])]

        listener_arn = get_https_listener_arn()
        apps = []
        for app_id in container_names:
            status = "stopped"
            if listener_arn:
                rule = find_listener_rule(listener_arn, workspace_id, app_id)
                if rule:
                    action_type = rule.get("Actions", [{}])[0].get("Type", "")
                    status = "running" if action_type == "forward" else "stopped"
            apps.append({
                "appId":  app_id,
                "status": status,
                "url":    app_url(workspace_id, app_id),
            })

        return {"workspaceId": workspace_id, "apps": apps}
    except Exception as exc:
        log.exception("list_workspace_apps failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/app/start")
def start_app(payload: AppAction):
    """Enable the ALB listener rule → traffic flows to the app container."""
    try:
        ok = set_app_rule_enabled(payload.workspaceId, payload.appId, enabled=True)
        if not ok:
            raise RuntimeError(
                f"No listener rule for workspace={payload.workspaceId} app={payload.appId}. Run bootstrap first."
            )
        return {
            "status": "app started",
            "workspaceId": payload.workspaceId,
            "appId": payload.appId,
            "url": app_url(payload.workspaceId, payload.appId),
        }
    except Exception as exc:
        log.exception("start_app failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/app/stop")
def stop_app(payload: AppAction):
    """Disable the ALB listener rule → 503 returned. Container keeps running."""
    try:
        ok = set_app_rule_enabled(payload.workspaceId, payload.appId, enabled=False)
        if not ok:
            raise RuntimeError(
                f"No listener rule for workspace={payload.workspaceId} app={payload.appId}."
            )
        return {
            "status": "app stopped",
            "workspaceId": payload.workspaceId,
            "appId": payload.appId,
        }
    except Exception as exc:
        log.exception("stop_app failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.put("/app/sync")
def sync_app(payload: AppSync):
    try:
        prefix = payload.s3Prefix or ""
        log.info("Syncing s3://%s/%s → workspace=%s app=%s", payload.s3Bucket, prefix, payload.workspaceId, payload.appId)
        paginator = s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=payload.s3Bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        log.info("Found %d objects to sync", len(keys))
        return {
            "status": "sync queued",
            "workspaceId": payload.workspaceId,
            "appId": payload.appId,
            "objects_found": len(keys),
        }
    except Exception as exc:
        log.exception("sync_app failed")
        raise HTTPException(status_code=500, detail=str(exc))
