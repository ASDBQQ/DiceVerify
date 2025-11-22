# app/handlers/balance.py

from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.bot import dp
from app.services.balances import (
    get_balance,
    get_ton_rate,
    pending_transfer_target,
    pending_transfer_amount,
    change_balance,
)
from app.services.transfers import add_transfer
from app.utils.keyboards import bottom_menu
from app.services.state_reset import reset_user_state
from app.config import MAIN_ADMIN_ID


@dp.message(F.text == "💼 Баланс")
async def balance_menu(message: Message):
    reset_user_state(message.from_user.id)

    bal_rub = get_balance(message.from_user.id)
    ton_rate = await get_ton_rate()
    ton_equiv = bal_rub / ton_rate if ton_rate else 0

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Пополнить (TON)", callback_data="topup")],
            [InlineKeyboardButton(text="💸 Перевод", callback_data="transfer")],
            [InlineKeyboardButton(text="🐢 Вывод TON", callback_data="withdraw")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back_main")],
        ]
    )

    await message.answer(
        f"📦 Ваш баланс: {ton_equiv:.4f} TON\n"
        f"≈ {bal_rub} ₽\n"
        f"Текущий курс: 1 TON = {ton_rate} ₽",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "back_main")
async def back_main(callback):
    reset_user_state(callback.from_user.id)
    await callback.message.answer("Главное меню:", reply_markup=bottom_menu())
    await callback.answer()


@dp.callback_query(F.data == "transfer")
async def transfer_start(callback):
    reset_user_state(callback.from_user.id)
    pending_transfer_target[callback.from_user.id] = True

    await callback.message.answer(
        "💳 *Перевод средств другому пользователю*\n\n"
        "1️⃣ Введите @username или ID пользователя.\n"
        "2️⃣ Затем бот попросит указать сумму.\n\n"
        "Важно: получатель должен хотя бы раз написать боту.",
        parse_mode="Markdown",
    )
    await callback.answer()


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







