variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Name prefix for all created resources."
  type        = string
  default     = "relocation-job-hunter"
}

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 GB) is a sensible default for this app."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size_gb" {
  description = "Size of the root EBS volume (also holds the /data app state)."
  type        = number
  default     = 20
}

variable "ssh_public_key" {
  description = "SSH public key contents used to create the EC2 key pair (e.g. contents of ~/.ssh/id_ed25519.pub)."
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH (port 22). Lock this to your IP/32 for security."
  type        = string
  default     = "0.0.0.0/0"
}

variable "github_repo" {
  description = "GitHub repository in 'owner/name' form, used to scope the OIDC deploy role."
  type        = string
}

variable "github_oidc_provider_exists" {
  description = "Set true if the GitHub OIDC provider already exists in this AWS account (only one is allowed per account)."
  type        = bool
  default     = false
}
