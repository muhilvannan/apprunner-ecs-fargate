# Makefile for Terraform

.PHONY: init plan apply destroy validate fmt clean output \
        workspace-list workspace-select workspace-new workspace-delete \
        dev staging prod experiment

# ---------------------------------------------------------------------------
# Current workspace guard — prints active workspace before destructive ops
# ---------------------------------------------------------------------------
_check-workspace:
	@echo "[terraform] Active workspace: $$(terraform workspace show)"

# Initialize Terraform
init:
	terraform init

# Validate configuration
validate:
	terraform validate

# Format code
fmt:
	terraform fmt -recursive

# Plan changes — shows active workspace so you always know which stack
plan: _check-workspace
	terraform plan -var-file=terraform.tfvars

# Apply changes — shows active workspace, requires confirmation unless WS is explicit
apply: _check-workspace
	terraform apply -var-file=terraform.tfvars -auto-approve

# Destroy resources — shows active workspace
destroy: _check-workspace
	terraform destroy -var-file=terraform.tfvars -auto-approve

# Show outputs
output:
	terraform output -json > ../infrastructure-outputs.json
	@echo "[terraform] Outputs written to ../infrastructure-outputs.json"
	@terraform output

# Clean up local state (does NOT destroy AWS resources)
clean:
	rm -f terraform.tfstate* .terraform.lock.hcl
	rm -rf .terraform

# ---------------------------------------------------------------------------
# Workspace management
# ---------------------------------------------------------------------------

workspace-list:
	terraform workspace list

workspace-select:
	@echo "Available workspaces:" && terraform workspace list
	@read -p "Enter workspace name: " ws && terraform workspace select $$ws

workspace-new:
	@read -p "Enter new workspace name: " ws && terraform workspace new $$ws

workspace-delete:
	@echo "Available workspaces:" && terraform workspace list
	@read -p "Enter workspace to delete: " ws && terraform workspace delete $$ws

# ---------------------------------------------------------------------------
# Named workspace shortcuts — select (or create) then plan/apply
# ---------------------------------------------------------------------------

# dev:
# 	terraform workspace select dev 2>/dev/null || terraform workspace new dev
# 	@echo "[terraform] Switched to workspace: dev"

# staging:
# 	terraform workspace select staging 2>/dev/null || terraform workspace new staging
# 	@echo "[terraform] Switched to workspace: staging"

prod:
	terraform workspace select prod 2>/dev/null || terraform workspace new prod
	@echo "[terraform] Switched to workspace: prod"

# Experiment workspace — isolated stack for task-level-app-experiments branch
experiment:
	terraform workspace select experiment 2>/dev/null || terraform workspace new experiment
	@echo "[terraform] Switched to workspace: experiment (builder.muhilvannan.com / ecs-app-tester-exp-dev)"

# ---------------------------------------------------------------------------
# Compound targets — select workspace then act (safe, explicit)
# ---------------------------------------------------------------------------

# Deploy experiment stack from scratch
experiment-apply: experiment plan apply output
	@echo "[terraform] Experiment stack deployed in workspace: experiment"

# Tear down only the experiment stack
experiment-destroy: experiment destroy
	@echo "[terraform] Experiment stack destroyed"

# Export outputs for experiment workspace
experiment-output: experiment output

# Prod stack shortcuts (brewer.muhilvannan.com)
prod-apply: prod plan apply output
prod-destroy: prod destroy

# ---------------------------------------------------------------------------
# Nuke all workspaces — destroys infra in every non-default workspace then
# deletes the workspace. Skips the built-in 'default' workspace (no destroy).
# ---------------------------------------------------------------------------
destroy-all:
	@echo "[terraform] WARNING: This will destroy ALL workspaces including default (prod)."
	@echo "[terraform] Press Ctrl-C within 5 seconds to abort..."
	@sleep 5
	@for WS in $$(terraform workspace list | tr -d '* ' | grep -v '^$$'); do \
		echo ""; \
		echo "=== Destroying workspace: $$WS ==="; \
		terraform workspace select $$WS; \
		terraform destroy -var-file=terraform.tfvars -auto-approve || true; \
		if [ "$$WS" != "default" ]; then \
			terraform workspace select default; \
			terraform workspace delete $$WS && echo "[terraform] Deleted workspace: $$WS" || echo "[terraform] Could not delete $$WS (may have state remaining)"; \
		fi; \
	done; \
	echo ""; \
	echo "[terraform] All workspaces destroyed. Active workspace: default"
