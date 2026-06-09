#!/bin/bash
set -euxo pipefail

# Install Docker + Compose plugin on Amazon Linux 2023.
dnf update -y
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
COMPOSE_VERSION="v2.29.7"
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# App working directory (compose file + .env are uploaded here by CI) and the
# persistent data directory (SQLite DB, uploads, generated PDFs).
mkdir -p /opt/app
mkdir -p /data/uploads /data/generated
chown -R ec2-user:ec2-user /opt/app /data
