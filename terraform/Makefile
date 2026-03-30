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

# Workspace management
.PHONY: workspace-list workspace-select workspace-new workspace-delete dev staging prod

# List workspaces
workspace-list:
	terraform workspace list

# Select workspace
workspace-select:
	@echo "Available workspaces:" && terraform workspace list
	@read -p "Enter workspace name: " ws && terraform workspace select $$ws

# Create new workspace
workspace-new:
	@echo "Available workspaces:" && terraform workspace list
	@read -p "Enter new workspace name: " ws && terraform workspace new $$ws

# Delete workspace
workspace-delete:
	@echo "Available workspaces:" && terraform workspace list
	@read -p "Enter workspace to delete: " ws && terraform workspace delete $$ws

# Environment shortcuts
dev:
	terraform workspace select dev 2>/dev/null || terraform workspace new dev

staging:
	terraform workspace select staging 2>/dev/null || terraform workspace new staging

prod:
	terraform workspace select prod 2>/dev/null || terraform workspace new prod
