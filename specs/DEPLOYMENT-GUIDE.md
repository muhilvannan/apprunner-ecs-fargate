# Phase 01 Deployment Quick Start

## Prerequisites

Ensure you have:
- Terraform 1.0+ installed: `terraform version`
- AWS CLI: `aws --version`
- AWS credentials configured: `aws configure`
- Appropriate IAM permissions for ECS, EC2, EFS, ALB, CloudMap, IAM, CloudWatch

## Step 1: Review Configuration

```bash
cd /Users/muhil-work/Projects/ecs-app-tester/terraform

# Verify terraform.tfvars has correct values (mostly defaults are fine)
cat terraform.tfvars
```

Expected content:
```
aws_region                   = "us-east-1"
environment                  = "dev"
vpc_cidr                     = "10.0.0.0/16"
availability_zones           = ["us-east-1a", "us-east-1b"]
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

## Step 4: Export Outputs for Phase 02

```bash
terraform output -json > ../infrastructure-outputs.json

# Verify outputs exported
cat ../infrastructure-outputs.json | jq 'keys'
```

Keys should include: `alb_dns_name`, `cluster_arn`, `cloudmap_namespace_id`, `efs_id`, etc.

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

2. **Update inventory (for Phase 02 controller):**
   - Controller API will read `infrastructure-outputs.json`
   - Ensure JSON file is accessible to controller process

3. **Next: Phase 02**
   - Ready to start Controller API development
   - API will bootstrap workspaces using ECS and CloudMap
   - Phase 02 plan will be generated next

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
- [ ] Ready for Phase 02 (Controller API development)

---

**Phase 01 deployment complete!** Proceed with Phase 02 when ready.
