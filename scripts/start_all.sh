#!/bin/bash
# Apply database migrations
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input

#python manage.py migrate --noinput

# Start bots in the background
python bots/telegram_bot.py &
python bots/discord_bot.py &

# Start Django with Gunicorn
gunicorn core.wsgi --bind 0.0.0.0:$PORT
