# app/services/balances.py

from typing import Dict, Any

# Баланс пользователей
user_balances: Dict[int, int] = {}

# username по user_id (для переводов)
user_usernames: Dict[int, str] = {}

# ----- Пополнения -----
pending_topup: Dict[int, Any] = {}

# ----- Вывод -----
pending_withdraw: Dict[int, Any] = {}
temp_withdraw: Dict[int, Any] = {}

# ----- Переводы -----
pending_transfer_step: Dict[int, str] = {}       # "target" → ждем username, "amount" → ждём сумму
pending_transfer_target: Dict[int, int] = {}     # id получателя
temp_transfer: Dict[int, Any] = {}               # временная сумма


# 🟦 USER MANAGEMENT --------------------------------------------------------

def register_user(user):
    """Сохраняем username пользователя для переводов."""
    if user.username:
        user_usernames[user.id] = user.username


# 🟦 BALANCE ----------------------------------------------------------------

def get_balance(uid: int) -> int:
    return user_balances.get(uid, 0)


def change_balance(uid: int, amount: int):
    """Изменить баланс на +amount или -amount"""
    user_balances[uid] = user_balances.get(uid, 0) + amount


def set_balance(uid: int, amount: int):
    """Админская функция — установить баланс напрямую."""
    user_balances[uid] = amount
