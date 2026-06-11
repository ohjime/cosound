#!/bin/sh
# Container entrypoint: prepare the database, then run the three
# procfile.prod processes (gunicorn, db_worker, refresh) under honcho.
#
# Unlike the Render build (bin/buildserver_prod.sh) this does NOT run
# makemigrations — migration files must be committed to the repo.
set -e

cd /app

echo "==> Applying migrations..."
uv run src/main.py migrate --noinput

echo "==> Ensuring cache table exists..."
uv run src/main.py createcachetable

if [ -n "$FIRST_ADMIN_EMAIL" ] && [ -n "$FIRST_ADMIN_USERNAME" ] && [ -n "$FIRST_ADMIN_PASSWORD" ]; then
  echo "==> Ensuring first admin account exists..."
  uv run src/main.py shell <<'EOF'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["FIRST_ADMIN_EMAIL"].strip("'\"")
username = os.environ["FIRST_ADMIN_USERNAME"].strip("'\"")
password = os.environ["FIRST_ADMIN_PASSWORD"].strip("'\"")

if User.objects.filter(email=email).exists():
    print(f"Superuser with email '{email}' already exists.")
elif User.objects.filter(username=username).exists():
    print(f"Superuser with username '{username}' already exists.")
else:
    User.objects.create_superuser(email=email, username=username, password=password)
    print(f"Superuser '{username}' created.")
EOF
else
  echo "==> FIRST_ADMIN_* not fully set; skipping admin bootstrap."
fi

echo "==> Starting processes from procfile.prod..."
exec uv run honcho -f procfile.prod start
