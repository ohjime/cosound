#!/bin/bash

# Build script for production deployment
# This script:
# 2. Builds Vite assets for production
# 3. Makes Django migrations
# 4. Runs Django migrations
# 5. Collects static files


set -e  # Exit on any error

echo "🏗️  Starting production build..."

# Navigate to server directory
cd "$(dirname "$0")/../src/server"

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Build Vite assets for production
echo "⚡ Building Vite assets..."
cd vite
npm install
npm run build
cd ..

# Make migrations
echo "🔄 Making migrations..."
uv run src/main.py makemigrations

# Run migrations
echo "🔄 Running migrations..."
uv run src/main.py migrate

# Collect static files
echo "📂 Collecting static files..."
uv run src/main.py collectstatic --noinput

echo "✅ Production build complete!"

