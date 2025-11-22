# app/services/balances.py
import asyncio
from datetime import datetime, timezone
from typing import Dict

from aiogram import types

from app.config import START_BALANCE_COINS
from app.db.users import upsert_user


# Кэш балансов и username
user_balances: Dict[int, int] = {}
user_usernames: Dict[int, str] = {}


def get_balance(uid: int) -> int:
    """Вернуть баланс пользователя, если его нет — создать."""
    if uid not in user_balances:
        user_balances[uid] = START_BALANCE_COINS
    return user_balances[uid]


def _schedule_upsert_user(uid: int, registered_at: datetime | None = None):
    """Асинхронное обновление в БД (fire-and-forget)."""
    username = user_usernames.get(uid)
    balance = user_balances.get(uid, 0)
    try:
        asyncio.create_task(upsert_user(uid, username, balance, registered_at))
    except RuntimeError:
        pass


def change_balance(uid: int, delta: int):
    """Изменить баланс и сохранить изменения в БД."""
    get_balance(uid)
    user_balances[uid] += delta

    # Сохраняем в PostgreSQL КАЖДЫЙ раз
    asyncio.create_task(
        upsert_user(
            uid,
            user_usernames.get(uid),
            user_balances[uid],
        )
    )


def set_balance(uid: int, value: int):
    """Принудительно установить баланс в БД."""
    user_balances[uid] = value

    asyncio.create_task(
        upsert_user(
            uid,
            user_usernames.get(uid),
            user_balances[uid],
        )
    )


def register_user(user: types.User):
    uid = user.id

    # Если пользователь впервые — создаём в БД и в кэше
    if uid not in user_balances:
        user_balances[uid] = START_BALANCE_COINS

        asyncio.create_task(
            upsert_user(
                uid,
                user.username,
                user_balances[uid],
                datetime.now(timezone.utc),
            )
        )

    # Обновляем username при каждом входе
    if user.username:
        user_usernames[uid] = user.username

        asyncio.create_task(
            upsert_user(
                uid,
                user.username,
                user_balances[uid],
            )
        )


