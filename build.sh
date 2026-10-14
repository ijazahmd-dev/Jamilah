#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Collect static files to static storage / Cloudinary
python manage.py collectstatic --no-input --no-post-process

# Run database migrations
python manage.py migrate
