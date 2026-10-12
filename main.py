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

# Render автоматически выдаст уникальный URL вашему приложению и запишет его в эту переменную среды
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://onrender.com")
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

SYSTEM_PROMPT = (
    "Ты — профессиональный, эмпатичный ИИ-психолог. Помогай пользователю методами КПТ.\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА ДЛЯ ТЕСТОВ И МЕТОДИК:\n"
    "1. Если пользователь хочет пройти тест, выбери подходящий психологический тест и начни его.\n"
    "2. Проводи тест строго ПОШАГОВО: задавай ровно ОДИН вопрос за раз. Жди ответа пользователя.\n"
    "3. В конце теста подведи итог, расшифруй баллы.\n"
    "ВАЖНО: Всегда отвечай строго на русском языке!"
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Серверная оперативная память для удержания контекста переписки {user_id: [сообщения]}
user_history = {}

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Пройти психологический тест 📝")) 
    builder.row(types.KeyboardButton(text="Мне тревожно 😰"), types.KeyboardButton(text="У меня выгорание 🔋"))
    builder.row(types.KeyboardButton(text="Практика 5-4-3-2-1 🌿"))
    builder.row(types.KeyboardButton(text="🗑️ Сбросить память чата"))
    return builder.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def start_command(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer(
        "Привет! Я твой личный ИИ-психолог. 🌿 Готов выслушать тебя или предложить интерактивный тест.",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    total_users = len(user_history)
    await message.answer(f"📊 *Панель администратора*\n\n👥 Активных сессий в памяти сервера: *{total_users}*", parse_mode="Markdown")

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    if user_text == "🗑️ Сбросить память чата":
        user_history[user_id] = []
        await message.answer("Память очищена. Начнем с чистого листа.", reply_markup=get_main_keyboard())
        return

    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append({"role": "user", "content": user_text})
    
    # Ограничиваем глубину памяти последними 8 сообщениями
    recent_history = user_history[user_id][-8:]
    messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + recent_history

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Пересылаем структурированный JSON через стабильный POST-запрос, 
    # который на серверах Render работает со 100% гарантией без обрывов
    url = "https://pollinations.ai"
    payload = {
        "messages": messages_to_send,
        "model": "openai",
        "jsonMode": False
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            bot_reply = response.text.strip()
            user_history[user_id].append({"role": "assistant", "content": bot_reply})
            await message.answer(bot_reply, reply_markup=get_main_keyboard())
        else:
            await message.answer("Извини, я немного отвлекся. Повтори мысль.", reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        await message.answer("Я отвлекся. Напиши еще раз, пожалуйста.", reply_markup=get_main_keyboard())

async def on_startup(bot: Bot) -> None:
    # При старте сервера автоматически регистрируем адрес Вебхука в Телеграме
    await bot.set_webhook(url=WEBHOOK_URL)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    # Порт автоматически выделится сервером через переменную среды
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
