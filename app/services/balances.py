# app/services/balances.py
import asyncio
from datetime import datetime, timezone
from typing import Optional

from aiogram import types

from app.config import START_BALANCE_COINS
from app.db.users import upsert_user
from app.db.pool import redis_pool, pool # <-- НОВОЕ


# УДАЛЕНЫ ГЛОБАЛЬНЫЕ СЛОВАРИ: user_balances и user_usernames


async def _check_and_load_user(uid: int, username: str | None) -> bool:
    """Проверяет наличие пользователя в Redis, если нет — загружает из Postgres или создает."""
    
    # 1. Проверяем наличие баланса в Redis
    if await redis_pool.exists(f"balance:{uid}"):
        # Если баланс есть, обновляем юзернейм (если он поменялся)
        if username:
            await redis_pool.set(f"username:{uid}", username)
        return True

    # 2. Если в Redis нет, ищем в Postgres
    async with pool.acquire() as db:
        record = await db.fetchrow(
            "SELECT username, balance, registered_at FROM users WHERE user_id = $1", uid
        )

    if record:
        # 3. Нашли в Postgres, кэшируем в Redis
        await redis_pool.set(f"balance:{uid}", record["balance"])
        if record["username"]:
            await redis_pool.set(f"username:{uid}", record["username"])
        if record["registered_at"]:
            await redis_pool.set(f"registered_at:{uid}", record["registered_at"].isoformat())
        return True

    # 4. Пользователя нет нигде: создаем в Postgres и Redis
    balance = START_BALANCE_COINS
    registered_at = datetime.now(timezone.utc)
    
    # Создаем/обновляем в Postgres
    await upsert_user(uid, username, balance, registered_at)
    
    # Кэш в Redis
    await redis_pool.set(f"balance:{uid}", balance)
    if username:
        await redis_pool.set(f"username:{uid}", username)
    await redis_pool.set(f"registered_at:{uid}", registered_at.isoformat())
    
    return True


async def get_balance(uid: int) -> int:
    """Асинхронно вернуть баланс пользователя из Redis, если его нет — создать/загрузить."""
    balance_bytes = await redis_pool.get(f"balance:{uid}")
    
    if balance_bytes is None:
        await _check_and_load_user(uid, None)
        balance_bytes = await redis_pool.get(f"balance:{uid}")
        
    return int(balance_bytes.decode() if balance_bytes else 0)


async def get_username(uid: int) -> str | None:
    """Вернуть username пользователя из Redis."""
    username_bytes = await redis_pool.get(f"username:{uid}")
    return username_bytes.decode() if username_bytes else None


async def register_user(user: types.User):
    """Регистрирует/обновляет пользователя и загружает его в Redis/DB."""
    uid = user.id
    username = user.username
    await _check_and_load_user(uid, username)


async def _async_db_update(uid: int, registered_at: datetime | None = None):
    """Асинхронное обновление в БД (fire-and-forget)."""
    username = await get_username(uid)
    balance = await get_balance(uid)
    try:
        # Теперь upsert_user ожидает async get_balance/get_username
        asyncio.create_task(upsert_user(uid, username, balance, registered_at))
    except RuntimeError:
        pass


async def change_balance(uid: int, delta: int):
    """Атомарно изменить баланс пользователя в Redis и запланировать обновление в БД."""
    
    # 1. Атомарное изменение в Redis (для масштабирования это критично)
    await redis_pool.incrby(f"balance:{uid}", delta)

    # 2. Запланировать обновление в БД (для персистентности)
    await _async_db_update(uid)


async def set_balance(uid: int, value: int):
    """Установить баланс вручную (админ) в Redis и запланировать обновление в БД."""
    
    # 1. Установка в Redis
    await redis_pool.set(f"balance:{uid}", value)

    # 2. Запланировать обновление в БД
    await _async_db_update(uid)
