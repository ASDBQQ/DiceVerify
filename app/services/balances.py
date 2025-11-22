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
    """Изменить баланс пользователя."""
    get_balance(uid)
    user_balances[uid] += delta
    _schedule_upsert_user(uid)


def set_balance(uid: int, value: int):
    """Установить баланс вручную (админ)."""
    user_balances[uid] = value
    _schedule_upsert_user(uid)


def register_user(user: types.User):
    """Регистрирует пользователя при первом сообщении."""
    uid = user.id

    # если юзера нет — создаём
    if uid not in user_balances:
        user_balances[uid] = START_BALANCE_COINS
        _schedule_upsert_user(uid, datetime.now(timezone.utc))

    if user.username:
        user_usernames[uid] = user.username
        _schedule_upsert_user(uid)
