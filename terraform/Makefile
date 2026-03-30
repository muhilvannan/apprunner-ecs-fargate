# Makefile for Terraform

.PHONY: init plan apply destroy validate fmt clean output

# Initialize Terraform
init:
	terraform init

# Validate configuration
validate:
	terraform validate

# Format code
fmt:
	terraform fmt -recursive

# Plan changes
plan:
	terraform plan -var-file=terraform.tfvars

# Apply changes
apply:
	terraform apply -var-file=terraform.tfvars -auto-approve

# Destroy resources
destroy:
	terraform destroy -var-file=terraform.tfvars -auto-approve

# Show outputs
output:
	terraform output

# Clean up
clean:
	rm -f terraform.tfstate* .terraform.lock.hcl
	rm -rf .terraform

# Plan with workspace vars (if exists)
plan-workspace:
	terraform plan -var-file=workspace.tfvars

# Apply with workspace vars
apply-workspace:
	terraform apply -var-file=workspace.tfvars -auto-approve