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
apt-get install -y -q docker.io docker-compose-v2 unattended-upgrades python3-venv

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

# OCI CLI for uploading backups (plan 03-03). It authenticates as the VM itself
# (instance principal), so no API key ever sits on the server.
if [[ ! -x /opt/oci-cli/bin/oci ]]; then
  python3 -m venv /opt/oci-cli
  /opt/oci-cli/bin/pip install -q oci-cli
fi

# Nightly database backup: 03:00 IST (21:30 UTC). Persistent=true runs a missed backup
# as soon as the VM is back up.
cat > /etc/systemd/system/pcbuilder-backup.service <<'UNIT'
[Unit]
Description=PC Builder nightly database backup (scripts/backup_db.sh)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=ubuntu
ExecStart=/bin/bash /srv/pcbuilder/app/scripts/backup_db.sh
UNIT
cat > /etc/systemd/system/pcbuilder-backup.timer <<'UNIT'
[Unit]
Description=Run the PC Builder database backup nightly

[Timer]
OnCalendar=*-*-* 21:30:00 UTC
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now pcbuilder-backup.timer

docker --version
docker compose version
/opt/oci-cli/bin/oci --version
echo "server setup done"
