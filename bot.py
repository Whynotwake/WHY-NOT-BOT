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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = Flask(__name__)
pending_messages = {}

with open("bot_memory.txt", encoding="utf-8") as f:
    bot_memory = f.read()

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
        print("DEBUG: Webhook triggered")
        print("RAW JSON:", request.json)

        data = request.json
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                print("DEBUG: value =", value)

                if "messages" in value and "contacts" in value:
                    for msg in value["messages"]:
                        print("DEBUG: message =", msg)
                        message_id = msg.get("id")
                        text = msg.get("text", {}).get("body", "")
                        from_user = value["contacts"][0]["profile"].get("name", "Неизвестный")
                        from_id = value["contacts"][0]["wa_id"]
                        print(f"DEBUG: Parsed msg_id={message_id}, from={from_user}, text={text}")

                        if message_id and text:
                            pending_messages[message_id] = (text, from_user, from_id)
                            threading.Thread(target=notify_admin, args=(message_id, text, from_user)).start()

        return jsonify(status="ok"), 200@app.route("/privacy-policy")
def privacy_policy():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Privacy Policy</title>
    </head>
    <body>
        <h1>Privacy Policy</h1>
        <p><strong>Last Updated:</strong> 11.05.2025</p>
        <h2>1. Data Collection</h2>
        <p>Our app interacts with the Instagram API to receive messages from your Instagram account. As part of this process, we may collect the following data:</p>
        <ul>
            <li>The text of the messages received from your Instagram account.</li>
            <li>Information about the users who sent those messages.</li>
            <li>The date and time the messages were received.</li>
        </ul>
        <h2>2. Use of Data</h2>
        <ul>
            <li>To process and send messages to your server via webhook.</li>
            <li>To analyze and monitor the app’s performance.</li>
            <li>To ensure the proper functioning of the app and improve the user experience.</li>
        </ul>
        <h2>3. Data Transmission</h2>
        <p>We use webhooks to send messages to the server you have specified. We ensure that the data is transmitted securely and used only for the described purposes.</p>
        <h2>4. Data Storage</h2>
        <p>We store only essential operational data, which resides on your server. We do not store messages on our server unless explicitly configured.</p>
        <h2>5. Data Security</h2>
        <p>We implement reasonable security measures to prevent unauthorized access, loss, or alteration.</p>
        <h2>6. Data Access and Changes</h2>
        <p>You may request access, modification, or deletion of your data by contacting us using the details below.</p>
        <h2>7. Third-Party Services</h2>
        <p>We use third-party APIs like Instagram. Please review their policies separately.</p>
        <h2>8. Age Restrictions</h2>
        <p>This app is not for use by individuals under 13 years of age.</p>
        <h2>9. Changes to the Policy</h2>
        <p>We may update this policy. Updates will appear here with the revision date.</p>
    </body>
    </html>
    """

def notify_admin(message_id, text, from_user):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Разрешить", callback_data=f"allow_{message_id}")],
        [types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message_id}")]
    ])
    msg = f"Сообщение из Instagram от {from_user}:\n{text}\n\nОтправить ответ?"
    asyncio.run(bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=msg, reply_markup=kb))

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    if call.data.startswith("allow_"):
        msg_id = call.data.split("_", 1)[1]
        data = pending_messages.get(msg_id)
        if data:
            text, _, from_id = data
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": bot_memory},
                        {"role": "user", "content": text}
                    ]
                }
            )
            reply = response.json()["choices"][0]["message"]["content"]
            url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": from_id,
                "type": "text",
                "text": {"body": reply.strip()}
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
    
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    start_aiogram()
