terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: store state remotely. Configure and uncomment if desired.
  # backend "s3" {
  #   bucket = "your-tf-state-bucket"
  #   key    = "relocation-job-hunter/terraform.tfstate"
  #   region = "eu-west-2"
  # }
}

provider "aws" {
  region = var.aws_region
}
