# app/main.py
import asyncio

from app.bot import bot, dp
from app.db.pool import init_db
from app.services.balances import user_balances, user_usernames
from app.services.ton import ton_deposit_worker, processed_ton_tx

# Импортируем хендлеры (они регистрируются через декораторы)
from app.handlers import (
    start, profile, balance, admin,
    games_menu, raffle_menu, text
)  # noqa: F401


async def main():
    print("🚀 Бот запущен!")

    # Инициализация базы
    await init_db(user_balances, user_usernames, processed_ton_tx)

    # TON-пополнения — запускаем воркер
    asyncio.create_task(ton_deposit_worker())

    # Старт polling
    await dp.start_polling(bot)
