#!/usr/bin/env bash
# Run once on the EC2 instance (via SSH) if SSM Fleet Manager shows it as offline.
set -euo pipefail
sudo dnf install -y amazon-ssm-agent
sudo systemctl enable --now amazon-ssm-agent
sudo systemctl status amazon-ssm-agent --no-pager
echo "Wait 2-5 minutes, then check Systems Manager > Fleet Manager for this instance."
