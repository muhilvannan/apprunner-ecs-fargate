# ECS Task Execution Role (can pull images, push logs, etc.)
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${local.project}-exec-role-${local.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.project}-exec-role-${local.environment}"
  }
}

# Attach AWS-managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Inline policy for CloudWatch logs
resource "aws_iam_role_policy" "ecs_task_execution_cloudwatch" {
  name = "${local.project}-exec-cw-${local.environment}"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          aws_cloudwatch_log_group.ecs.arn,
          "${aws_cloudwatch_log_group.ecs.arn}:*"
        ]
      }
    ]
  })
}

# ECS Workspace Task Role (base role, will be customized per workspace)
resource "aws_iam_role" "ecs_workspace_task_role" {
  name = "${local.project}-ws-task-role-${local.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.project}-ws-task-role-${local.environment}"
    Type = "workspace-base"
  }
}

# Inline policy: Cloud Map service discovery for landing-page proxy
resource "aws_iam_role_policy" "ecs_workspace_task_cloudmap" {
  name = "${local.project}-ws-task-cloudmap-${local.environment}"
  role = aws_iam_role.ecs_workspace_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["servicediscovery:DiscoverInstances"]
        Resource = "*"
      }
    ]
  })
}

# Data source for reusable S3 bucket access policy (for controller to use)
data "aws_iam_policy_document" "s3_bucket_access" {
  statement {
    sid    = "S3ReadAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:GetObjectVersion"
    ]
    resources = [
      "arn:aws:s3:::BUCKET_NAME",
      "arn:aws:s3:::BUCKET_NAME/*"
    ]
  }
}
