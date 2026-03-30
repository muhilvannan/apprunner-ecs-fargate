# ECS App Tester — Deployment Guide

v0.1 Alpha shipped. Both phases (Foundation + Controller API) are complete. This guide covers deploying the base infrastructure to a fresh AWS account.

## Prerequisites

Ensure you have:
- Terraform 1.0+ installed: `terraform version`
- AWS CLI: `aws --version`
- AWS credentials configured: `aws configure`
- Appropriate IAM permissions for ECS, EC2, EFS, ALB, IAM, CloudWatch

## Step 1: Review Configuration

```bash
cd /Users/muhil-work/Projects/apprunner-ecs-fargate/terraform

# Verify terraform.tfvars has correct values (mostly defaults are fine)
cat terraform.tfvars
```

Expected content:
```
aws_region                   = "eu-west-1"
environment                  = "dev"
vpc_cidr                     = "10.0.0.0/16"
availability_zones           = ["eu-west-1a", "eu-west-1b"]
container_log_retention_days = 30
```

## Step 2: Plan Infrastructure

```bash
terraform plan -var-file=terraform.tfvars
```

Expected output:
```
Plan: 35 to add, 0 to change, 0 to destroy.
```

Review the plan. If you see errors, check:
- AWS credentials: `aws sts get-caller-identity`
- AWS region: `aws configure get region`
- VPC CIDR doesn't conflict with existing VPCs

## Step 3: Apply Infrastructure

```bash
terraform apply -var-file=terraform.tfvars
```

When prompted: `Do you want to perform these actions?`  
Type: `yes`

**Wait 5-10 minutes for resources to create.**

Expected completion:
```
Apply complete! Resources: 35 added, 0 changed, 0 destroyed.
```

## Step 4: Export Outputs for Controller

```bash
terraform output -json > ../infrastructure-outputs.json

# Verify outputs exported
cat ../infrastructure-outputs.json | jq 'keys'
```

Keys should include: `alb_dns_name`, `cluster_arn`, `cluster_name`, `efs_id`, `vpc_id`, etc.

## Step 5: Verify Deployment

### Check ECS Cluster
```bash
aws ecs describe-clusters --cluster-names ecs-app-tester-dev --query 'clusters[0]' | jq '{name:.clusterName, status:.status, runningCount:.runningCount}'
```

Expected output:
```json
{
  "name": "ecs-app-tester-dev",
  "status": "ACTIVE",
  "runningCount": 0
}
```

### Check EFS
```bash
EFS_ID=$(terraform output -raw efs_id)
aws efs describe-file-systems --file-system-ids $EFS_ID --query 'FileSystems[0]' | jq '{id:.FileSystemId, state:.LifeCycleState, encrypted:.Encrypted}'
```

Expected output:
```json
{
  "id": "fs-xxxxxxxx",
  "state": "available",
  "encrypted": true
}
```

### Check ALB
```bash
ALB_DNS=$(terraform output -raw alb_dns_name)
echo "ALB accessible at: http://$ALB_DNS"

# Verify target group health
TG_ARN=$(terraform output -raw target_group_arn)
aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions' | jq 'length'
```

Initially, target health count should be 0 (no tasks registered yet).

## Step 6: Destroy (Optional, for cleanup)

If you want to tear down all resources:

```bash
terraform destroy -var-file=terraform.tfvars
```

When prompted: Type `yes`

**This will delete all AWS resources created by Phase 01.** Be careful!

---

## Troubleshooting

### Error: "failed to create load balancer"
- Check if you already have an ALB with the same name
- Try changing `environment` variable in terraform.tfvars

### Error: "failed to create EFS"
- Ensure VPC has at least 2 private subnets
- Check AZ availability in your region

### Error: "Access Denied"
- Verify AWS credentials: `aws sts get-caller-identity`
- Check IAM permissions for ECS, EC2, EFS, ALB, CloudMap, IAM, CloudWatch

### Terraform state issues
- Never commit `.tfstate` files to git (already in .gitignore)
- To migrate state: use `terraform state mv`, `terraform state rm`
- To reset local state: `rm -rf terraform.tfstate* .terraform/`  
  (then run `terraform init` and replan)

---

## After Deployment

1. **Save outputs:**
   ```bash
   terraform output -json > ../infrastructure-outputs.json
   ```

2. **Start Controller & UI:**
   ```bash
   make api-rebuild && make api-run  # Start FastAPI controller
   make ui-start                      # Start Express UI (port 3000)
   ```

3. **Access the UI:**
   - Local: http://localhost:3000
   - Live: https://brewer.muhilvannan.com (if domain configured)

4. **Bootstrap a Workspace:**
   - Enter workspace ID in UI
   - Select app types (streamlit, fastapi, reactjs, mkdocs)
   - Click "Bootstrap"
   - Apps start in stopped state (call `/app/start` to enable)

---

## Useful Commands

```bash
# Show all outputs
terraform output

# Show specific output
terraform output cluster_arn

# Show JSON (for scripting)
terraform output -json

# Show plan without applying
terraform plan

# Show resource state
terraform state list
terraform state show aws_ecs_cluster.main

# Validate syntax
terraform validate

# Format code
terraform fmt

# Refresh state (sync with AWS)
terraform refresh

# Destroy specific resource (careful!)
terraform destroy -target=aws_lb.main
```

---

## Deployment Checklist

**Phase 01: Infrastructure**
- [ ] Terraform installed and validated: `terraform version`
- [ ] AWS credentials configured: `aws sts get-caller-identity`
- [ ] terraform.tfvars reviewed
- [ ] Terraform plan created: `terraform plan -var-file=terraform.tfvars`
- [ ] Resources reviewed (35 resources)
- [ ] `terraform apply` executed and completed
- [ ] All 35 resources created successfully in AWS
- [ ] Outputs exported: `terraform output -json > ../infrastructure-outputs.json`
- [ ] ECS cluster active: `aws ecs describe-clusters`
- [ ] EFS file system available: `aws efs describe-file-systems`
- [ ] ALB created: `aws elbv2 describe-load-balancers`

**Phase 02: Controller & UI**
- [ ] Controller Docker image built: `make api-build`
- [ ] Controller running: `make api-run` (port 8000)
- [ ] UI running: `make ui-start` (port 3000)
- [ ] UI accessible: http://localhost:3000
- [ ] Bootstrap a workspace via UI
- [ ] Start an app and verify it's accessible

---

**Phase 01 deployment complete!** Proceed with Phase 02 when ready.
