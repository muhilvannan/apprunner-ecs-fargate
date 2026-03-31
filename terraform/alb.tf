# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${replace(local.cluster_name, "_", "-")}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [for subnet in aws_subnet.public : subnet.id]

  enable_deletion_protection = false

  tags = {
    Name = "${local.cluster_name}-alb"
    Type = "lb"
  }
}

# Default Target Group
resource "aws_lb_target_group" "default" {
  name        = "${replace(local.project, "_", "-")}-tg-default"
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
    Name = "${local.cluster_name}-tg-default"
  }
}

# HTTP Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default.arn
  }

  tags = {
    Name = "${local.cluster_name}-listener-http"
  }
}

# HTTPS Listener (conditional - only if certificate provided)
resource "aws_lb_listener" "https" {
  count = 1

  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default.arn
  }

  tags = {
    Name = "${local.cluster_name}-listener-https"
  }
}

# HTTP to HTTPS Redirect Rule (conditional)
resource "aws_lb_listener_rule" "http_redirect_https" {
  count = 1

  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}
