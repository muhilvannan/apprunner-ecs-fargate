variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}


variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for multi-AZ deployment"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "Must specify at least 2 availability zones."
  }
}

variable "container_log_retention_days" {
  description = "CloudWatch log retention for ECS container logs (in days)"
  type        = number
  default     = 30
  validation {
    condition     = var.container_log_retention_days > 0
    error_message = "Log retention must be greater than 0."
  }
}

variable "ssl_certificate_arn" {
  description = "ACM certificate ARN for HTTPS listener (optional)"
  type        = string
  default     = ""
}
variable "create_workspace_service" {
  description = "Whether to create the workspace ECS service (set by controller)"
  type        = bool
  default     = false
}

variable "workspace_id" {
  description = "Unique identifier for the workspace (set by controller)"
  type        = string
  default     = ""
}

variable "workspace_service_desired_count" {
  description = "Desired number of tasks for the workspace service"
  type        = number
  default     = 1
  validation {
    condition     = var.workspace_service_desired_count >= 0
    error_message = "Desired count must be non-negative."
  }
}
