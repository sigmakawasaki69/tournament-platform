#!/bin/bash
# 1. Apply database migrations (CRITICAL for fixing 500 error)
#python manage.py migrate --noinput

# 2. Start bots in the background
python bots/telegram_bot.py &
python bots/discord_bot.py &

# 3. Start Django with Gunicorn
# Using ${PORT:-8000} ensures that if PORT is empty, it uses 8000
gunicorn core.wsgi --bind 0.0.0.0:${PORT:-8000}
