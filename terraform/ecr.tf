# ECR repository for the workspace landing page image
resource "aws_ecr_repository" "landing_page" {
  name                 = "${local.project}-landing-page-${local.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = {
    Name = "${local.project}-landing-page-${local.environment}"
  }
}
