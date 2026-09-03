#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

python3 scripts/deploy_preflight.py
docker compose config --quiet
docker compose build --pull
docker compose up -d --wait --wait-timeout 240

curl --fail --silent --show-error http://127.0.0.1/api/v1/health >/dev/null
curl --fail --silent --show-error http://127.0.0.1/ >/dev/null

echo "Deployment completed and health checks passed."
