#!/bin/bash
# Install a new version of MM Store: fetch the code, rebuild, restart. Database migrations run on start.
set -euo pipefail
cd "$(dirname "$0")/.."
deploy/backup.sh                                   # always a fresh backup before changing anything
git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
docker image prune -f >/dev/null
echo "✅ MM Store mis à jour."
