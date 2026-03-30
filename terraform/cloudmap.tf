# CloudMap Private DNS Namespace for Service Discovery
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = local.namespace
  vpc  = aws_vpc.main.id

  description = "Service discovery namespace for ECS workspaces"

  tags = {
    Name = "${local.cluster_name}-discovery"
  }
}
