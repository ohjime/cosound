# Deploying cosound to a DigitalOcean droplet

The production stack is three Docker containers defined in
`docker-compose.yml` at the repo root:

| Service | What it runs |
|---------|--------------|
| `app`   | Django via gunicorn (`:8000`), the django-tasks `db_worker`, and the 180s `refresh` loop — all three `procfile.prod` processes under honcho |
| `db`    | Postgres 17 with pgvector (`pgvector/pgvector:pg17`), data in the `pgdata` volume |
| `caddy` | HTTPS termination for `cosound.ca` / `www.cosound.ca` with automatic Let's Encrypt certificates |

S3 (sound files, media, backups) and SES (auth email) stay on AWS exactly as
they were on Render.

## 1. Provision the droplet

1. Create a droplet: **Ubuntu 24.04 LTS, 2 GB RAM minimum** (1 GB is too
   tight for Postgres + gunicorn + the Vite build). The $12/mo Basic
   droplet is fine.
2. Assign a **Reserved IP** to the droplet (Networking → Reserved IPs) so
   DNS never has to change if the droplet is rebuilt.
3. Install Docker (includes compose):

   ```sh
   curl -fsSL https://get.docker.com | sh
   ```

4. Basic firewall — only SSH and HTTP(S) in:

   ```sh
   ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
   ```

## 2. Configure and start the stack

```sh
git clone https://github.com/ohjime/cosound /opt/cosound
cd /opt/cosound
cp env/.env.production.example env/.env.production
nano env/.env.production
```

Fill in every `changeme`:

- `SECRET_KEY`: generate with `openssl rand -base64 48`
- `POSTGRES_PASSWORD` and the password inside `DATABASE_URL` must match
- AWS keys: same IAM credentials Render used (S3 + SES access)
- `FIRST_ADMIN_*`: bootstrap admin account, created on first start

Then:

```sh
docker compose up -d --build
```

First build takes a few minutes (Vite build + Python deps). The app
entrypoint applies migrations and creates the cache table and admin account
automatically. Note it does **not** run `makemigrations` (unlike the old
Render build script) — migration files must be committed to the repo.

Check health: `docker compose ps` (app should report `healthy`) and
`docker compose logs -f app`.

## 3. Migrate the data from Render

Postgres on Render → droplet, while Render is still up:

```sh
# On the droplet. Get the EXTERNAL connection string from the Render
# dashboard (cosound-db → Connect → External Database URL).
docker compose exec db pg_dump --no-owner --no-privileges -Fc \
  -d 'postgres://<render-external-url>' > /tmp/render.dump

docker compose exec -T db pg_restore -U cosound -d cosound \
  --clean --if-exists --no-owner --no-privileges < /tmp/render.dump

docker compose restart app
```

S3 needs no migration — both deployments point at the same bucket.

## 4. Point DNS at the droplet (Route 53)

In the Route 53 hosted zone for `cosound.ca`:

1. `A` record for `cosound.ca` → the droplet's **Reserved IP**.
2. `A` record for `www.cosound.ca` → same IP (or a CNAME to `cosound.ca`).
3. Drop the TTL to 300s before the cutover so you can roll back quickly.

Within a minute or two of DNS propagating, Caddy will obtain certificates
for both names automatically (watch `docker compose logs -f caddy`).
Port 80 must be reachable for the ACME challenge — don't firewall it off.

> **S3 CORS reminder:** before launch, the `cosounds-frishkopf` bucket needs
> a CORS rule allowing `https://cosound.ca` and `https://www.cosound.ca`,
> or the mix app plays silent.

Once cosound.ca serves from the droplet and login + sound playback work,
suspend/delete the Render service and database.

## 5. Nightly database backups

The `pgdata` Docker volume lives on the droplet's disk — back it up
off-host. `docker/backup.sh` dumps the DB and streams it to
`s3://<bucket>/db-backups/`, keeping the newest 14 (override with
`DB_BACKUP_RETAIN` in `env/.env.production`). Install on the host crontab:

```sh
crontab -e
# nightly at 09:00 UTC
0 9 * * * /opt/cosound/docker/backup.sh >> /var/log/cosound-backup.log 2>&1
```

Restore a dump:

```sh
aws s3 cp s3://<bucket>/db-backups/<name>.dump - | \
  docker compose exec -T db pg_restore -U cosound -d cosound --clean --if-exists
```

(or download the dump from the S3 console and pipe the file in).

## 6. Day-2 operations

| Task | Command (from `/opt/cosound`) |
|------|-------------------------------|
| Deploy new code | `git pull && docker compose up -d --build` |
| Tail logs | `docker compose logs -f app` |
| Django shell | `docker compose exec app uv run src/main.py shell` |
| Management command | `docker compose exec app uv run src/main.py <cmd>` |
| psql | `docker compose exec db psql -U cosound` |
| Manual backup | `docker/backup.sh` |
| Roll back code | `git checkout <prev-sha> && docker compose up -d --build` |

The player is unaffected by all of this — it runs on its own hardware and
only needs `COSOUND_API_URL` to keep pointing at `https://cosound.ca/api`.
