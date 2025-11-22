# app/handlers/balance.py
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.bot import dp
from app.config import TON_WALLET_ADDRESS
from app.services.balances import (
    register_user,
    get_balance,
    user_usernames,
)
from app.services.ton import get_ton_rub_rate
from app.utils.formatters import format_rubles


# состояния для вывода и переводов (используются и в handlers/text.py)
pending_withdraw_step: dict[int, str] = {}
temp_withdraw: dict[int, dict] = {}

pending_transfer_step: dict[int, str] = {}
temp_transfer: dict[int, dict] = {}


async def format_balance_text(uid: int) -> str:
    bal = get_balance(uid)
    rate = await get_ton_rub_rate()
    ton_equiv = bal / rate if rate > 0 else 0
    return (
        f"💼 Ваш баланс: {ton_equiv:.4f} TON\n"
        f"≈ {format_rubles(bal)} ₽\n"
        f"Текущий курс: 1 TON ≈ {rate:.2f} ₽"
    )


@dp.message(F.text == "💼 Баланс")
async def msg_balance(m: types.Message):
    register_user(m.from_user)
    uid = m.from_user.id
    bal_text = await format_balance_text(uid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Пополнить (TON)", callback_data="deposit_menu")],
            [InlineKeyboardButton(text="🔄 Перевод", callback_data="transfer_menu")],
            [InlineKeyboardButton(text="💸 Вывод TON", callback_data="withdraw_menu")],
        ]
    )
    await m.answer(bal_text, reply_markup=kb)


@dp.callback_query(F.data == "deposit_menu")
async def cb_deposit_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    rate = await get_ton_rub_rate()
    half_ton = int(rate * 0.5)
    one_ton = int(rate * 1)

    ton_url = f"ton://transfer/{TON_WALLET_ADDRESS}?text=ID{uid}"

    text = (
        "💎 Пополнение через TON\n\n"
        f"1 TON ≈ {rate:.2f} ₽.\n"
        f"0.5 TON ≈ {format_rubles(half_ton)} ₽.\n"
        f"1 TON ≈ {format_rubles(one_ton)} ₽.\n\n"
        "Как пополнить:\n"
        "1️⃣ Откройте TON-кошелёк (Tonkeeper/@wallet).\n"
        f"2️⃣ Отправьте TON на адрес: <code>{TON_WALLET_ADDRESS}</code>\n"
        f"3️⃣ В комментарии к переводу укажите: <code>ID{uid}</code> (обязательно!).\n"
        "4️⃣ Бот автоматически зачислит ₽ по этому ID и отправит уведомление.\n\n"
        "Важно: 1 ₽ = 1 рубль (внутренняя валюта бота)."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💎 Открыть кошелёк", url=ton_url)]]
    )

    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "withdraw_menu")
async def cb_withdraw_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    bal = get_balance(uid)
    if bal <= 0:
        await callback.answer("Баланс нулевой.", show_alert=True)
        return

    pending_withdraw_step[uid] = "amount"
    temp_withdraw[uid] = {}

    rate = await get_ton_rub_rate()
    ton_equiv = bal / rate if rate > 0 else 0

    await callback.message.answer(
        "💸 Вывод средств в TON\n"
        f"Ваш баланс: {format_rubles(bal)} ₽ (≈ {ton_equiv:.4f} TON)\n"
        f"1 TON ≈ {rate:.2f} ₽.\n\n"
        "Введите сумму ₽ для вывода (целое число):"
    )
    await callback.answer()


@dp.callback_query(F.data == "transfer_menu")
async def cb_transfer_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    pending_transfer_step[uid] = "target"
    temp_transfer[uid] = {}
    await callback.message.answer(
        "🔄 Перевод ₽\n"
        "Введите ID или @username получателя.\n"
        "Важно: получатель должен хотя бы раз написать боту."
    )
    await callback.answer()


def resolve_user_by_username(username_str: str) -> int | None:
    uname = username_str.strip().lstrip("@").lower()
    for uid, uname_stored in user_usernames.items():
        if uname_stored and uname_stored.lower() == uname:
            return uid
    return None
