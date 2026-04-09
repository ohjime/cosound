#!/bin/bash

# Build script for production deployment
# This script:
# 2. Builds Vite assets for production
# 3. Makes Django migrations
# 4. Runs Django migrations
# 5. Collects static files


set -e  # Exit on any error

echo "🏗️  Starting production build..."

# Note: On Render, rootDir is src/server, so we're already in the right directory
# For local testing, navigate to server directory if not already there
if [[ ! -f "pyproject.toml" ]]; then
  cd "$(dirname "$0")/../src/server"
fi

# Install dependencies
echo "📦 Installing dependencies with uv..."
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

# Create cache table for django-file-form (required for multi-worker gunicorn)
echo "🗄️ Creating cache table..."
uv run src/main.py createcachetable

# Collect static files
echo "📂 Collecting static files..."
uv run src/main.py collectstatic --noinput

# Create superuser from environment variables
echo "👤 Creating superuser..."
uv run src/main.py shell <<EOF
from django.contrib.auth import get_user_model
import os

User = get_user_model()

# Require admin credentials from environment — no insecure defaults
email = os.getenv('FIRST_ADMIN_EMAIL', '').strip("'\"")
username = os.getenv('FIRST_ADMIN_USERNAME', '').strip("'\"")
password = os.getenv('FIRST_ADMIN_PASSWORD', '').strip("'\"")

if not (email and username and password):
    print("✗ Error: FIRST_ADMIN_EMAIL, FIRST_ADMIN_USERNAME, and FIRST_ADMIN_PASSWORD must be set.")
    exit(1)

# Check if user already exists
if User.objects.filter(email=email).exists():
    print(f"✓ Superuser with email '{email}' already exists.")
elif User.objects.filter(username=username).exists():
    print(f"✓ Superuser with username '{username}' already exists.")
else:
    # Create the superuser
    try:
        User.objects.create_superuser(
            email=email,
            username=username,
            password=password
        )
        print(f"✓ Superuser '{username}' created successfully!")
        print(f"  Email: {email}")
        print(f"  Username: {username}")
    except Exception as e:
        print(f"✗ Error creating superuser: {e}")
        exit(1)
EOF

echo "✅ Production build complete!"

