import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from groq import AsyncGroq

# ================= НАСТРОЙКА ОКРУЖЕНИЯ =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_API_KEY = os.getenv("GROQ_API_KEY")

# Белый список (0 — выключено, конкретный ID — приватный режим)
ADMIN_ID = 7706526704 

# Актуальная флагманская модель Groq
DEFAULT_MODEL = "llama-3.3-70b-specdec"
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://onrender.com")
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

SYSTEM_PROMPT = (
    "Ты — professional, эмпатичный ИИ-психолог. Твоя цель — слушать пользователя и помогать ему методами КПТ.\n"
    "Проводи тесты строго ПОШАГОВО: задавай ровно ОДИН вопрос за раз. Жди ответа.\n"
    "ВАЖНО: Всегда отвечай строго на русском языке!"
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
ai_client = AsyncGroq(api_key=AI_API_KEY)

# Временное in-memory хранилище аналитики
user_metadata = {}
users_analytics = {}

class ChatStates(StatesGroup):
    processing = State()  # Защита от спама, пока ИИ думает

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Пройти психологический тест 📝"))
    builder.row(types.KeyboardButton(text="Мне тревожно 😰"), types.KeyboardButton(text="У меня выгорание 🔋"))
    builder.row(types.KeyboardButton(text="🗑️ Сбросить память чата"))
    return builder.as_markup(resize_keyboard=True)

def track_user_activity(user: types.User):
    uid = user.id
    if uid not in users_analytics:
        users_analytics[uid] = {
            "full_name": user.full_name,
            "username": f"@{user.username}" if user.username else "нет никнейма",
            "messages_count": 0
        }
    users_analytics[uid]["messages_count"] += 1

def is_access_allowed(user_id: int) -> bool:
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        return False
    return True

@dp.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    track_user_activity(message.from_user)

    if not is_access_allowed(user_id):
        await message.answer("🔒 Извини, этот бот является приватным ИИ-ассистентом.")
        return

    await state.set_state(None)
    await state.set_data({"history": []})
    
    user_metadata[user_id] = datetime.now()
    await message.answer("Привет, создатель! Твой личный ИИ-психолог на связи. 🌿 Чем могу помочь?", reply_markup=get_main_keyboard())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    if not is_access_allowed(user_id):
        await message.answer("🔒 У тебя нет прав доступа к этой команде.")
        return

    session_duration = "Сессия еще не начата. Нажми /start"
    if user_id in user_metadata:
        diff = datetime.now() - user_metadata[user_id]
        session_duration = f"{int(diff.total_seconds() // 60)} мин. {int(diff.total_seconds() % 60)} сек."

    if users_analytics:
        users_text = "".join(
            f"👤 *{data['full_name']}* ({data['username']})\n"
            f"└ ID: `{uid}` | Реплик: *{data['messages_count']}*\n\n"
            for uid, data in users_analytics.items()
        )
    else:
        users_text = "В базе активности пока пусто."

    admin_text = (
        "📊 *Панель управления создателя бота*\n\n"
        f"👥 Всего уникальных пользователей: *{len(users_analytics)}*\n\n"
        f"📈 *Детальная активность:*\n\n{users_text}"
        f"⏱ Время текущей сессии: *{session_duration}*"
    )
    await message.answer(admin_text)

@dp.message(F.text == "🗑️ Сбросить память чата")
async def reset_memory(message: types.Message, state: FSMContext):
    if not is_access_allowed(message.from_user.id):
        await message.answer("🔒 Доступ ограничен.")
        return
        
    await state.set_data({"history": []})
    user_metadata[message.from_user.id] = datetime.now()
    await message.answer("Память чата очищена.", reply_markup=get_main_keyboard())

# Хэндлер-заглушка от спама
@dp.message(ChatStates.processing)
async def handle_spam(message: types.Message):
    await message.answer("⏳ Я еще обдумываю твой предыдущий ответ. Пожалуйста, подожди секунду...")

# Универсальный обработчик диалога
@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    global DEFAULT_MODEL
    user_id = message.from_user.id
    user_text = message.text
    
    current_state = await state.get_state()
    if current_state == ChatStates.processing.state:
        await handle_spam(message)
        return

    track_user_activity(message.from_user)

    if not is_access_allowed(user_id):
        await message.answer("🔒 Доступ ограничен.")
        return

    # Включаем состояние обработки запроса
    await state.set_state(ChatStates.processing)

    state_data = await state.get_data()
    history = state_data.get("history", [])
    history.append({"role": "user", "content": user_text})

    messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    bot_reply = ""
    current_model = DEFAULT_MODEL

    try:
        completion = await ai_client.chat.completions.create(
            model=current_model,
            messages=messages_to_send,
            temperature=0.7,
            max_tokens=600
        )
        bot_reply = completion.choices.message.content.strip()
    except Exception as e:
        logging.error(f"💥 Ошибка базовой модели {current_model}: {e}")
        try:
            models_list = await ai_client.models.list()
            active_models = [
                m.id for m in models_list.data 
                if not any(x in m.id.lower() for x in ["preview", "whisper", "audio", "guard", "vision", "telemetry", "oss", "orpheus", "allam"])
            ]
            
            if active_models:
                current_model = active_models[0]
                DEFAULT_MODEL = current_model 
                logging.info(f"🔄 Успешно переключился на рабочую текстовую модель: {current_model}")
                
                completion = await ai_client.chat.completions.create(
                    model=current_model,
                    messages=messages_to_send,
                    temperature=0.7,
                    max_tokens=600
                )
                bot_reply = completion.choices.message.content.strip()
        except Exception as critical_error:
            logging.error(f"🚨 Полный крах шлюза ИИ: {critical_error}")

    # Сбрасываем техническое состояние в None, сохраняя данные истории диалога
    await state.set_state(None)
    
    if bot_reply:
        if "</think>" in bot_reply:
            bot_reply = bot_reply.split("</think>")[-1].strip()

        history.append({"role": "assistant", "content": bot_reply})
        await state.set_data({"history": history})
        await message.answer(bot_reply, reply_markup=get_main_keyboard())
    else:
        await state.set_data({"history": history})
        await message.answer("⚠️ Ошибка шлюза ИИ. Попробуйте позже.", reply_markup=get_main_keyboard())

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
