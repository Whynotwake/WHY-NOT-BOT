import os
import threading
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = Flask(__name__)
pending_messages = {}

def generate_reply(user_input):
    with open("bot_memory.txt", "r", encoding="utf-8") as f:
        memory = f.read().strip()
    return memory.replace("{user_input}", user_input)

@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook/", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403

    if request.method == "POST":
        data = request.json
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value and "contacts" in value:
                    for msg in value["messages"]:
                        message_id = msg.get("id")
                        text = msg.get("text", {}).get("body", "")
                        from_user = value["contacts"][0]["profile"]["name"]
                        from_id = value["contacts"][0]["wa_id"]
                        if message_id and text:
                            pending_messages[message_id] = (text, from_user, from_id)
                            threading.Thread(target=notify_admin, args=(message_id, text, from_user)).start()
        return jsonify(status="ok"), 200

def notify_admin(message_id, text, from_user):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Разрешить", callback_data=f"allow_{message_id}")],
        [types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message_id}")]
    ])
    msg = f"Сообщение из Instagram от {from_user}:\n\n{text}\n\nОтправить ответ?"
    asyncio.run(bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=msg, reply_markup=kb))

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    if call.data.startswith("allow_"):
        msg_id = call.data.split("_", 1)[1]
        data = pending_messages.get(msg_id)
        if data:
            user_input, _, from_id = data
            reply = generate_reply(user_input)
            url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": from_id,
                "type": "text",
                "text": {"body": reply}
            }
            headers = {"Authorization": f"Bearer {FACEBOOK_ACCESS_TOKEN}"}
            requests.post(url, json=payload, headers=headers)
            await call.answer("Ответ отправлен в Instagram.")
    elif call.data.startswith("reject_"):
        await call.answer("Сообщение отклонено.")

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def start_aiogram():
    asyncio.run(dp.start_polling(bot))

if name == "__main__":
    threading.Thread(target=run_flask).start()
    start_aiogram()
