#!/bin/bash
# 1. Apply database migrations (CRITICAL for fixing 500 error)
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 3. Start Django with Gunicorn
gunicorn core.wsgi --bind 0.0.0.0:${PORT:-8000}
