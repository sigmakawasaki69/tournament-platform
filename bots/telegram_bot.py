import os
import random
import string
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = os.environ.get("PORT", "8080")
# Use local address if possible, otherwise public one
PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", f"http://127.0.0.1:{PORT}/api/social/register-code/")
API_BOT_TOKEN = os.environ.get("BOT_API_TOKEN", "ad0209")

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[KeyboardButton("Пройти валідацію 🛡️")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"Привіт, {user.first_name}! 👋\n\n"
        "Цей бот допоможе підтвердити ваш Telegram-акаунт на платформі турнірів.\n"
        "Натисніть кнопку нижче, щоб отримати код підтвердження.",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- RATE LIMIT ---
    if not hasattr(context.application, 'last_msg_times'):
        context.application.last_msg_times = {}
    
    user_id = update.effective_user.id
    now = asyncio.get_event_loop().time()
    if user_id in context.application.last_msg_times:
        if now - context.application.last_msg_times[user_id] < 5:
            return
    context.application.last_msg_times[user_id] = now

    # Обробка команди /start або повідомлення "Пройти валідацію"
    if update.message.text == "/start" or "валідація" in update.message.text.lower():
        code = generate_code()
        social_id = update.effective_user.id
        
        # Виклик API платформи
        try:
            response = requests.post(
                PLATFORM_API_URL,
                json={
                    "provider": "telegram",
                    "social_id": str(social_id), # Перетворюємо в string для API
                    "code": code
                },
                headers={"X-Bot-Token": API_BOT_TOKEN},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'already_verified':
                    await update.message.reply_text("✅ Ваш Telegram уже підтверджено на платформі!")
                    return

                await update.message.reply_text(
                    f"Ваш код підтвердження:\n\n`{code}`\n\n"
                    "Скопіюйте його та введіть у налаштуваннях профілю на сайті.",
                    parse_mode='Markdown'
                )
            else:
                print(f"API Error: Status {response.status_code}, Body: {response.text}")
                await update.message.reply_text("❌ Помилка зв'язку з платформою. Спробуйте пізніше.")
        except Exception as e:
            print(f"API Exception: {e}")
            await update.message.reply_text("❌ Помилка підключення до сервера.")

def main():
    print("Telegram Bot starting...")
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment.")
        return
        
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
