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

buildx_version="v0.36.1"
buildx_asset="buildx-${buildx_version}.linux-amd64"
buildx_base_url="https://github.com/docker/buildx/releases/download/${buildx_version}"
buildx_sha256="48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778"
curl --fail --location --silent --show-error \
  "${buildx_base_url}/${buildx_asset}" \
  --output "/tmp/${buildx_asset}"
echo "${buildx_sha256}  /tmp/${buildx_asset}" | sha256sum --check -
install -m 0755 "/tmp/${buildx_asset}" /usr/local/lib/docker/cli-plugins/docker-buildx
rm -f "/tmp/${buildx_asset}"

install -d -m 0755 -o ec2-user -g ec2-user /opt/helkki
