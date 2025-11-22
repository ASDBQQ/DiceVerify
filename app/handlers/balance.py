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

# чтобы при переходе в баланс не мешали “висящие” состояния из игр/банкира
from app.services.games import pending_bet_input
from app.services.raffle import pending_raffle_bet_input


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
    """
    Главное меню баланса.
    Сюда попадаем с обычной клавиатуры.
    """
    register_user(m.from_user)
    uid = m.from_user.id

    # при входе в меню баланса чистим состояния игр/банкира/выводов/переводов
    pending_bet_input.pop(uid, None)
    pending_raffle_bet_input.pop(uid, None)
    pending_withdraw_step.pop(uid, None)
    temp_withdraw.pop(uid, None)
    pending_transfer_step.pop(uid, None)
    temp_transfer.pop(uid, None)

    bal_text = await format_balance_text(uid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Пополнить (TON)", callback_data="deposit_menu")],
            [InlineKeyboardButton(text="🔄 Перевод", callback_data="transfer_menu")],
            [InlineKeyboardButton(text="💸 Вывод TON", callback_data="withdraw_menu")],
            [InlineKeyboardButton(text="🐼 Помощь", callback_data="help_balance")],
        ]
    )
    await m.answer(bal_text, reply_markup=kb)


# ======================= ПОПОЛНЕНИЕ TON =======================

@dp.callback_query(F.data == "deposit_menu")
async def cb_deposit_menu(callback: CallbackQuery):
    uid = callback.from_user.id

    # на всякий случай тоже подчистим состояния игр/банкира
    pending_bet_input.pop(uid, None)
    pending_raffle_bet_input.pop(uid, None)

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
        f"3️⃣ В комментарии к переводу укажите: <code>ID{uid}</code> (обязательно!).\n\n"
        "После получения TON бот автоматически зачислит ₽ на ваш баланс."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Открыть кошелёк", url=ton_url)],
        ]
    )

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ============================ ВЫВОД ============================

@dp.callback_query(F.data == "withdraw_menu")
async def cb_withdraw_menu(callback: CallbackQuery):
    uid = callback.from_user.id

    # при начале вывода чистим состояния игр/банкира и старые выводы/переводы
    pending_bet_input.pop(uid, None)
    pending_raffle_bet_input.pop(uid, None)
    pending_withdraw_step.pop(uid, None)
    temp_withdraw.pop(uid, None)
    pending_transfer_step.pop(uid, None)
    temp_transfer.pop(uid, None)

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
        "Введите сумму в ₽ для вывода (целое число):"
    )
    await callback.answer()


# =========================== ПЕРЕВОД ===========================

@dp.callback_query(F.data == "transfer_menu")
async def cb_transfer_menu(callback: CallbackQuery):
    uid = callback.from_user.id

    # самое главное: гасим режим ввода ставки в кости и банкира
    pending_bet_input.pop(uid, None)
    pending_raffle_bet_input.pop(uid, None)

    # и сбрасываем предыдущие попытки перевода/вывода
    pending_withdraw_step.pop(uid, None)
    temp_withdraw.pop(uid, None)
    pending_transfer_step[uid] = "target"
    temp_transfer[uid] = {}

    await callback.message.answer(
        "🔄 Перевод ₽\n"
        "Введите ID или @username получателя.\n"
        "Важно: получатель должен хотя бы раз написать боту."
    )
    await callback.answer()


# ==================== ПОИСК ПОЛУЧАТЕЛЯ ПО @ ===================

def resolve_user_by_username(username_str: str) -> int | None:
    """
    Ищем user_id по @username в сохранённом словаре user_usernames.
    Используется в handlers/text.py.
    """
    uname = username_str.strip().lstrip("@").lower()
    for uid, stored in user_usernames.items():
        if stored and stored.lower() == uname:
            return uid
    return None


# ============================ ПОМОЩЬ ===========================

@dp.callback_query(F.data == "help_balance")
async def cb_help_balance(callback: CallbackQuery):
    text = (
        "💳 *Помощь: Баланс / Вывод*\n\n"
        "• Пополнение через TON.\n"
        "• Средства приходят за 5–30 секунд.\n"
        "• Комиссия сети оплачивается отправителем.\n"
        "• Вывод возможен через администратора (заявка уходит в личку админам).\n"
        "• Переводы работают только между пользователями, которые уже писали боту."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()








