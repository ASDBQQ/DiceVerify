# app/db/games.py
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone

from app.db.pool import pool


async def upsert_game(g: Dict[str, Any]):
    """Создать/обновить игру в таблице games."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO games (
                id, creator_id, opponent_id, bet,
                creator_roll, opponent_roll, winner,
                finished, created_at, finished_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT(id) DO UPDATE SET
                creator_id = EXCLUDED.creator_id,
                opponent_id = EXCLUDED.opponent_id,
                bet = EXCLUDED.bet,
                creator_roll = EXCLUDED.creator_roll,
                opponent_roll = EXCLUDED.opponent_roll,
                winner = EXCLUDED.winner,
                finished = EXCLUDED.finished,
                created_at = EXCLUDED.created_at,
                finished_at = EXCLUDED.finished_at
        """,
            g["id"],
            g["creator_id"],
            g.get("opponent_id"),
            g["bet"],
            g.get("creator_roll"),
            g.get("opponent_roll"),
            str(g.get("winner")) if g.get("winner") is not None else None,
            1 if g.get("finished") else 0,
            g["created_at"].isoformat() if g.get("created_at") else None,
            g["finished_at"].isoformat() if g.get("finished_at") else None,
        )


async def get_user_games(uid: int) -> List[Dict[str, Any]]:
    """История игр пользователя (creator или opponent)."""
    if not pool:
        return []
    async with pool.acquire() as db:
        records = await db.fetch(
            """
            SELECT * FROM games
            WHERE creator_id = $1 OR opponent_id = $1
            ORDER BY created_at DESC
        """,
            uid,
        )
        return [dict(r) for r in records]


async def get_users_profit_and_games_30_days() -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Статистика по всем сыгранным играм за последние 30 дней
    (для рейтинга): прибыль и кол-во игр.
    """
    if not pool:
        return [], []

    delta_30_days = datetime.now(timezone.utc) - timedelta(days=30)

    async with pool.acquire() as db:
        # Берём все завершённые игры за 30 дней
        finished_games_records = await db.fetch(
            "SELECT * FROM games WHERE finished = 1 AND finished_at >= $1",
            delta_30_days.isoformat(),
        )
        finished_games = [dict(r) for r in finished_games_records]

        # Все пользователи
        all_uids_records = await db.fetch("SELECT user_id FROM users")
        all_uids = [row["user_id"] for row in all_uids_records]

    return finished_games, all_uids
