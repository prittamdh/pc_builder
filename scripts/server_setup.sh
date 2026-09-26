#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VM for PC Builder (plan 03-02). Safe to run
# again. Used for the production VM and for the rebuild drill (docs/DEPLOY.md).
#
#   scp scripts/server_setup.sh ubuntu@<vm>:/tmp/ && ssh ubuntu@<vm> 'sudo bash /tmp/server_setup.sh'
#
# Expects the data volume already mounted at /data (see docs/DEPLOY.md, "Data disk").
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run with sudo" >&2; exit 1; fi
if ! mountpoint -q /data; then echo "/data is not mounted - attach and mount the data volume first" >&2; exit 1; fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q
apt-get install -y -q docker.io docker-compose-v2 unattended-upgrades

# Docker keeps images, volumes and container logs on the data volume, not the 47 GB
# boot disk. Container logs rotate: 10 MB x 5 files per container.
mkdir -p /etc/docker /data/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "data-root": "/data/docker",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
systemctl enable docker
systemctl restart docker
usermod -aG docker ubuntu

# App directory: code is unpacked here by scripts/deploy.sh; .env is created by hand
# once and must stay private (mode 600, SEC-08).
mkdir -p /srv/pcbuilder /data/postgres /data/caddy /data/backups
chown -R ubuntu:ubuntu /srv/pcbuilder /data/backups
if [[ -f /srv/pcbuilder/.env ]]; then chmod 600 /srv/pcbuilder/.env; fi

# SSH: keys only.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

# Security updates install themselves (Ubuntu's default, made explicit).
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

docker --version
docker compose version
echo "server setup done"
