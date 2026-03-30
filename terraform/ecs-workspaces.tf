# ECS Workspaces and Task Definitions
# This file defines pre-set ECS task definitions and dynamic workspace services

# Pre-defined task definitions for common apps
resource "aws_ecs_task_definition" "streamlit_app" {
  family                   = "streamlit-app-${local.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_workspace_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "streamlit"
      image = "python:3.9-slim"
      portMappings = [
        {
          containerPort = 8501
          hostPort      = 8501
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      mountPoints = [
        {
          sourceVolume  = "efs-volume"
          containerPath = "/mnt/efs"
          readOnly      = false
        }
      ]
    }
  ])

  volume {
    name = "efs-volume"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.main.id
      transit_encryption = "ENABLED"
    }
  }

  tags = {
    Name = "nginx-app-task-def"
  }
}

# Add more pre-defined task definitions as needed (e.g., for other apps)
# resource "aws_ecs_task_definition" "web_app" { ... }

# Dynamic workspace service (created per workspace via controller)
resource "aws_ecs_service" "workspace_service" {
  count = var.create_workspace_service ? 1 : 0

  name            = "workspace-${var.workspace_id}-service"
  cluster         = aws_ecs_cluster.main.arn
  task_definition = aws_ecs_task_definition.streamlit_app.arn  # Use appropriate task def based on app
  desired_count   = var.workspace_service_desired_count

  network_configuration {
    subnets          = [for subnet in aws_subnet.private : subnet.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.workspace_service[0].arn
  }

  tags = {
    Name        = "workspace-${var.workspace_id}-service"
    WorkspaceId = var.workspace_id
  }

  depends_on = [aws_service_discovery_service.workspace_service]
}

# CloudMap service for workspace discovery
resource "aws_service_discovery_service" "workspace_service" {
  count = var.create_workspace_service ? 1 : 0

  name = "workspace-${var.workspace_id}"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }

  tags = {
    Name        = "workspace-${var.workspace_id}-discovery"
    WorkspaceId = var.workspace_id
  }
}

# ALB target group for workspace (optional, for routing)
resource "aws_lb_target_group" "workspace_tg" {
  count = var.create_workspace_service ? 1 : 0

  name        = "workspace-${var.workspace_id}-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/healthz"
    matcher             = "200-299"
    port                = "traffic-port"
  }

  tags = {
    Name        = "workspace-${var.workspace_id}-tg"
    WorkspaceId = var.workspace_id
  }
}

# ALB listener rule for workspace routing (pattern: /workspace{workspaceId}/app-{appId})
resource "aws_lb_listener_rule" "workspace_rule" {
  count = var.create_workspace_service ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100 + count.index  # Increment priority for each workspace

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.workspace_tg[count.index].arn
  }

  condition {
    path_pattern {
      values = ["/workspace${var.workspace_id}/*"]
    }
  }

  tags = {
    Name        = "workspace-${var.workspace_id}-rule"
    WorkspaceId = var.workspace_id
  }
}
