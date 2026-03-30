locals {
  workspace_config = {
    dev = {
      environment   = "dev"
      vpc_cidr      = "10.0.0.0/16"
      azs           = ["eu-west-1a", "eu-west-1b"]
      instance_count = 1
    }
    staging = {
      environment   = "staging"
      vpc_cidr      = "10.1.0.0/16"
      azs           = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
      instance_count = 2
    }
    prod = {
      environment   = "prod"
      vpc_cidr      = "10.2.0.0/16"
      azs           = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
      instance_count = 3
    }
  }

  current_config = lookup(local.workspace_config, terraform.workspace, local.workspace_config.dev)
  
  environment       = local.current_config.environment
  vpc_cidr          = local.current_config.vpc_cidr
  availability_zones = local.current_config.azs
}
