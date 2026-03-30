# Makefile for ECS Controller API

.PHONY: build rebuild run stop clean logs

build:
	docker build -t ecs-controller-api .

rebuild: stop build

run: build stop
	docker run -d --name ecs-controller -p 8000:8000 \
		-v $(HOME)/.aws:/root/.aws:ro \
		-v $(PWD)/../infrastructure-outputs.json:/app/infra/infrastructure-outputs.json:ro \
		-e AWS_PROFILE \
		-e AWS_ACCESS_KEY_ID \
		-e AWS_SECRET_ACCESS_KEY \
		-e AWS_SESSION_TOKEN \
		-e AWS_DEFAULT_REGION=eu-west-1 \
		ecs-controller-api

stop:
	docker stop ecs-controller 2>/dev/null || true
	docker rm ecs-controller 2>/dev/null || true

clean: stop
	docker rmi ecs-controller-api || true

logs:
	docker logs -f ecs-controller
