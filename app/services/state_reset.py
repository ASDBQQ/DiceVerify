# app/services/state_reset.py

from app.services.games import pending_bet_input
from app.services.raffle import pending_raffle_bet_input
from app.services.balances import (
    pending_transfer_target,
    pending_transfer_amount
)


def reset_user_state(uid: int):
    """Сбрасывает ВСЕ пользовательские состояния, чтобы бот не путал контекст."""
    pending_bet_input.pop(uid, None)
    pending_raffle_bet_input.pop(uid, None)
    pending_transfer_target.pop(uid, None)
    pending_transfer_amount.pop(uid, None)
