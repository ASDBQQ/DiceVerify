# app/db/users.py
from datetime import datetime, timezone
from typing import Optional

# Импортируем pool и новую функцию из pool.py
from .pool import pool, get_user_registered_at_from_redis # <-- ИЗМЕНЕНО

async def upsert_user(
    uid: int,
    username: str | None,
    balance: int,
    registered_at: Optional[datetime] = None,
):
    """Создать/обновить пользователя в БД."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, balance, registered_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT(user_id) DO UPDATE SET
                username=EXCLUDED.username,
                balance=EXCLUDED.balance
        """,
            uid,
            username,
            balance,
            # Asyncpg сам обрабатывает объект datetime для TIMESTAMP WITH TIME ZONE
            registered_at if registered_at else datetime.now(timezone.utc), # <-- ИЗМЕНЕНО
        )


async def get_user_registered_at(uid: int) -> Optional[datetime]:
    """Получить дату регистрации пользователя. Сначала из Redis, потом из БД."""
    
    # 1. Сначала проверяем Redis (быстрее)
    redis_date = await get_user_registered_at_from_redis(uid)
    if redis_date:
        return redis_date
        
    # 2. Если в Redis нет, ищем в Postgres
    if not pool:
        return None
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT registered_at FROM users WHERE user_id = $1",
            uid,
        )
        if row and row["registered_at"]:
            # Asyncpg возвращает datetime объект
            return row["registered_at"] 
            
    return None
