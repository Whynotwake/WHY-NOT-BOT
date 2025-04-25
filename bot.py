import os
import threading
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = Flask(__name__)

# Словарь для хранения сообщений на согласование
pending_messages = {}

# Получаем входящее сообщение из Instagram и пересылаем в Telegram на согласование
@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook/", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        # Для подтверждения webhook в Meta
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode and token and mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Verification failed", 403

    elif request.method == "POST":
        data = request.json
        # Разбор data — найди нужный путь до сообщения и пользователя
        # Пример:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    for msg in value["messages"]:
                        message_id = msg["id"]
                        text = msg["text"]
                        from_user = value["contacts"][0]["profile"]["name"]
                        pending_messages[message_id] = (text, from_user)
                        # Отправляем в Telegram на согласование
                        threading.Thread(target=notify_admin, args=(message_id, text, from_user)).start()
        return jsonify(status="ok")

def notify_admin(message_id, text, from_user):
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")  # Или свой id
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Разрешить", callback_data=f"allow_{message_id}")],
        [types.InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{message_id}")],
        [types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message_id}")]
    ])
    msg = f"Новое сообщение из Instagram от {from_user}:\n\n{text}\n\nРазрешить отправку ответа?"
    # Импортируй executor или используй run_in_executor для async -> sync
    import asyncio
    asyncio.run(bot.send_message(admin_id, msg, reply_markup=kb))

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    if call.data.startswith("allow_"):
        msg_id = call.data.replace("allow_", "")
        text, from_user = pending_messages.get(msg_id, ("", ""))
        # Здесь отправь текст обратно в Instagram через Meta Graph API
        await call.answer("Разрешено. Ответ отправлен в Instagram.")
    elif call.data.startswith("edit_"):
        # Логика для редактирования
        await call.answer("Функция редактирования не реализована.")
    elif call.data.startswith("reject_"):
        await call.answer("Сообщение отклонено.")

# Flask run for Railway
def run_flask():
    app.run(host="0.0.0.0", port=8080)

def start_aiogram():
    import asyncio
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    start_aiogram()
