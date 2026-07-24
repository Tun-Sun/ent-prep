#!/usr/bin/env bash
set -e
cd backend
python manage.py migrate
python manage.py import_json --skip-existing
python manage.py seed_data --keep-subjects --force
python manage.py ensure_admin
exec gunicorn core.wsgi:application --bind 0.0.0.0:$PORT
