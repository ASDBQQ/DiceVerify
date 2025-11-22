# app/services/balances.py

from typing import Dict, Any
from app.db.pool import db

# Балансы пользователей
balances: Dict[int, int] = {}

# Пополнения
pending_topup: Dict[int, Any] = {}

# Вывод средств
pending_withdraw: Dict[int, Any] = {}

# Переводы
pending_transfer_step: Dict[int, int] = {}      # 1 = ожидаем username, 2 = ожидаем сумму
pending_transfer_target: Dict[int, int] = {}    # кому перевод
temp_transfer: Dict[int, Any] = {}             # временная сумма перевода


def get_balance(uid: int) -> int:
    return balances.get(uid, 0)


def change_balance(uid: int, amount: int):
    balances[uid] = balances.get(uid, 0) + amount

