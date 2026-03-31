# Root Makefile for ECS App Tester

.PHONY: api-build api-rebuild api-run api-stop api-clean tf-init tf-validate tf-plan tf-apply tf-destroy tf-output tf-clean tf-destroy-all ui-install ui-start run stop clean cleanup-aws landing-push

# API targets
api-build:
	cd controller-python && make build

api-rebuild:
	cd controller-python && make rebuild

api-run:
	cd controller-python && make run

api-stop:
	cd controller-python && make stop

api-clean:
	cd controller-python && make clean

# Terraform targets — always prints active workspace before plan/apply/destroy
tf-init:
	cd terraform && make init

tf-validate:
	cd terraform && make validate

tf-plan:
	cd terraform && make plan

tf-apply:
	cd terraform && make apply

tf-destroy:
	cd terraform && make destroy

tf-output:
	cd terraform && make output

tf-clean:
	cd terraform && make clean

tf-workspace:
	cd terraform && terraform workspace list

# Experiment branch (task-level-app-experiments) — isolated state
tf-experiment:
	cd terraform && make experiment

tf-experiment-apply:
	cd terraform && make experiment-apply

tf-experiment-output:
	cd terraform && make experiment-output

tf-experiment-destroy:
	cd terraform && make experiment-destroy

# Prod stack (main branch — brewer.muhilvannan.com)
tf-prod:
	cd terraform && make prod

tf-destroy-all:
	cd terraform && make destroy-all

# Landing page — build and push to ECR (requires infrastructure-outputs.json to exist)
AWS_REGION     ?= eu-west-1
LANDING_ECR_URI = $(shell python3 -c "import json; d=json.load(open('infrastructure-outputs.json')); print(d['landing_page_ecr_uri']['value'])" 2>/dev/null)

landing-push:
	@if [ -z "$(LANDING_ECR_URI)" ]; then echo "ERROR: landing_page_ecr_uri not found in infrastructure-outputs.json — run make tf-experiment-output first"; exit 1; fi
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(LANDING_ECR_URI)
	docker buildx build --platform linux/amd64 -t landing-page ui-nodejs/workspace-landing/ --load
	docker tag landing-page:latest $(LANDING_ECR_URI):latest
	docker push $(LANDING_ECR_URI):latest
	@echo "Pushed $(LANDING_ECR_URI):latest"

# UI targets
ui-install:
	cd ui-nodejs && make install

ui-start:
	cd ui-nodejs && make start

# Convenience
setup: tf-init api-build
run: api-run
stop: api-stop
clean: api-clean tf-clean

# AWS runtime cleanup — stops all workspace tasks/services, removes target groups and listener rules
# Does NOT touch base infrastructure (VPC, ECS cluster, ALB, IAM, EFS)
CLUSTER    ?= ecs-app-tester-exp-dev
AWS_REGION ?= eu-west-1

cleanup-aws:
	@echo "--- Stopping all running tasks ---"
	@TASKS=$$(aws ecs list-tasks --cluster $(CLUSTER) --region $(AWS_REGION) --query 'taskArns[]' --output text); \
	if [ -n "$$TASKS" ]; then \
		for TASK in $$TASKS; do \
			echo "Stopping task $$TASK"; \
			aws ecs stop-task --cluster $(CLUSTER) --task $$TASK --region $(AWS_REGION) --output text > /dev/null; \
		done; \
	else echo "No running tasks."; fi

	@echo "--- Deleting workspace ECS services (ws-* prefixed) ---"
	@SERVICES=$$(aws ecs list-services --cluster $(CLUSTER) --region $(AWS_REGION) --query 'serviceArns[]' --output text); \
	if [ -n "$$SERVICES" ]; then \
		for SVC in $$SERVICES; do \
			NAME=$$(echo $$SVC | sed 's|.*/||'); \
			echo "Scaling down and deleting service $$NAME"; \
			aws ecs update-service --cluster $(CLUSTER) --service $$NAME --desired-count 0 --region $(AWS_REGION) --output text > /dev/null; \
			aws ecs delete-service --cluster $(CLUSTER) --service $$NAME --region $(AWS_REGION) --output text > /dev/null; \
		done; \
	else echo "No services to delete."; fi

	@echo "--- Removing workspace ALB listener rules (priority 100-399) ---"
	@ALB_ARN=$$(aws elbv2 describe-load-balancers --region $(AWS_REGION) --query "LoadBalancers[?contains(LoadBalancerName,'ecs-app-tester')].LoadBalancerArn" --output text); \
	if [ -n "$$ALB_ARN" ]; then \
		LISTENER_ARN=$$(aws elbv2 describe-listeners --load-balancer-arn $$ALB_ARN --region $(AWS_REGION) --query "Listeners[?Port==\`443\`].ListenerArn" --output text); \
		if [ -n "$$LISTENER_ARN" ]; then \
			RULES=$$(aws elbv2 describe-rules --listener-arn $$LISTENER_ARN --region $(AWS_REGION) --query "Rules[?Priority!='default' && to_number(Priority)>=\`100\` && to_number(Priority)<=\`399\`].RuleArn" --output text); \
			if [ -n "$$RULES" ]; then \
				for RULE in $$RULES; do \
					echo "Deleting listener rule $$RULE"; \
					aws elbv2 delete-rule --rule-arn $$RULE --region $(AWS_REGION); \
				done; \
			else echo "No workspace listener rules found."; fi; \
		fi; \
	fi

	@echo "--- Deleting workspace target groups (ws-*-tg) ---"
	@TGS=$$(aws elbv2 describe-target-groups --region $(AWS_REGION) --query "TargetGroups[?starts_with(TargetGroupName,'ws-')].TargetGroupArn" --output text); \
	if [ -n "$$TGS" ]; then \
		for TG in $$TGS; do \
			echo "Deleting target group $$TG"; \
			aws elbv2 delete-target-group --target-group-arn $$TG --region $(AWS_REGION); \
		done; \
	else echo "No workspace target groups found."; fi

	@echo "--- Cleanup complete ---"
