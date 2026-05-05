#!/bin/bash
# Apply database migrations
#python manage.py migrate --noinput || echo "Migration failed, check your database connection."

# Start bots in the background
python bots/telegram_bot.py &
python bots/discord_bot.py &

# Start Django with Gunicorn, fallback to 8080 if PORT is empty
gunicorn core.wsgi --bind 0.0.0.0:${PORT:-8080}
