import logging
import os
import uuid
import threading
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from flask import Flask, request, jsonify
import httpx
import asyncio

from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ID админов для Telegram (подставь своих!)
ADMINS = [621587126, 619318985]

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = Flask(__name__)

drafts = {}  # user_id: (question, reply, draft_id)

def get_gpt_response(prompt):
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Ты — бот WHY NOT Wakeboard. Общайся с клиентом, как опытный райдер и менеджер, дружелюбно, уверенно, на русском, английском или французском. Используй фирменный стиль и сленг, если уместно."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("WHY NOT: админ-панель. Сюда будут приходить заявки из Instagram для согласования.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_callback(call: CallbackQuery):
    uid = call.data.replace("approve_", "")
    for user_id, (question, reply, draft_id) in list(drafts.items()):
        if draft_id == uid:
            await send_instagram_reply(user_id, reply)
            await call.message.edit_text(f"✅ Ответ отправлен в Instagram!\n<b>Q:</b> {question}\n<b>A:</b> {reply}")
            drafts.pop(user_id)
            break

@dp.callback_query(F.data.startswith("edit_"))
async def edit_callback(call: CallbackQuery):
    uid = call.data.replace("edit_", "")
    for user_id, (question, reply, draft_id) in list(drafts.items()):
        if draft_id == uid:
            await call.message.answer(f"✏️ Пришли новый текст для ответа в Instagram:\n<b>Q:</b> {question}", reply_markup=None)
            dp._user_id_for_edit = user_id
            break

@dp.message(F.text)
async def edited_response(message: Message):
    user_id = getattr(dp, '_user_id_for_edit', None)
    if user_id and user_id in drafts:
        question, _, draft_id = drafts[user_id]
        reply = message.text.strip()
        await send_instagram_reply(user_id, reply)
        await message.answer(f"✅ Новый ответ отправлен в IG:\n<b>Q:</b> {question}\n<b>A:</b> {reply}")
        drafts.pop(user_id)
        dp._user_id_for_edit = None

async def send_instagram_reply(user_id, message_text):
    url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/messages"
    headers = {"Authorization": f"Bearer {FACEBOOK_ACCESS_TOKEN}"}
    data = {
        "messaging_product": "instagram",
        "recipient": {"id": user_id},
        "message": {"text": message_text}
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=data)
        logging.info(f"Sent reply to IG user {user_id}: {r.text}")

@app.route("/webhook/instagram", methods=["POST"])
def instagram_webhook():
    data = request.get_json()
    if "entry" in data:
        for entry in data["entry"]:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    text = msg.get("text")
                    user_id = msg.get("from")
                    if text:
                        ai_reply = get_gpt_response(text)
                        uid = str(uuid.uuid4())
                        drafts[user_id] = (text, ai_reply, uid)
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Отправить", callback_data=f"approve_{uid}"),
                             InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{uid}")]
                        ])
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        for admin in ADMINS:
                            loop.run_until_complete(
                                bot.send_message(
                                    admin,
                                    f"<b>IG-вопрос:</b> {text}\n<b>Черновик-ответ:</b> {ai_reply}",
                                    reply_markup=kb
                                )
                            )
    return jsonify({"status": "ok"})

@app.route("/webhook/instagram", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == "YOUR_VERIFY_TOKEN":  # подставь свой токен!
        return challenge
    return "error", 403

def start_aiogram():
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t = threading.Thread(target=start_aiogram)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
