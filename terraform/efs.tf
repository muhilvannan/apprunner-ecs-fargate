# Security Group for EFS (Allow NFS from ECS tasks)
resource "aws_security_group" "efs" {
  name_prefix = "${local.cluster_name}-efs-"
  description = "Security group for EFS - ${local.cluster_name}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
    description     = "Allow NFS from ECS tasks"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "${local.cluster_name}-efs-sg"
  }
}

# EFS File System
resource "aws_efs_file_system" "main" {
  encrypted           = true
  performance_mode    = "generalPurpose"
  throughput_mode     = "bursting"
  availability_zone_name = null # Regional EFS

  tags = {
    Name = "${local.cluster_name}-efs"
    Type = "shared-storage"
  }
}

# EFS Mount Targets (one per availability zone for HA)
resource "aws_efs_mount_target" "private" {
  count           = length(aws_subnet.private)
  file_system_id  = aws_efs_file_system.main.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# EFS Access Point (optional but recommended)
resource "aws_efs_access_point" "main" {
  file_system_id = aws_efs_file_system.main.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }

  tags = {
    Name = "${local.cluster_name}-efs-ap"
  }
}
