# Milestones

## v0.1 Alpha — 2026-03-30

**Status:** ✅ Shipped
**Phases:** 01–02 (5 plans total)
**Delivered:** AWS ECS multi-workspace app management platform with ALB-based start/stop, live at brewer.muhilvannan.com

### Key Accomplishments

1. Provisioned AWS base infra via Terraform (VPC, ECS Fargate cluster, ALB, IAM, EFS) — 35 resources
2. Built Python/FastAPI controller in Docker with full boto3 AWS SDK integration
3. Implemented 1-service-per-workspace architecture with multi-container always-running tasks
4. App start/stop via ALB listener rule toggle (forward ↔ fixed-response 503) — no cold-start
5. Manual IP → TG registration flow enabling N apps per workspace in single ECS service
6. Streamlit `--server.baseUrlPath` fix for static asset routing through ALB path prefix

### Stats

- Languages: Python (controller), Node.js (UI proxy), HCL (Terraform)
- Controller: ~520 LOC Python
- Infrastructure: ~1,200 LOC Terraform (8 .tf files, 35 resources)
- App types: streamlit, fastapi, dash, jupyter, custom
- Live URL: https://brewer.muhilvannan.com

### Known Gaps

- No EFS file mounting in task containers (S3 sync lists only)
- No automated test suite
- App containers install packages at runtime (~90s cold start)
- Phases 03 (routing) and 04 (testing) from original roadmap not formally executed

Archive: [specs/milestones/v0.1-ROADMAP.md](milestones/v0.1-ROADMAP.md)
