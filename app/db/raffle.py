# app/db/raffle.py
from typing import Any, Dict

from .pool import pool


async def upsert_raffle_round(r: Dict[str, Any]):
    """Сохранить результат раунда 'Банкир'."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO raffle_rounds (created_at, finished_at, winner_id, total_bank)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT(id) DO UPDATE SET
                created_at=EXCLUDED.created_at,
                finished_at=EXCLUDED.finished_at,
                winner_id=EXCLUDED.winner_id,
                total_bank=EXCLUDED.total_bank
        """,
            r["created_at"].isoformat() if r.get("created_at") else None,
            r["finished_at"].isoformat() if r.get("finished_at") else None,
            r.get("winner_id"),
            r.get("total_bank", 0),
        )


async def add_raffle_bet(raffle_id: int, user_id: int, amount: int):
    """Добавить ставку пользователя в конкретный раунд."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO raffle_bets (raffle_id, user_id, amount)
            VALUES ($1, $2, $3)
        """,
            raffle_id,
            user_id,
            amount,
        )


async def get_user_raffle_bets_count(uid: int) -> int:
    """Количество раундов Банкира, где участвовал пользователь."""
    if not pool:
        return 0
    async with pool.acquire() as db:
        count = await db.fetchval(
            "SELECT COUNT(DISTINCT raffle_id) FROM raffle_bets WHERE user_id = $1",
            uid,
        )
        return count if count is not None else 0


async def get_user_bets_in_raffle(raffle_id: int, user_id: int) -> int:
    """Количество ставок пользователя в конкретном раунде Банкира."""
    if not pool:
        return 0
    async with pool.acquire() as db:
        count = await db.fetchval(
            "SELECT COUNT(*) FROM raffle_bets WHERE raffle_id = $1 AND user_id = $2",
            raffle_id,
            user_id,
        )
        return count if count is not None else 0
