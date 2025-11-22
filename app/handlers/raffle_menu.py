# app/handlers/raffle_menu.py
from aiogram import F
from aiogram.types import CallbackQuery

from app.bot import dp
from app.config import RAFFLE_MIN_BET
from app.services.raffle import (
    pending_raffle_bet_input,
    _process_raffle_bet,
    send_raffle_menu,
)
from app.services.games import pending_bet_input


@dp.callback_query(F.data == "raffle_make_bet")
async def cb_raffle_make_bet(callback: CallbackQuery):
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    msg_text = await _process_raffle_bet(uid, chat_id, RAFFLE_MIN_BET)
    await callback.message.answer(msg_text)
    await callback.answer()


@dp.callback_query(F.data.startswith("raffle_quick:"))
async def cb_raffle_quick(callback: CallbackQuery):
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    try:
        amount = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная сумма.", show_alert=True)
        return

    msg_text = await _process_raffle_bet(uid, chat_id, amount)
    await callback.message.answer(msg_text)
    await callback.answer()


@dp.callback_query(F.data == "raffle_enter_amount")
async def cb_raffle_enter_amount(callback: CallbackQuery):
    uid = callback.from_user.id
    pending_raffle_bet_input[uid] = True
    pending_bet_input.pop(uid, None)

    await callback.message.answer(
        "Введите сумму ₽ для участия в Банкире.\n"
        f"Минимальная ставка: {RAFFLE_MIN_BET} ₽."
    )
    await callback.answer()


@dp.callback_query(F.data == "raffle_refresh")
async def cb_raffle_refresh(callback: CallbackQuery):
    await send_raffle_menu(callback.message.chat.id, callback.from_user.id)
    await callback.answer("Обновлено!")


@dp.callback_query(F.data == "raffle_back")
async def cb_raffle_back(callback: CallbackQuery):
    await send_raffle_menu(callback.message.chat.id, callback.from_user.id)
    await callback.answer()
