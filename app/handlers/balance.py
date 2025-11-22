# app/handlers/balance.py
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.bot import dp, bot
from app.config import TON_WALLET_ADDRESS
from app.services.balances import (
    register_user,
    get_balance,
    change_balance,
    user_usernames,
)
from app.services.ton import get_ton_rub_rate
from app.utils.formatters import format_rubles
from app.utils.keyboards import bottom_menu

from app.services.transfers import add_transfer

# состояния
pending_withdraw_step: dict[int, str] = {}
temp_withdraw: dict[int, dict] = {}

pending_transfer_step: dict[int, str] = {}
temp_transfer: dict[int, dict] = {}

# вспомогательная функция поиска юзера
def resolve_user_by_username(username_str: str) -> int | None:
    uname = username_str.strip().lstrip("@").lower()
    for uid, stored in user_usernames.items():
        if stored and stored.lower() == uname:
            return uid
    return None


# форматирование баланса
async def format_balance_text(uid: int) -> str:
    bal = get_balance(uid)
    rate = await get_ton_rub_rate()
    ton_equiv = bal / rate if rate > 0 else 0
    return (
        f"💼 Ваш баланс: {ton_equiv:.4f} TON\n"
        f"≈ {format_rubles(bal)} ₽\n"
        f"Текущий курс: 1 TON ≈ {rate:.2f} ₽"
    )


# ===================== ОСНОВНОЕ МЕНЮ БАЛАНСА ============================
@dp.message(F.text == "💼 Баланс")
async def msg_balance(m: types.Message):
    register_user(m.from_user)
    uid = m.from_user.id
    text = await format_balance_text(uid)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Пополнить (TON)", callback_data="deposit_menu")],
            [InlineKeyboardButton(text="🔄 Перевод", callback_data="transfer_menu")],
            [InlineKeyboardButton(text="💸 Вывод TON", callback_data="withdraw_menu")],
            [
                InlineKeyboardButton(text="🐼 Помощь", callback_data="help_balance"),
                InlineKeyboardButton(text="⬅ Назад", callback_data="menu_start"),
            ],
        ]
    )
    await m.answer(text, reply_markup=kb)


# ========================= ПОПОЛНЕНИЕ TON ===============================
@dp.callback_query(F.data == "deposit_menu")
async def cb_deposit_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    rate = await get_ton_rub_rate()
    half = int(rate * 0.5)
    one = int(rate * 1)

    ton_url = f"ton://transfer/{TON_WALLET_ADDRESS}?text=ID{uid}"

    text = (
        "💎 Пополнение через TON\n\n"
        f"1 TON ≈ {rate:.2f} ₽\n"
        f"0.5 TON ≈ {format_rubles(half)} ₽\n"
        f"1 TON ≈ {format_rubles(one)} ₽\n\n"
        "Как пополнить:\n"
        "1️⃣ Откройте TON-кошелёк.\n"
        f"2️⃣ Отправьте TON на адрес: <code>{TON_WALLET_ADDRESS}</code>\n"
        f"3️⃣ В комментарии укажите: <code>ID{uid}</code>\n\n"
        "Бот автоматически зачислит ₽ после получения TON."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💎 Открыть кошелёк", url=ton_url)]]
    )

    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# =========================== ПЕРЕВОДЫ ====================================
@dp.callback_query(F.data == "transfer_menu")
async def cb_transfer_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    pending_transfer_step[uid] = "await_username"
    temp_transfer[uid] = {}

    await callback.message.answer(
        "🔄 *Перевод пользователю*\n\n"
        "1️⃣ Введите @username или ID пользователя.\n"
        "2️⃣ Затем бот попросит указать сумму перевода.\n\n"
        "Получатель должен хотя бы раз писать боту.",
        parse_mode="Markdown"
    )
    await callback.answer()


# ============================== ВЫВОД TON ================================
@dp.callback_query(F.data == "withdraw_menu")
async def cb_withdraw_menu(callback: CallbackQuery):
    uid = callback.from_user.id

    pending_withdraw_step[uid] = "await_ton_wallet"
    temp_withdraw[uid] = {}

    await callback.message.answer(
        "💸 *Вывод TON*\n\n"
        "1️⃣ Введите ваш TON-кошелёк.\n"
        "2️⃣ Затем укажите сумму для вывода.\n\n"
        "Заявки выполняются вручную.",
        parse_mode="Markdown"
    )
    await callback.answer()


# ============================ ПОМОЩЬ ====================================
@dp.callback_query(F.data == "help_balance")
async def cb_help_balance(callback: CallbackQuery):
    text = (
        "💳 *Помощь по балансу*\n\n"
        "• Пополнение только через TON.\n"
        "• Переводы доступны между пользователями.\n"
        "• Вывод выполняется вручную.\n"
        "• Курс TON обновляется автоматически."
    )

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# ========================== НАЗАД В МЕНЮ ================================
@dp.callback_query(F.data == "menu_start")
async def cb_balance_back(callback: CallbackQuery):
    """
    Возвращает пользователя в главное меню
    """
    await callback.message.answer(
        "Выберите раздел:",
        reply_markup=bottom_menu()
    )
    await callback.answer()






