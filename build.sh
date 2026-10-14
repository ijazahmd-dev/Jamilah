#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate
