terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
  # State backend: configure before team use, e.g.
  # backend "s3" {
  #   bucket         = "medisense-terraform-state"
  #   key            = "ecs/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "medisense-terraform-lock"
  # }
}

provider "aws" {
  region = var.region
}
