output "ecr_repository_url" {
  description = "ECR repository URI. Set as the ECR_REPOSITORY GitHub secret (or derive the registry from it)."
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_registry" {
  description = "ECR registry host (account.dkr.ecr.region.amazonaws.com)."
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "instance_public_ip" {
  description = "Elastic IP of the app instance. Set as the EC2_HOST GitHub secret."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance ID (optional; for SSM troubleshooting)."
  value       = aws_instance.app.id
}

output "security_group_id" {
  description = "App security group ID (used by CI for ephemeral SSH during deploy)."
  value       = aws_security_group.app.id
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC. Set as the AWS_DEPLOY_ROLE_ARN GitHub secret."
  value       = aws_iam_role.github_actions.arn
}

output "app_url" {
  description = "Where the app will be reachable once deployed."
  value       = "http://${aws_eip.app.public_ip}"
}

output "ssh_command" {
  description = "Convenience SSH command (assumes your matching private key)."
  value       = "ssh ec2-user@${aws_eip.app.public_ip}"
}
