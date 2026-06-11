#!/bin/sh
# Dump the cosound database and ship it to S3 (db-backups/ prefix).
# Run on the droplet from the host crontab, e.g. nightly at 09:00 UTC:
#   0 9 * * * /opt/cosound/docker/backup.sh >> /var/log/cosound-backup.log 2>&1
#
# Restore with:
#   docker compose exec -T db pg_restore -U cosound -d cosound --clean --if-exists < backup.dump
set -e

cd "$(dirname "$0")/.."

STAMP=$(date -u +%Y%m%d-%H%M%S)

docker compose exec -T db pg_dump -U cosound -d cosound -Fc \
  | docker compose exec -T app uv run python backup_to_s3.py "cosound-db-$STAMP.dump"
