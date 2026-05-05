import discord
import random
import string
import requests
import asyncio
import os

# --- CONFIG ---
TOKEN = "MTUwMTIyNTc5NDEyMTM3MTcyOQ.GSZMCY.wbtV6L6htCkeiJv6ER9sS8FXdj7Ecb5Il6qD6c"
PLATFORM_API_URL = "http://127.0.0.1:8000/users/api/social/register-code/"
API_BOT_TOKEN = "debug_token"

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f'Discord Bot logged in as {self.user} (ID: {self.user.id})')

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('!validate') or message.content.startswith('!verify'):
            code = generate_code()
            social_id = message.author.id
            
            # Call platform API
            try:
                response = requests.post(
                    PLATFORM_API_URL,
                    json={
                        "provider": "discord",
                        "social_id": social_id,
                        "code": code
                    },
                    headers={"X-Bot-Token": API_BOT_TOKEN},
                    timeout=5
                )
                
                if response.status_code == 200:
                    await message.author.send(
                        f"Привіт! 👋\n\nВаш код підтвердження для платформи турнірів:\n\n**{code}**\n\n"
                        "Введіть його в налаштуваннях профілю на сайті."
                    )
                    await message.channel.send(f"{message.author.mention}, я відправив вам код в особисті повідомлення (DM).")
                else:
                    await message.channel.send("❌ Помилка зв'язку з платформою. Спробуйте пізніше.")
            except Exception as e:
                print(f"API Error: {e}")
                await message.channel.send("❌ Помилка підключення до сервера.")

def main():
    print("Discord Bot starting...")
    intents = discord.Intents.default()
    intents.message_content = True
    
    client = MyBot(intents=intents)
    client.run(TOKEN)

if __name__ == "__main__":
    main()
