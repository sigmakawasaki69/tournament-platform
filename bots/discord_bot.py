import discord
import random
import string
import requests
import asyncio
import os

# --- CONFIG ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# Since bots are now separate services, use the public URL of the main platform
PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "https://calculator-112.up.railway.app/api/social/register-code/")
API_BOT_TOKEN = os.environ.get("BOT_API_TOKEN", "ad0209")

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f'Discord Bot logged in as {self.user} (ID: {self.user.id})')

    async def on_message(self, message):
        # Ігноруємо повідомлення від самого бота
        if message.author == self.user:
            return

        # Простий Rate Limit (5 секунд)
        if not hasattr(self, 'last_msg_times'):
            self.last_msg_times = {}
        
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        if user_id in self.last_msg_times:
            if now - self.last_msg_times[user_id] < 5:
                # Можна просто ігнорувати або відповісти один раз
                return
        self.last_msg_times[user_id] = now

        # Обробка команд !validate або !verify
        if message.content.startswith('!validate') or message.content.startswith('!verify'):
            code = generate_code()
            social_id = message.author.id
            
            # Виклик API платформи
            try:
                response = requests.post(
                    PLATFORM_API_URL,
                    json={
                        "provider": "discord",
                        "social_id": str(social_id), # Перетворюємо в string для API
                        "code": code
                    },
                    headers={"X-Bot-Token": API_BOT_TOKEN},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'already_verified':
                        await message.author.send("✅ Ваш акаунт Discord уже підтверджено на платформі! Ви можете вільно реєструватися на турніри.")
                        return

                    try:
                        await message.author.send(
                            f"Привіт! 👋\n\nВаш код підтвердження для платформи турнірів:\n\n"
                            f"**{code}**\n\n"
                            f"Введіть його в налаштуваннях профілю на сайті."
                        )
                        if message.guild:
                            await message.channel.send(f"{message.author.mention}, я відправив вам код в особисті повідомлення (DM).")
                    except discord.Forbidden:
                        await message.channel.send(f"{message.author.mention}, я не можу відправити вам DM. Перевірте налаштування приватності.")
                else:
                    print(f"API Error: Status {response.status_code}, Body: {response.text}")
                    await message.channel.send("❌ Помилка зв'язку з платформою. Спробуйте пізніше.")
            except Exception as e:
                print(f"API Exception: {e}")
                await message.channel.send("❌ Помилка підключення до сервера.")
        
        # Якщо повідомлення в DM і це не команда - даємо підказку
        elif isinstance(message.channel, discord.DMChannel):
            await message.author.send(
                "Привіт! 👋 Щоб отримати код підтвердження для сайту, напишіть команду:\n\n"
                "**!verify**"
            )

def main():
    print("Discord Bot starting...")
    if not TOKEN:
        print("Error: DISCORD_BOT_TOKEN not found in environment.")
        return
    
    # --- ВИПРАВЛЕННЯ INTENTS ---
    intents = discord.Intents.default()
    intents.message_content = True  # Дозволяє читати текст повідомлень (!validate)
    intents.members = True          # Дозволяє бачити учасників та відправляти DM
    
    client = MyBot(intents=intents)
    client.run(TOKEN)

if __name__ == "__main__":
    main()