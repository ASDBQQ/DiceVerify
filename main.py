# app/main.py
import asyncio
from aiogram import Bot, Dispatcher

from app.bot import bot, dp
from app.db.pool import init_db

# Импортируем все роутеры
from app.handlers import (
    start,
    games_menu,
    balance,
    admin,
    text,
)
from app.handlers import profile   # <<< ВАЖНО: подключаем профиль


async def main():
    # Инициализация базы данных
    await init_db()

    # Подключаем обработчики
    dp.include_router(start.router)
    dp.include_router(games_menu.router)
    dp.include_router(balance.router)
    dp.include_router(admin.router)
    dp.include_router(profile.router)  # <<< ВОТ ЭТОГО НЕ ХВАТАЛО!
    dp.include_router(text.router)

    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


