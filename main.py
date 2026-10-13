import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from groq import Groq # Подключаем официальный неубиваемый клиент Groq

# ================= БЕЗОПАСНАЯ НАСТРОЙКА КЛЮЧЕЙ =================
# Бот заберет ключи из скрытых настроек Render, на GitHub их не будет!
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_API_KEY = os.getenv("GROQ_API_KEY")

# Стабильная бесплатная модель на серверах Groq
MODEL_NAME = "llama3-8b-8192"

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://ai-psy-1.onrender.com")
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

SYSTEM_PROMPT = (
    "Ты — профессиональный, эмпатичный ИИ-психолог. Твоя цель — слушать пользователя и помогать ему методами КПТ.\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА ДЛЯ ТЕСТОВ И МЕТОДИК:\n"
    "1. Если пользователь хочет пройти тест (или нажал кнопку теста), выбери подходящий психологический тест и начни его.\n"
    "2. Проводи тест строго ПОШАГОВО: задавай ровно ОДИН вопрос за раз. Жди ответа пользователя перед отправкой следующего вопроса.\n"
    "3. В конце теста подведи итог, расшифруй баллы и предложи подходящую психологическую технику для улучшения состояния.\n"
    "ВАЖНО: Всегда отвечай строго на русском языке!"
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализируем официальный ИИ-клиент через сохраненный ключ
ai_client = Groq(api_key=AI_API_KEY)

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
        await message.answer("Память чата полностью очищена.", reply_markup=get_main_keyboard())
        return

    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append({"role": "user", "content": user_text})
    messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + user_history[user_id][-8:]

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Официальный вызов Groq Cloud API через родной SDK (Ошибки 405 больше не будет!)
        completion = ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_to_send,
            temperature=0.7,
            max_tokens=600
        )
        
        bot_reply = completion.choices[0].message.content.strip()

        if "</think>" in bot_reply: 
            bot_reply = bot_reply.split("</think>")[-1].strip()

        user_history[user_id].append({"role": "assistant", "content": bot_reply})
        await message.answer(bot_reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logging.error(f"Ошибка ИИ Groq SDK: {e}")
        await message.answer(f"⚠️ Извини, я немного отвлекся. Напиши, пожалуйста, еще раз.", reply_markup=get_main_keyboard())

async def on_startup(bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
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
