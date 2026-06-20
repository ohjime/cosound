#!/usr/bin/env bash
# Manual deploy: run on the droplet from the repo checkout (e.g. /opt/cosound).
set -euo pipefail
cd "$(dirname "$0")/.."
make docker-deploy
