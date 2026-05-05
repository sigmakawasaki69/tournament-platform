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
        self.last_msg_times = {}

    async def on_ready(self):
        print(f'Discord Bot logged in as {self.user} (ID: {self.user.id})')

    async def on_member_join(self, member):
        """Автоматично надсилаємо код при вході на сервер."""
        print(f"New member joined: {member.name}")
        await self.send_verification_code(member, is_new_join=True)

    async def send_verification_code(self, user, channel=None, is_new_join=False):
        """Метод для генерації та надсилання коду."""
        code = generate_code()
        social_id = user.id
        
        try:
            response = requests.post(
                PLATFORM_API_URL,
                json={
                    "provider": "discord",
                    "social_id": str(social_id),
                    "code": code
                },
                headers={"X-Bot-Token": API_BOT_TOKEN},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'already_verified':
                    if not is_new_join:
                        await user.send("✅ Ваш акаунт Discord уже підтверджено на платформі!")
                    return

                welcome_msg = "Привіт! 👋\n\n"
                if is_new_join:
                    welcome_msg += "Вітаємо на нашому сервері! "
                
                welcome_msg += (
                    f"Ваш код підтвердження для платформи турнірів:\n\n"
                    f"**{code}**\n\n"
                    f"Введіть його в налаштуваннях профілю на сайті."
                )
                
                try:
                    await user.send(welcome_msg)
                    if channel and not isinstance(channel, discord.DMChannel):
                        await channel.send(f"{user.mention}, я відправив вам код в особисті повідомлення (DM).")
                except discord.Forbidden:
                    if channel and not isinstance(channel, discord.DMChannel):
                        await channel.send(f"{user.mention}, я не можу відправити вам DM. Перевірте налаштування приватності.")
            else:
                if channel:
                    await channel.send("❌ Помилка зв'язку з платформою. Спробуйте пізніше.")
        except Exception as e:
            print(f"API Exception: {e}")
            if channel:
                await channel.send("❌ Помилка підключення до сервера.")

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Rate Limit (5 seconds)
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        if user_id in self.last_msg_times:
            if now - self.last_msg_times[user_id] < 5:
                return
        self.last_msg_times[user_id] = now

        if message.content.startswith('!validate') or message.content.startswith('!verify'):
            await self.send_verification_code(message.author, message.channel)
        
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

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True # Потрібно для on_member_join
    
    bot = MyBot(intents=intents)
    bot.run(TOKEN)

if __name__ == "__main__":
    main()