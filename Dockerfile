# syntax=docker/dockerfile:1
# Server image for the DigitalOcean droplet deployment.
# Build context is the repo root: docker build -t cosound-server .

# ---- Stage 1: build Vite assets ----
FROM node:22-alpine AS vite
WORKDIR /build/vite
COPY src/server/vite/package.json src/server/vite/package-lock.json ./
RUN npm ci
COPY src/server/vite/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first so code changes don't bust this layer
COPY src/server/pyproject.toml src/server/uv.lock src/server/README.md ./
RUN uv sync --frozen --no-dev

# Application code + built frontend assets
COPY src/server/src ./src
COPY src/server/procfile.prod ./procfile.prod
COPY docker/backup_to_s3.py ./backup_to_s3.py
COPY --from=vite /build/vite/static ./vite/static

# Bake the whitenoise static manifest into the image (no DB access needed)
RUN DEBUG=false uv run src/main.py collectstatic --noinput

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
