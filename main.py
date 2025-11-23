# app/main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot import bot, dp
from app.db.pool import init_db
from app.services.balances import user_balances, user_usernames
from app.services.ton import processed_ton_tx

import app.handlers  # важно: регистрирует хендлеры


async def main():
    logging.basicConfig(level=logging.INFO)

    # -----------------------------
    # 🔥 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
    # -----------------------------
    await init_db(
        user_balances=user_balances,
        user_usernames=user_usernames,
        processed_ton_tx=processed_ton_tx,
    )

    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
