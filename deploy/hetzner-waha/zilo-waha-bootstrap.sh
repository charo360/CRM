#!/usr/bin/env bash
set -Eeuo pipefail

# This is installed by the Rescue workflow on a fresh Ubuntu host. It runs once
# on the first normal boot, after networking is online and the secrets-only
# .env file has been placed beside the Compose configuration.
exec > >(tee -a /var/log/zilo-waha-bootstrap.log) 2>&1
export DEBIAN_FRONTEND=noninteractive

# Some Ubuntu images arrive with Docker CE and its Compose plugin already
# installed. Reusing that working installation avoids replacing it with the
# distro package, which can conflict with the preinstalled plugin.
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  apt-get update
  if dpkg-query -W -f='${Status}' docker-compose-plugin 2>/dev/null | grep -q 'install ok installed'; then
    apt-get remove -y docker-compose-plugin
  fi
  apt-get install -y --no-install-recommends ca-certificates docker.io docker-compose-v2
fi

install -d -m 0755 \
  /opt/zilo-waha/data/sessions \
  /opt/zilo-waha/data/media \
  /opt/zilo-waha/data/caddy \
  /opt/zilo-waha/config/caddy

systemctl enable --now docker.service
/usr/bin/docker compose -f /opt/zilo-waha/docker-compose.yml up -d

# The stack is now supervised by Docker restart policies. Leave the log behind
# for diagnostics but remove this one-shot bootstrap service.
systemctl disable zilo-waha-bootstrap.service || true
rm -f /etc/systemd/system/zilo-waha-bootstrap.service
systemctl daemon-reload
