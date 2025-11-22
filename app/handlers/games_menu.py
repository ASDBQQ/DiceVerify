# app/handlers/games_menu.py
from datetime import datetime, timezone

from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.bot import dp
from app.config import DICE_MIN_BET, DICE_BET_MIN_CANCEL_AGE
from app.services.balances import get_balance, change_balance
from app.services.games import (
    games,
    pending_bet_input,
    send_games_list,
    build_games_text,
    build_games_keyboard,
    build_user_stats_and_history,
    build_history_keyboard,
    build_rating_text,
    play_game,
)
from app.services.raffle import pending_raffle_bet_input
from app.utils.formatters import format_rubles


@dp.callback_query(F.data == "menu_games")
async def cb_menu_games(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Кости", callback_data="mode_dice")],
            [InlineKeyboardButton(text="🎩 Банкир", callback_data="mode_banker")],
        ]
    )
    await callback.message.answer("Выберите режим игры:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "create_game")
async def cb_create_game(callback: CallbackQuery):
    uid = callback.from_user.id
    pending_bet_input[uid] = True
    pending_raffle_bet_input.pop(uid, None)
    await callback.message.answer(
        f"Введите ставку (числом, в ₽). Минимум {DICE_MIN_BET} ₽:"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("game_open:"))
async def cb_game_open(callback: CallbackQuery):
    gid = int(callback.data.split(":", 1)[1])
    g = games.get(gid)

    if not g:
        return await callback.answer("Игра не найдена.", show_alert=True)
    if g["opponent_id"] is not None:
        return await callback.answer("Кто-то уже вступил!", show_alert=True)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✔ Вступить", callback_data=f"join_confirm:{gid}"
                )
            ],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu_games")],
        ]
    )

    await callback.message.answer(
        f"🎲 Игра №{gid}\n"
        f"💰 Ставка: {format_rubles(g['bet'])} ₽\n\n"
        "Хотите вступить?",
        reply_markup=kb,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("game_my:"))
async def cb_game_my(callback: CallbackQuery):
    uid = callback.from_user.id
    gid = int(callback.data.split(":", 1)[1])

    g = games.get(gid)
    if not g:
        return await callback.answer("Игра не найдена.", show_alert=True)
    if g["creator_id"] != uid:
        return await callback.answer("Это не ваша игра.", show_alert=True)
    if g["opponent_id"] is not None:
        return await callback.answer("Уже есть соперник.", show_alert=True)

    time_passed = datetime.now(timezone.utc) - g["created_at"]
    rows = []

    if time_passed < DICE_BET_MIN_CANCEL_AGE:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Отменить ставку", callback_data=f"cancel_game:{gid}"
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu_games")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await callback.message.answer(
        f"🎲 Ваша игра №{gid}\n"
        f"💰 Ставка: {format_rubles(g['bet'])} ₽\n\n"
        "Ожидание соперника...",
        reply_markup=kb,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("cancel_game:"))
async def cb_cancel_game(callback: CallbackQuery):
    uid = callback.from_user.id
    gid = int(callback.data.split(":", 1)[1])

    g = games.get(gid)
    if not g:
        return await callback.answer("Игра не найдена.", show_alert=True)
    if g["creator_id"] != uid:
        return await callback.answer("Это не ваша игра.", show_alert=True)
    if g["opponent_id"] is not None:
        return await callback.answer("Уже есть соперник.", show_alert=True)

    created_at = g["created_at"]
    if (datetime.now(timezone.utc) - created_at) > DICE_BET_MIN_CANCEL_AGE:
        return await callback.answer(
            "Ставку можно отменить только в течение первой минуты после создания.",
            show_alert=True,
        )

    bet = g["bet"]
    change_balance(uid, bet)
    del games[gid]

    await callback.message.answer(
        f"❌ Ставка №{gid} отменена. {format_rubles(bet)} ₽ возвращены на баланс."
    )
    await send_games_list(callback.message.chat.id, uid)
    await callback.answer()


@dp.callback_query(F.data.startswith("join_confirm:"))
async def cb_join_confirm(callback: CallbackQuery):
    uid = callback.from_user.id
    gid = int(callback.data.split(":", 1)[1])

    g = games.get(gid)
    if not g:
        return await callback.answer("Игра не найдена.", show_alert=True)
    if g["opponent_id"] is not None:
        return await callback.answer("Кто-то уже вступил!", show_alert=True)

    bet = g["bet"]
    if get_balance(uid) < bet:
        return await callback.answer("Недостаточно ₽.", show_alert=True)

    g["opponent_id"] = uid
    change_balance(uid, -bet)

    from app.db.games import upsert_game

    await upsert_game(g)

    await callback.message.answer(f"✅ Вы присоединились к игре №{gid}!")
    await callback.answer()

    await play_game(gid)


@dp.callback_query(F.data.startswith("my_games"))
async def cb_my_games(callback: CallbackQuery):
    uid = callback.from_user.id
    page = int(callback.data.split(":", 1)[1])

    stats, history = await build_user_stats_and_history(uid)
    kb = build_history_keyboard(history, page)

    await callback.message.answer(stats, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "refresh_games")
async def cb_refresh_games(callback: CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_text(
            build_games_text(),
            reply_markup=build_games_keyboard(uid),
        )
    except Exception:
        await callback.message.answer(
            build_games_text(),
            reply_markup=build_games_keyboard(uid),
        )
    await callback.answer("Обновлено!")


@dp.callback_query(F.data == "rating")
async def cb_rating(callback: CallbackQuery):
    text = await build_rating_text(callback.from_user.id)
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Кости", callback_data="help_dice")],
            [InlineKeyboardButton(text="🎩 Банкир", callback_data="help_banker")],
            [InlineKeyboardButton(text="💸 Баланс/Вывод", callback_data="help_balance")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu_games")],
        ]
    )
    await callback.message.answer("🐼 Выберите раздел помощи:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "help_dice")
async def cb_help_dice(callback: CallbackQuery):
    text = (
        "🎲 Помощь: Кости (1 на 1)\n\n"
        "1. Игроки ставят в банк сумму первоначальной ставки. Максимальное число игроков - 2.\n"
        "2. После того как игроки найдены, запускается розыгрыш.\n"
        "3. Игроки бросают кости, тот, кто выбросил больше - забирает весь банк. "
        "Результат генерируется на стороне Телеграм.\n"
        "4. Ставку можно отменить <b>только в течение первой минуты</b> после создания."
    )
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "help_banker")
async def cb_help_banker(callback: CallbackQuery):
    text = (
        "🎩 Помощь: Банкир (розыгрыш)\n\n"
        "1. Участники кладут в банк сумму равную самой первой ставке.\n"
        "2. Можно сделать не больше 10 ставок за игру.\n"
        "3. Чем больше вы положили в банк, тем выше ваш шанс на победу.\n"
        "4. После того, как набралось минимум 2 участника, запускается таймер до окончания игры.\n"
        "5. По истечении таймера начинается розыгрыш, система выбирает случайного победителя "
        "из всех, кто скинулся в банк. Победитель забирает весь банк (минус 1% комиссии).\n"
        "6. Ставку можно отменить в течение 10 минут после последней ставки."
    )
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "help_balance")
async def cb_help_balance(callback: CallbackQuery):
    text = (
        "💸 Помощь: Баланс и Вывод\n\n"
        "1. Пополнение: Отправьте TON на указанный адрес, обязательно указав в комментарии "
        "свой ID (формат IDXXXXXX). Бот автоматически зачислит ₽ по текущему курсу.\n"
        "2. Вывод: Вывод осуществляется в TON по курсу. Заявка отправляется администратору.\n"
        "3. Переводы: Доступны между игроками в разделе 'Баланс'.\n"
        "4. Комиссия: С каждой игры (Кости, Банкир) удерживается 1% комиссии."
    )
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "ignore")
async def cb_ignore(callback: CallbackQuery):
    await callback.answer()

