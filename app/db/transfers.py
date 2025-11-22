# app/db/transfers.py
from datetime import datetime, timezone

from .pool import pool


async def add_transfer(from_id: int, to_id: int, amount: int):
    """Сохранить перевод между пользователями."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO transfers (from_id, to_id, amount, at)
            VALUES ($1, $2, $3, $4)
        """,
            from_id,
            to_id,
            amount,
            # ИЗМЕНЕНИЕ: передаем объект datetime, а не строку isoformat()
            datetime.now(timezone.utc),
        )
