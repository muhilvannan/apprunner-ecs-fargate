# Phase 02-01 Execution Summary (Retrospective)

**Status:** ✅ COMPLETE (delivered as architectural pivot from plan)
**Wave:** 1 (Controller Scaffold)
**Plan intent:** Node.js/Express scaffold with AWS SDK v3

## What Was Actually Built

The controller was implemented in **Python 3.12 / FastAPI / Boto3** — not Node.js. The decision was made early to avoid an extra runtime layer; Python with boto3 is the canonical AWS SDK and FastAPI provides equivalent HTTP ergonomics to Express.

### Files Created

| File | Purpose |
|------|---------|
| `controller-python/main.py` | FastAPI app — all AWS logic, endpoints |
| `controller-python/Dockerfile` | `python:3.12-slim`, port 8000 |
| `controller-python/entrypoint.sh` | Minimal `exec "$@"` passthrough |
| `controller-python/requirements.txt` | fastapi, uvicorn, boto3, pydantic |
| `controller-python/Makefile` | build / run / stop / logs targets |

### Docker Runtime

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py entrypoint.sh ./
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Mounted at runtime:
- `~/.aws:/root/.aws:ro` — AWS credentials
- `../infrastructure-outputs.json:/app/infra/infrastructure-outputs.json:ro` — Terraform outputs

### Health Endpoint

`GET /health` returns AWS caller identity (via STS) + loaded infra config:

```json
{
  "status": "ok",
  "region": "eu-west-1",
  "caller_identity": { "account": "...", "arn": "..." },
  "cluster": "ecs-app-tester-dev",
  "vpc_id": "vpc-...",
  "infra_loaded": true
}
```

## Pivot from Plan

| Planned (02-01-PLAN.md) | Actual |
|------------------------|--------|
| Node.js 20 + Express | Python 3.12 + FastAPI |
| AWS SDK v3 (@aws-sdk/client-ecs etc.) | boto3 |
| pino logging | Python logging (stdlib) |
| Docker + docker-compose | Docker only (Makefile) |
| Port 3000 | Port 8000 |

## Infra Config Loading

At startup, `/app/infra/infrastructure-outputs.json` (Terraform output) is parsed to load:
- Cluster name, VPC ID, private subnets, security group ID
- IAM role ARNs (execution + task)
- CloudWatch log group name

All AWS clients (ecs, elbv2, iam, s3) are initialised once at module level using `boto3.client`.
