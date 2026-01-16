#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install dependencies using uv
uv sync

# Change to src directory where manage.py equivalent lives
cd src

# Convert static asset files
python main.py collectstatic --no-input

# Apply any outstanding database migrations
python main.py migrate
