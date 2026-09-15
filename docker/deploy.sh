#!/usr/bin/env bash
# Manual deploy: run on the droplet from the repo checkout (e.g. /opt/cosound).
# Optionally name a branch:  ./docker/deploy.sh merging/algorithm
set -euo pipefail
cd "$(dirname "$0")/.."
if [ $# -gt 0 ]; then
	make docker-deploy BRANCH="$1"
else
	make docker-deploy
fi
