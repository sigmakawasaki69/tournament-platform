#!/bin/bash
# Apply database migrations
python manage.py migrate --noinput

# Start bots in the background
python bots/telegram_bot.py &
python bots/discord_bot.py &

# Start Django with Gunicorn
gunicorn core.wsgi --bind 0.0.0.0:$PORT
