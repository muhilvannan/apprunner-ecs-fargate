# VPC Outputs
output "vpc_id" {
  value       = aws_vpc.main.id
  description = "VPC ID"
}

output "vpc_cidr" {
  value       = aws_vpc.main.cidr_block
  description = "VPC CIDR block"
}

output "public_subnet_ids" {
  value       = [for subnet in aws_subnet.public : subnet.id]
  description = "Public subnet IDs"
}

output "private_subnet_ids" {
  value       = [for subnet in aws_subnet.private : subnet.id]
  description = "Private subnet IDs"
}

output "ecs_task_security_group_id" {
  value       = aws_security_group.ecs_tasks.id
  description = "Security group ID for ECS tasks"
}

output "alb_security_group_id" {
  value       = aws_security_group.alb.id
  description = "Security group ID for ALB"
}

# ECS Outputs
output "cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "ECS cluster name"
}

output "cluster_arn" {
  value       = aws_ecs_cluster.main.arn
  description = "ECS cluster ARN"
}

output "cloudwatch_log_group_name" {
  value       = aws_cloudwatch_log_group.ecs.name
  description = "CloudWatch log group name for ECS"
}

output "cloudwatch_log_group_arn" {
  value       = aws_cloudwatch_log_group.ecs.arn
  description = "CloudWatch log group ARN for ECS"
}

# CloudMap Outputs
output "cloudmap_namespace_id" {
  value       = aws_service_discovery_private_dns_namespace.main.id
  description = "CloudMap namespace ID"
}

output "cloudmap_namespace_arn" {
  value       = aws_service_discovery_private_dns_namespace.main.arn
  description = "CloudMap namespace ARN"
}

output "cloudmap_namespace_name" {
  value       = aws_service_discovery_private_dns_namespace.main.name
  description = "CloudMap namespace name"
}

# IAM Role Outputs
output "ecs_task_execution_role_arn" {
  value       = aws_iam_role.ecs_task_execution_role.arn
  description = "ARN of ECS task execution role"
}

output "ecs_task_execution_role_name" {
  value       = aws_iam_role.ecs_task_execution_role.name
  description = "Name of ECS task execution role"
}

output "ecs_workspace_task_role_arn" {
  value       = aws_iam_role.ecs_workspace_task_role.arn
  description = "ARN of ECS workspace task role"
}

output "ecs_workspace_task_role_name" {
  value       = aws_iam_role.ecs_workspace_task_role.name
  description = "Name of ECS workspace task role"
}

output "s3_bucket_access_policy" {
  value       = data.aws_iam_policy_document.s3_bucket_access.json
  description = "S3 bucket access policy template (for controller use)"
}

# ALB Outputs
output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "ALB DNS name"
}

output "alb_zone_id" {
  value       = aws_lb.main.zone_id
  description = "ALB zone ID"
}

output "alb_arn" {
  value       = aws_lb.main.arn
  description = "ALB ARN"
}

# Domain Outputs
output "domain_name" {
  value       = "brewer.muhilvannan.com"
  description = "Custom domain name"
}

output "hosted_zone_id" {
  value       = aws_route53_zone.main.zone_id
  description = "Route53 hosted zone ID for delegation"
}

output "hosted_zone_name_servers" {
  value       = aws_route53_zone.main.name_servers
  description = "Name servers for hosted zone delegation"
}

output "certificate_arn" {
  value       = aws_acm_certificate.main.arn
  description = "ACM certificate ARN"
}
