# app/services/balances.py

from typing import Dict, Any

# Храним балансы пользователей
user_balances: Dict[int, int] = {}

# Храним username → id пользователя (для переводов)
user_usernames: Dict[int, str] = {}

# --- Пополнения ---
pending_topup: Dict[int, Any] = {}

# --- Вывод ---
pending_withdraw: Dict[int, Any] = {}
temp_withdraw: Dict[int, Any] = {}

# --- Переводы ---
pending_transfer_step: Dict[int, str] = {}      # "target" / "amount"
pending_transfer_target: Dict[int, int] = {}    # id получателя
temp_transfer: Dict[int, Any] = {}             # сумма перевода


# ----------------------- ФУНКЦИИ -----------------------

def register_user(user):
    """Сохраняем username пользователя для переводов"""
    if user.username:
        user_usernames[user.id] = user.username


def get_balance(uid: int) -> int:
    return user_balances.get(uid, 0)


def change_balance(uid: int, amount: int):
    user_balances[uid] = user_balances.get(uid, 0) + amount
