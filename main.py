# app/main.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from app.config import BOT_TOKEN
from app.db.pool import init_db
from app.handlers import admin, balance, games_menu, start, text
from app.bot import dp


async def main():
    await init_db()   # <-- БЕЗ параметров!

    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)

    # Регистрация хендлеров (если у тебя dp.router(...))
    # но у тебя handlers импортируются сами через декораторы

    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

