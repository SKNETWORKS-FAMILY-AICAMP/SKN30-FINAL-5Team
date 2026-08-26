#!/bin/bash
set -euo pipefail

dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

compose_version="v2.40.3"
compose_asset="docker-compose-linux-x86_64"
compose_base_url="https://github.com/docker/compose/releases/download/${compose_version}"
install -d -m 0755 /usr/local/lib/docker/cli-plugins
curl --fail --location --silent --show-error \
  "${compose_base_url}/${compose_asset}" \
  --output "/tmp/${compose_asset}"
curl --fail --location --silent --show-error \
  "${compose_base_url}/${compose_asset}.sha256" \
  --output "/tmp/${compose_asset}.sha256"
(
  cd /tmp
  sha256sum --check "${compose_asset}.sha256"
)
install -m 0755 "/tmp/${compose_asset}" /usr/local/lib/docker/cli-plugins/docker-compose
rm -f "/tmp/${compose_asset}" "/tmp/${compose_asset}.sha256"

install -d -m 0755 -o ec2-user -g ec2-user /opt/helkki
