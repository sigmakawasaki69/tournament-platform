#!/bin/bash

# Run migrations
python manage.py migrate

# Start Telegram Bot in background
python bots/telegram_bot.py &

# Start Discord Bot in background
python bots/discord_bot.py &

# Start Django (Web server)
# Use gunicorn for production
gunicorn core.wsgi --bind 0.0.0.0:$PORT
