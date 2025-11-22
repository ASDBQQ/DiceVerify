# app/main.py
import asyncio
from datetime import datetime, timezone

from app.bot import bot, dp
from app.db.pool import init_db
from app.db.games import get_unfinished_games
from app.services.balances import user_balances, user_usernames
from app.services.ton import ton_deposit_worker, processed_ton_tx
from app.services import games as games_service  # games, next_game_id

# Импортируем handlers (важно: чтобы сработали декораторы)
from app.handlers import (
    start,
    profile,
    balance,
    admin,
    games_menu,
    raffle_menu,
    text,
)  # noqa: F401


async def main():
    print("🚀 Бот запущен!")

    # 1. Инициализация БД + загрузка пользователей, балансов, TON-транзакций
    await init_db(user_balances, user_usernames, processed_ton_tx)

    # 2. Восстанавливаем НЕзавершённые игры
    unfinished = await get_unfinished_games()

    for row in unfinished:
        gid = row["id"]
        games_service.games[gid] = {
            "id": gid,
            "creator_id": row["creator_id"],
            "opponent_id": row["opponent_id"],
            "bet": row["bet"],
            "creator_roll": row["creator_roll"],
            "opponent_roll": row["opponent_roll"],
            "winner": row["winner"],
            "finished": False,
            "created_at": datetime.fromisoformat(row["created_at"])
            if row.get("created_at") else datetime.now(timezone.utc),
            "finished_at": None,
        }

    # 3. Выставляем корректный next_game_id
    if games_service.games:
        games_service.next_game_id = max(games_service.games.keys()) + 1
    else:
        games_service.next_game_id = 1

    # 4. Запускаем TON воркер
    asyncio.create_task(ton_deposit_worker())

    # 5. Запускаем поллинг
    await dp.start_polling(bot)

