# app/db/pool.py

import os
import asyncpg

db = None


async def init_db():
    global db

    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        raise Exception("DATABASE_URL не найден!")

    db = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        ssl="require",           # <--- обязательно для Railway
        min_size=1,
        max_size=10,
    )
    print("📦 PostgreSQL подключен!")


