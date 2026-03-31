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

REGION                = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "eu-west-1")
CLUSTER               = INFRA.get("cluster_name", "ecs-app-tester-exp-dev")
PRIVATE_SUBNETS       = INFRA.get("private_subnet_ids", [])
TASK_SG               = INFRA.get("ecs_task_security_group_id", "")
EXEC_ROLE_ARN         = INFRA.get("ecs_task_execution_role_arn", "")
WS_TASK_ROLE_ARN      = INFRA.get("ecs_workspace_task_role_arn", "")
LOG_GROUP             = INFRA.get("cloudwatch_log_group_name", "/ecs/app-tester")
VPC_ID                = INFRA.get("vpc_id", "")
CLOUDMAP_NAMESPACE_ID  = INFRA.get("cloudmap_namespace_id", "")
LANDING_PAGE_IMAGE     = INFRA.get("landing_page_ecr_uri", "")
DOMAIN                 = "builder.muhilvannan.com"

# Ports
LANDING_PAGE_PORT  = 3001

# Images
_PY      = "public.ecr.aws/docker/library/python:3.12-slim"
_NODE    = "public.ecr.aws/docker/library/node:20-slim"

# App type → (image, port, startup command)
APP_CONFIGS = {
    "streamlit": (_PY, 8501, None),   # command built dynamically
    "fastapi":   (_PY, 8000,
                  ["sh", "-c",
                   "pip install --quiet fastapi uvicorn && "
                   "python -c \""
                   "from fastapi import FastAPI; import uvicorn; "
                   "app=FastAPI(); app.get('/')(lambda: {'status':'ok'}); "
                   "uvicorn.run(app, host='0.0.0.0', port=8000)"
                   "\""]),
    "reactjs":   (_PY, 3000, None),   # command built dynamically
    "mkdocs":    (_PY, 8001, None),   # command built dynamically
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
                   f"--server.port=8501 --server.headless=true --server.address=0.0.0.0"]

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
        command = ["sh", "-c",
                   f"pip install --quiet mkdocs && "
                   f"mkdir -p /app/docs/docs && "
                   f"cat > /app/docs/mkdocs.yml << 'EOF'\n"
                   f"site_name: My Docs\n"
                   f"use_directory_urls: false\n"
                   f"EOF\n"
                   f"cat > /app/docs/docs/index.md << 'EOF'\n"
                   f"# Welcome\n\nMkDocs is running on ECS Fargate.\n"
                   f"EOF\n"
                   f"cd /app/docs && mkdocs serve --dev-addr=0.0.0.0:8001"]

    return image, port, command

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------
ecs   = boto3.client("ecs",              region_name=REGION)
elbv2 = boto3.client("elbv2",            region_name=REGION)
iam   = boto3.client("iam",             region_name=REGION)
sd    = boto3.client("servicediscovery", region_name=REGION)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class WorkspaceBootstrap(BaseModel):
    workspaceId: str
    apps: list[dict]

class AppAction(BaseModel):
    workspaceId: str
    appId: str

# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------
def workspace_service_name(workspace_id: str) -> str:
    return workspace_id

def workspace_task_family(workspace_id: str) -> str:
    """Task family for the workspace service task (landing page only)."""
    return f"{workspace_id}-task"

def app_task_family(workspace_id: str, app_id: str) -> str:
    """Task family for a standalone app task."""
    return f"{workspace_id}-{app_id}-task"

def app_task_group(workspace_id: str) -> str:
    """ECS task group tag — used to find all app tasks for a workspace."""
    return f"workspace:{workspace_id}"

def workspace_tg_name(workspace_id: str) -> str:
    return f"{workspace_id}-tg"[:32]

def cloudmap_service_name(workspace_id: str) -> str:
    """Cloud Map service name for workspace app discovery."""
    return f"{workspace_id}-apps"

def workspace_iam_role_name(workspace_id: str) -> str:
    return f"{workspace_id}-app-role"

def workspace_url(workspace_id: str) -> str:
    return f"https://{DOMAIN}/workspace{workspace_id}"

def app_url(workspace_id: str, app_id: str) -> str:
    return f"https://{DOMAIN}/workspace{workspace_id}/{app_id}"

# ---------------------------------------------------------------------------
# IAM — per-workspace app task role
# ---------------------------------------------------------------------------
def create_workspace_iam_role(workspace_id: str) -> str:
    """Create a per-workspace IAM role for app tasks.
    Scoped to ECS describe permissions only. No S3/EFS in scope for this experiment.
    Deny stop/run to prevent lateral movement between workspaces.
    """
    role_name = workspace_iam_role_name(workspace_id)

    assume_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })

    inline_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ECSDescribeOwnCluster",
                "Effect": "Allow",
                "Action": ["ecs:DescribeTasks", "ecs:DescribeTaskDefinition"],
                "Resource": "*",
                "Condition": {
                    "ArnLike": {
                        "ecs:cluster": f"arn:aws:ecs:*:*:cluster/{CLUSTER}"
                    }
                },
            },
            {
                "Sid": "DenyLateralMovement",
                "Effect": "Deny",
                "Action": ["ecs:StopTask", "ecs:RunTask", "ecs:StartTask"],
                "Resource": "*",
            },
        ],
    })

    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_policy,
            Description=f"App task role for workspace {workspace_id}",
            Tags=[{"Key": "WorkspaceId", "Value": workspace_id}],
        )
        arn = resp["Role"]["Arn"]
        log.info("Created IAM role: %s", arn)
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        log.info("IAM role already exists: %s", arn)

    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{workspace_id}-app-policy",
        PolicyDocument=inline_policy,
    )
    log.info("Applied inline policy to %s", role_name)
    return arn

# ---------------------------------------------------------------------------
# Workspace service task (landing page only)
# ---------------------------------------------------------------------------
def register_workspace_task_definition(workspace_id: str) -> str:
    """Register the workspace service task: landing-page container only (Option C: Cloud Map + Node.js proxy)."""
    family = workspace_task_family(workspace_id)
    base_path = f"/workspace{workspace_id}"

    container_defs = [
        {
            "name": "landing-page",
            "image": LANDING_PAGE_IMAGE,
            "portMappings": [{"containerPort": LANDING_PAGE_PORT, "protocol": "tcp"}],
            "essential": True,
            "environment": [
                {"name": "WORKSPACE_ID", "value": workspace_id},
                {"name": "BASE_PATH", "value": base_path},
                {"name": "DOMAIN", "value": DOMAIN},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": LOG_GROUP,
                    "awslogs-region": REGION,
                    "awslogs-stream-prefix": f"{workspace_id}/landing-page",
                },
            },
        },
    ]

    volumes = []

    log.info("Registering workspace task definition: family=%s", family)
    resp = ecs.register_task_definition(
        family=family,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="512",
        memory="1024",
        executionRoleArn=EXEC_ROLE_ARN,
        taskRoleArn=WS_TASK_ROLE_ARN,
        containerDefinitions=container_defs,
        volumes=volumes,
        tags=[{"key": "WorkspaceId", "value": workspace_id}],
    )
    arn = resp["taskDefinition"]["taskDefinitionArn"]
    log.info("Workspace task definition registered: %s", arn)
    return arn

def register_app_task_definition(workspace_id: str, app_def: dict, app_role_arn: str) -> str:
    """Register a single-container task definition for one app.
    Uses the workspace-scoped IAM role for strong isolation.
    """
    app_id   = app_def.get("name", "app")
    app_type = app_def.get("type", "custom")
    family   = app_task_family(workspace_id, app_id)
    image, port, command = _app_config(app_type, workspace_id, app_id)

    cdef: dict = {
        "name": app_id,
        "image": image,
        "portMappings": [{"containerPort": port, "protocol": "tcp"}],
        "essential": True,
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": LOG_GROUP,
                "awslogs-region": REGION,
                "awslogs-stream-prefix": f"{workspace_id}/{app_id}",
            },
        },
    }
    if command:
        cdef["command"] = command

    log.info("Registering app task definition: family=%s", family)
    resp = ecs.register_task_definition(
        family=family,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="256",
        memory="512",
        executionRoleArn=EXEC_ROLE_ARN,
        taskRoleArn=app_role_arn,
        containerDefinitions=[cdef],
        tags=[
            {"key": "WorkspaceId", "value": workspace_id},
            {"key": "AppId", "value": app_id},
            {"key": "AppType", "value": app_type},
        ],
    )
    arn = resp["taskDefinition"]["taskDefinitionArn"]
    log.info("App task definition registered: %s", arn)
    return arn

# ---------------------------------------------------------------------------
# Cloud Map — per-workspace service registry
# ---------------------------------------------------------------------------
def create_cloudmap_service(workspace_id: str) -> str:
    """Create (or return existing) Cloud Map service for workspace app discovery.
    Service name: {workspaceId}-apps  in namespace workspace-discovery.local
    FailureThreshold: 1 — auto-deregisters instances when health check fails once.
    Returns the Cloud Map service ID.
    """
    svc_name = cloudmap_service_name(workspace_id)

    # Idempotent: check if service already exists in the namespace
    try:
        paginator = sd.get_paginator("list_services")
        for page in paginator.paginate(
            Filters=[{
                "Name": "NAMESPACE_ID",
                "Values": [CLOUDMAP_NAMESPACE_ID],
                "Condition": "EQ",
            }]
        ):
            for svc in page.get("Services", []):
                if svc["Name"] == svc_name:
                    log.info("Cloud Map service already exists: %s (id=%s)", svc_name, svc["Id"])
                    return svc["Id"]
    except Exception as e:
        log.warning("Could not check existing Cloud Map services: %s", e)

    log.info("Creating Cloud Map service: %s in namespace %s", svc_name, CLOUDMAP_NAMESPACE_ID)
    resp = sd.create_service(
        Name=svc_name,
        NamespaceId=CLOUDMAP_NAMESPACE_ID,
        DnsConfig={
            "NamespaceId": CLOUDMAP_NAMESPACE_ID,
            "DnsRecords": [{"Type": "A", "TTL": 10}],
        },
        HealthCheckCustomConfig={"FailureThreshold": 1},
        Description=f"App service discovery for workspace {workspace_id}",
        Tags=[
            {"Key": "WorkspaceId", "Value": workspace_id},
            {"Key": "ManagedBy", "Value": "ecs-controller"},
        ],
    )
    svc_id = resp["Service"]["Id"]
    log.info("Cloud Map service created: %s (id=%s)", svc_name, svc_id)
    return svc_id

def get_cloudmap_service_id(workspace_id: str) -> str:
    """Look up the Cloud Map service ID for a workspace. Raises RuntimeError if not found."""
    svc_name = cloudmap_service_name(workspace_id)
    paginator = sd.get_paginator("list_services")
    for page in paginator.paginate(
        Filters=[{
            "Name": "NAMESPACE_ID",
            "Values": [CLOUDMAP_NAMESPACE_ID],
            "Condition": "EQ",
        }]
    ):
        for svc in page.get("Services", []):
            if svc["Name"] == svc_name:
                return svc["Id"]
    raise RuntimeError(f"Cloud Map service not found for workspace {workspace_id}. Bootstrap first.")

# ---------------------------------------------------------------------------
# ECS service (workspace)
# ---------------------------------------------------------------------------
def ensure_workspace_service(workspace_id: str, task_def_arn: str) -> str:
    """Create or update the workspace ECS service (landing page only).
    desiredCount=1, always running, service-scheduler managed.
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

# ---------------------------------------------------------------------------
# App tasks (run_task — standalone)
# ---------------------------------------------------------------------------
def run_app_task(workspace_id: str, app_def: dict, task_def_arn: str, app_role_arn: str) -> str | None:
    """Launch a standalone app task via run_task.
    Tagged with WorkspaceId and AppId for later lookup.
    Uses workspace-scoped IAM role for isolation.
    Note: task will NOT appear under the workspace service in ECS console.
    """
    app_id = app_def.get("name", "app")
    log.info("Launching app task: workspace=%s app=%s", workspace_id, app_id)
    resp = ecs.run_task(
        cluster=CLUSTER,
        taskDefinition=task_def_arn,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": PRIVATE_SUBNETS,
                "securityGroups": [TASK_SG],
                "assignPublicIp": "DISABLED",
            }
        },
        overrides={"taskRoleArn": app_role_arn},
        tags=[
            {"key": "WorkspaceId", "value": workspace_id},
            {"key": "AppId", "value": app_id},
        ],
        enableECSManagedTags=True,
        propagateTags="TASK_DEFINITION",
    )
    failures = resp.get("failures", [])
    if failures:
        log.warning("run_task failures: %s", failures)
        return None
    task_arn = resp["tasks"][0]["taskArn"]
    log.info("App task launched: %s", task_arn)
    return task_arn

def stop_app_task(workspace_id: str, app_id: str) -> bool:
    """Stop the running app task for a given workspace/app."""
    task_arns = _find_app_task_arns(workspace_id, app_id)
    if not task_arns:
        log.warning("No running task found for workspace=%s app=%s", workspace_id, app_id)
        return False
    for arn in task_arns:
        log.info("Stopping app task: %s", arn)
        ecs.stop_task(cluster=CLUSTER, task=arn, reason=f"app/stop called for {app_id}")
    return True

def _find_app_task_arns(workspace_id: str, app_id: str) -> list[str]:
    """Find running task ARNs for a given workspace/app by tag filter."""
    try:
        arns = ecs.list_tasks(
            cluster=CLUSTER,
            family=app_task_family(workspace_id, app_id),
            desiredStatus="RUNNING",
        ).get("taskArns", [])
        return arns
    except Exception as e:
        log.warning("Could not find app task arns: %s", e)
        return []

# ---------------------------------------------------------------------------
# Target group + ALB (1 per workspace, points to Envoy)
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

def ensure_workspace_target_group(workspace_id: str) -> str:
    """One target group per workspace, pointing at landing page port."""
    tg_name = workspace_tg_name(workspace_id)
    try:
        existing = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
        if existing:
            arn = existing[0]["TargetGroupArn"]
            log.info("Workspace TG already exists: %s", arn)
            return arn
    except elbv2.exceptions.TargetGroupNotFoundException:
        pass

    log.info("Creating workspace target group: %s port=%d", tg_name, LANDING_PAGE_PORT)
    resp = elbv2.create_target_group(
        Name=tg_name,
        Protocol="HTTP",
        Port=LANDING_PAGE_PORT,
        VpcId=VPC_ID,
        TargetType="ip",
        HealthCheckProtocol="HTTP",
        HealthCheckPath="/healthz",
        HealthCheckIntervalSeconds=30,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=3,
        Matcher={"HttpCode": "200-499"},
    )
    arn = resp["TargetGroups"][0]["TargetGroupArn"]
    log.info("Workspace TG created: %s", arn)
    return arn

def find_workspace_listener_rule(listener_arn: str, workspace_id: str) -> dict | None:
    path = f"/workspace{workspace_id}*"
    rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
    for rule in rules:
        for cond in rule.get("Conditions", []):
            if cond.get("Field") == "path-pattern" and path in cond.get("Values", []):
                return rule
    return None

def ensure_workspace_listener_rule(workspace_id: str, tg_arn: str) -> str:
    """One ALB rule per workspace: /workspace{id}/* → workspace TG (landing page).
    Always forward — landing page handles per-app routing via Cloud Map proxy.
    """
    listener_arn = get_https_listener_arn()
    if not listener_arn:
        log.warning("No HTTPS listener found — skipping listener rule")
        return ""

    existing = find_workspace_listener_rule(listener_arn, workspace_id)
    if existing:
        log.info("Workspace listener rule already exists: %s", existing["RuleArn"])
        return existing["RuleArn"]

    path = f"/workspace{workspace_id}*"
    used = {int(r["Priority"]) for r in elbv2.describe_rules(ListenerArn=listener_arn)["Rules"] if r["Priority"].isdigit()}
    priority = next(p for p in range(100, 400) if p not in used)

    log.info("Creating workspace listener rule: path=%s priority=%d", path, priority)
    resp = elbv2.create_rule(
        ListenerArn=listener_arn,
        Priority=priority,
        Conditions=[{"Field": "path-pattern", "Values": [path]}],
        Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
    )
    rule_arn = resp["Rules"][0]["RuleArn"]
    log.info("Workspace listener rule created: %s", rule_arn)
    return rule_arn

# ---------------------------------------------------------------------------
# Task IP helpers
# ---------------------------------------------------------------------------
def wait_for_task_running(service_name: str, retries: int = 24, delay: int = 5) -> str | None:
    """Wait for the workspace service scheduler to start a task. Returns task ARN."""
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

def wait_for_app_task_running(task_arn: str, retries: int = 24, delay: int = 5) -> bool:
    """Wait for a standalone run_task task to reach RUNNING."""
    for attempt in range(retries):
        try:
            tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=[task_arn])["tasks"]
            if tasks:
                status = tasks[0].get("lastStatus", "")
                if status == "RUNNING":
                    return True
                if status == "STOPPED":
                    log.warning("App task stopped: %s", tasks[0].get("stoppedReason"))
                    return False
        except Exception as e:
            log.warning("Waiting for app task RUNNING (attempt %d/%d): %s", attempt + 1, retries, e)
        time.sleep(delay)
    log.warning("Timed out waiting for app task %s", task_arn)
    return False

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

def register_workspace_to_tg(task_arn: str, tg_arn: str) -> None:
    """Register the workspace service task IP:LANDING_PAGE_PORT to the workspace TG."""
    ip = wait_for_task_ip(task_arn)
    if not ip:
        log.warning("Could not get workspace task IP — skipping TG registration")
        return
    log.info("Registering workspace task %s:%d → TG", ip, LANDING_PAGE_PORT)
    elbv2.register_targets(TargetGroupArn=tg_arn, Targets=[{"Id": ip, "Port": LANDING_PAGE_PORT}])

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
        "cluster": CLUSTER,
        "domain": DOMAIN,
        "caller_identity": caller,
        "vpc_id": VPC_ID,
        "private_subnets": PRIVATE_SUBNETS,
        "task_sg": TASK_SG,
        "exec_role_arn": EXEC_ROLE_ARN,
        "infra_loaded": bool(INFRA),
        "arch": "per-app-run_task+cloudmap",
    }

@app.post("/workspace/bootstrap")
def bootstrap_workspace(payload: WorkspaceBootstrap):
    """
    1. Create workspace-scoped IAM role for app tasks.
    2. Register workspace service task def (landing-page only).
    3. Cloud Map service (for app instance registration).
    4. Create/update workspace ECS service (desiredCount=1).
    5. Create workspace target group (→ landing page port) + ALB listener rule.
    6. Wait for workspace service task to be running, register to TG.
    7. For each app:
       a. Register single-container app task definition.
       b. run_task with workspace IAM role.
       c. Wait for task running + get IP.
       (Cloud Map registration happens via /app/start, not here)
    """
    try:
        workspace_id = payload.workspaceId

        # 1. IAM role
        app_role_arn = create_workspace_iam_role(workspace_id)

        # 2. Workspace task def (landing page only)
        workspace_task_def_arn = register_workspace_task_definition(workspace_id)

        # 3. Cloud Map service (for app instance registration)
        cloudmap_service_id = create_cloudmap_service(workspace_id)

        # 4. Workspace service
        svc_name = ensure_workspace_service(workspace_id, workspace_task_def_arn)

        # 5. TG + ALB rule
        tg_arn = ensure_workspace_target_group(workspace_id)
        ensure_workspace_listener_rule(workspace_id, tg_arn)

        # 6. Wait for workspace service task, register to TG
        log.info("Waiting for workspace service task to be running...")
        workspace_task_arn = wait_for_task_running(svc_name)
        if workspace_task_arn:
            register_workspace_to_tg(workspace_task_arn, tg_arn)
        else:
            log.warning("Workspace task did not reach RUNNING — TG registration skipped")

        # 7. Per-app: register task def, run_task
        # Note: Cloud Map registration happens via /app/start endpoint, not bootstrap
        app_results = {}
        for app_def in payload.apps:
            app_id   = app_def.get("name", "app")
            app_type = app_def.get("type", "custom")

            try:
                app_task_def_arn = register_app_task_definition(workspace_id, app_def, app_role_arn)
                app_task_arn = run_app_task(workspace_id, app_def, app_task_def_arn, app_role_arn)

                app_ip = None
                if app_task_arn:
                    running = wait_for_app_task_running(app_task_arn)
                    if running:
                        app_ip = wait_for_task_ip(app_task_arn)

                app_results[app_id] = {
                    "url": app_url(workspace_id, app_id),
                    "taskArn": app_task_arn,
                    "ip": app_ip,
                    "status": "running" if app_ip else "starting",
                }
            except Exception as app_exc:
                log.exception("Failed to bootstrap app %s", app_id)
                app_results[app_id] = {"error": str(app_exc)}

        return {
            "status": "workspace bootstrapped",
            "workspaceId": workspace_id,
            "service": svc_name,
            "cloudmapServiceId": cloudmap_service_id,
            "workspaceUrl": workspace_url(workspace_id),
            "apps": app_results,
        }
    except Exception as exc:
        log.exception("bootstrap_workspace failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/workspace/{workspace_id}/apps")
def list_workspace_apps(workspace_id: str):
    """List apps by finding run_task tasks tagged with WorkspaceId
    and cross-referencing with Cloud Map instance registration state.
    """
    try:
        # Query Cloud Map for running app instances
        try:
            discovery_resp = sd.discover_instances(
                NamespaceName="workspace-discovery.local",
                ServiceName=cloudmap_service_name(workspace_id),
                HealthStatus="HEALTHY",
                MaxResults=100,
            )
            running_app_ids = {
                inst["Attributes"].get("app_id")
                for inst in discovery_resp.get("Instances", [])
                if inst["Attributes"].get("app_id")
            }
        except Exception as e:
            log.warning("Could not query Cloud Map for workspace %s: %s", workspace_id, e)
            running_app_ids = set()

        # Find app tasks by listing task families matching {workspaceId}-*-task
        apps = []
        task_families_resp = ecs.list_task_definition_families(
            familyPrefix=f"{workspace_id}-",
            status="ACTIVE",
        )
        for family in task_families_resp.get("families", []):
            # Skip the workspace service task itself
            if family == workspace_task_family(workspace_id):
                continue
            # Extract app_id: "{workspaceId}-{appId}-task" → "{appId}"
            prefix = f"{workspace_id}-"
            suffix = "-task"
            if family.startswith(prefix) and family.endswith(suffix):
                app_id = family[len(prefix):-len(suffix)]
                in_route = app_id in running_app_ids
                task_arns = _find_app_task_arns(workspace_id, app_id)
                apps.append({
                    "appId": app_id,
                    "status": "running" if (task_arns and in_route) else "stopped",
                    "url": app_url(workspace_id, app_id),
                })

        return {"workspaceId": workspace_id, "apps": apps}
    except Exception as exc:
        log.exception("list_workspace_apps failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/app/start")
def start_app(payload: AppAction):
    """Start an app: run_task if not running, then register in Cloud Map."""
    try:
        workspace_id = payload.workspaceId
        app_id       = payload.appId

        # Check if already running
        task_arns = _find_app_task_arns(workspace_id, app_id)
        app_ip = None
        app_task_arn = None

        if task_arns:
            app_task_arn = task_arns[0]
            app_ip = wait_for_task_ip(app_task_arn, retries=3, delay=2)
            log.info("App task already running: %s ip=%s", app_task_arn, app_ip)
        else:
            # Re-run the task using the latest registered task definition
            family = app_task_family(workspace_id, app_id)
            app_role_arn = iam.get_role(RoleName=workspace_iam_role_name(workspace_id))["Role"]["Arn"]

            # Get latest task def revision
            task_defs = ecs.list_task_definitions(familyPrefix=family, sort="DESC", maxResults=1)
            if not task_defs["taskDefinitionArns"]:
                raise RuntimeError(f"No task definition found for {family}. Bootstrap workspace first.")
            task_def_arn = task_defs["taskDefinitionArns"][0]

            # Reconstruct app_def from task definition to get app type
            td = ecs.describe_task_definition(taskDefinition=task_def_arn)["taskDefinition"]
            # App type stored in task definition tags at registration time
            td_tags = {t["key"]: t["value"] for t in td.get("tags", [])}
            app_type = td_tags.get("AppType", "custom")
            app_def = {"name": app_id, "type": app_type}

            app_task_arn = run_app_task(workspace_id, app_def, task_def_arn, app_role_arn)
            if not app_task_arn:
                raise RuntimeError("run_task failed")

            running = wait_for_app_task_running(app_task_arn)
            if not running:
                raise RuntimeError("App task failed to reach RUNNING")

            app_ip = wait_for_task_ip(app_task_arn)

        if not app_ip:
            raise RuntimeError("Could not get app task IP")

        # Register in Cloud Map
        service_id = get_cloudmap_service_id(workspace_id)
        # Get port from task definition
        family = app_task_family(workspace_id, app_id)
        task_defs_resp = ecs.list_task_definitions(familyPrefix=family, sort="DESC", maxResults=1)
        td = ecs.describe_task_definition(taskDefinition=task_defs_resp["taskDefinitionArns"][0])["taskDefinition"]
        port = td["containerDefinitions"][0]["portMappings"][0]["containerPort"]

        # Cloud Map InstanceId max 64 chars — use task ID, not full ARN
        task_id = app_task_arn.split("/")[-1]
        sd.register_instance(
            ServiceId=service_id,
            InstanceId=task_id,
            Attributes={
                "AWS_INSTANCE_IPV4": app_ip,
                "AWS_INSTANCE_PORT": str(port),
                "app_id": app_id,
            },
        )
        log.info("Registered Cloud Map instance: %s → %s:%d", app_id, app_ip, port)

        return {
            "status": "app started",
            "workspaceId": workspace_id,
            "appId": app_id,
            "taskArn": app_task_arn,
            "ip": app_ip,
            "url": app_url(workspace_id, app_id),
        }
    except Exception as exc:
        log.exception("start_app failed")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/app/stop")
def stop_app(payload: AppAction):
    """Stop an app: deregister from Cloud Map first, then stop_task."""
    try:
        workspace_id = payload.workspaceId
        app_id       = payload.appId

        # Deregister from Cloud Map first (prevents traffic before task stops)
        task_arns = _find_app_task_arns(workspace_id, app_id)
        if task_arns:
            service_id = get_cloudmap_service_id(workspace_id)
            try:
                task_id = task_arns[0].split("/")[-1]
                sd.deregister_instance(ServiceId=service_id, InstanceId=task_id)
                log.info("Deregistered Cloud Map instance: %s (task %s)", app_id, task_arns[0])
            except sd.exceptions.InstanceNotFound:
                log.warning("Cloud Map instance not found for %s — already deregistered?", app_id)
            except Exception as e:
                log.warning("Cloud Map deregister failed for %s: %s", app_id, e)
        else:
            log.warning("No running task found for app %s — skipping Cloud Map deregister", app_id)

        # Stop the task
        stopped = stop_app_task(workspace_id, app_id)
        if not stopped:
            log.warning("No running task found for app %s — may already be stopped", app_id)

        return {
            "status": "app stopped",
            "workspaceId": workspace_id,
            "appId": app_id,
        }
    except Exception as exc:
        log.exception("stop_app failed")
        raise HTTPException(status_code=500, detail=str(exc))
