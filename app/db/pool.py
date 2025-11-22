# app/db/pool.py
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import asyncpg
import aioredis # <-- НОВОЕ

# Глобальный пул подключений к PostgreSQL и Redis
pool: asyncpg.Pool | None = None
redis_pool: aioredis.Redis | None = None # <-- НОВОЕ


async def get_user_registered_at_from_redis(uid: int) -> Optional[datetime]:
    """Вспомогательная функция: Получить дату регистрации из Redis."""
    if not redis_pool:
        return None
    date_str_bytes = await redis_pool.get(f"registered_at:{uid}")
    if date_str_bytes:
        try:
            return datetime.fromisoformat(date_str_bytes.decode())
        except ValueError:
            pass
    return None


async def init_db(): # <-- ИЗМЕНЕНО: Убраны аргументы
    """Инициализация пулов подключений и создание таблиц + загрузка кэша в Redis."""
    global pool, redis_pool

    DATABASE_URL = os.environ.get("DATABASE_URL")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost") # <-- НОВОЕ
    if not DATABASE_URL:
        raise Exception(
            "Переменная окружения DATABASE_URL не найдена. "
            "Подключение к PostgreSQL невозможно."
        )

    pool = await asyncpg.create_pool(DATABASE_URL)
    # Инициализация Redis
    redis_pool = await aioredis.from_url(REDIS_URL) # <-- НОВОЕ

    async with pool.acquire() as db:
        # 1. Таблица users
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance INTEGER,
                registered_at TIMESTAMP WITH TIME ZONE -- <-- ИЗМЕНЕНО: был TEXT
            )
        """
        )

        # 2. Таблица games
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY,
                creator_id BIGINT,
                opponent_id BIGINT,
                bet INTEGER,
                creator_roll INTEGER,
                opponent_roll INTEGER,
                winner TEXT,
                finished SMALLINT,
                created_at TIMESTAMP WITH TIME ZONE, -- <-- ИЗМЕНЕНО: был TEXT
                finished_at TIMESTAMP WITH TIME ZONE -- <-- ИЗМЕНЕНО: был TEXT
            )
        """
        )

        # 3. Таблица raffle_rounds
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffle_rounds (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP WITH TIME ZONE, -- <-- ИЗМЕНЕНО: был TEXT
                finished_at TIMESTAMP WITH TIME ZONE, -- <-- ИЗМЕНЕНО: был TEXT
                winner_id BIGINT,
                total_bank INTEGER
            )
        """
        )

        # 4. Таблица raffle_bets (без изменений)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffle_bets (
                id SERIAL PRIMARY KEY,
                raffle_id INTEGER,
                user_id BIGINT,
                amount INTEGER
            )
        """
        )

        # 5. Таблица ton_deposits
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ton_deposits (
                tx_hash TEXT PRIMARY KEY,
                user_id BIGINT,
                ton_amount REAL,
                coins INTEGER,
                comment TEXT,
                at TIMESTAMP WITH TIME ZONE -- <-- ИЗМЕНЕНО: был TEXT
            )
        """
        )

        # 6. Таблица transfers
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transfers (
                id SERIAL PRIMARY KEY,
                from_id BIGINT,
                to_id BIGINT,
                amount INTEGER,
                at TIMESTAMP WITH TIME ZONE -- <-- ИЗМЕНЕНО: был TEXT
            )
        """
        )

        # 7. Загрузка пользователей в Redis (Миграция данных из PostgreSQL)
        records = await db.fetch("SELECT user_id, username, balance, registered_at FROM users")
        for record in records:
            uid = record["user_id"]
            username = record["username"]
            balance = record["balance"]
            registered_at = record["registered_at"]
            
            # Сохраняем в Redis
            await redis_pool.set(f"balance:{uid}", balance)
            if username:
                await redis_pool.set(f"username:{uid}", username)
            if registered_at:
                await redis_pool.set(f"registered_at:{uid}", registered_at.isoformat())

        # 8. Загрузка обработанных TON-транзакций (Миграция)
        records = await db.fetch("SELECT tx_hash FROM ton_deposits")
        for record in records:
            # Загружаем в Redis Set
            await redis_pool.sadd("processed_ton_tx", record["tx_hash"])
        
        # 9. Инициализация глобальных ID (для дальнейших правок games.py и raffle.py)
        await redis_pool.setnx("next_game_id", 1)
        await redis_pool.setnx("next_raffle_id", 1)
