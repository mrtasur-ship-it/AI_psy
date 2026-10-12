import asyncio
import logging
import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ================= АКТИВНЫЕ КЛЮЧИ ПРОЕКТА =================
TELEGRAM_TOKEN = "8444646491:AAGxTAzNEtRGGWI7SFGZjI1_JjxhJmXegRo"

# Твой рабочий API-ключ Groq
AI_API_KEY = os.getenv("GROQ_API_KEY")

# Мощная и полностью бесплатная модель на серверах Groq
MODEL_NAME = "llama-3.1-70b-versatile"

# Ссылка твоего приложения на Render
RENDER_EXTERNAL_URL = "https://onrender.com"
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

SYSTEM_PROMPT = (
    "Ты — профессиональный, эмпатичный ИИ-психолог. Твоя цель — слушать пользователя и помогать ему методами КПТ.\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА ДЛЯ ТЕСТОВ:\n"
    "1. Если пользователь хочет пройти тест, выбери подходящий психологический тест и начни его.\n"
    "2. Проводи тест строго ПОШАГОВО: задавай ровно ОДИН вопрос за раз. Жди ответа пользователя перед отправкой следующего вопроса.\n"
    "3. В конце теста подведи итог, расшифруй баллы.\n"
    "4. Пиши сообщения только на русском языке, не используй иностранные слова без необходимости."
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Оперативная память сервера для истории сообщений
user_history = {}

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Пройти психологический тест 📝")) 
    builder.row(types.KeyboardButton(text="Мне тревожно 😰"), types.KeyboardButton(text="У меня выгорание 🔋"))
    builder.row(types.KeyboardButton(text="🗑️ Сбросить память чата"))
    return builder.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def start_command(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer("Привет! Я твой личный ИИ-психолог. 🌿 Чем могу помочь?", reply_markup=get_main_keyboard())

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    if user_text == "🗑️ Сбросить память чата":
        user_history[user_id] = []
        await message.answer("Память очищена.", reply_markup=get_main_keyboard())
        return

    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append({"role": "user", "content": user_text})
    messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + user_history[user_id][-10:]

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Официальный защищенный эндпоинт Groq Cloud API
    url = "https://groq.com"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": messages_to_send,
        "model": MODEL_NAME,
        "temperature": 0.7
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            bot_reply = response.json()['choices'][0]['message']['content'].strip()
            
            # Убираем внутренние теги рассуждений, если они просочатся
            if "</think>" in bot_reply: 
                bot_reply = bot_reply.split("</think>")[-1].strip()

            user_history[user_id].append({"role": "assistant", "content": bot_reply})
            await message.answer(bot_reply, reply_markup=get_main_keyboard())
        else:
            logging.error(f"Сбой ИИ: {response.status_code} - {response.text}")
            await message.answer("Извини, я немного отвлекся. Повтори, пожалуйста, свою мысль.", reply_markup=get_main_keyboard())

    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        await message.answer("Извини, я немного отвлекся. Повтори, пожалуйста, свою мысль.", reply_markup=get_main_keyboard())

async def on_startup(bot: Bot) -> None:
    await bot.set_webhook(url=WEBHOOK_URL)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
