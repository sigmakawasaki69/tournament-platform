#!/bin/bash
# 1. Apply database migrations
#python manage.py migrate --noinput

# 2. Start bots in the background
python bots/telegram_bot.py &
python bots/discord_bot.py &

# 3. Start Django with Gunicorn using the port provided by Railway
gunicorn core.wsgi --bind 0.0.0.0:$PORT
