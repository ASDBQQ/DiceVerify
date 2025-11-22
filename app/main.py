# app/main.py
import asyncio

from app.bot import bot, dp
from app.db.pool import init_db
# УДАЛЕНЫ: from app.services.balances import user_balances, user_usernames
# УДАЛЕНЫ: from app.services.ton import processed_ton_tx
from app.services.ton import ton_deposit_worker
from app.handlers import (
    start, profile, balance, admin,
    games_menu, raffle_menu, text
)  # noqa: F401


async def main():
    print("🚀 Бот запущен!")

    # Инициализация базы и Redis. Аргументы больше не нужны.
    await init_db()

    # TON-пополнения — запускаем воркер
    asyncio.create_task(ton_deposit_worker())

    # Старт polling
    await dp.start_polling(bot)
