# app/handlers/text.py
from datetime import datetime, timezone

from aiogram import types
from aiogram.types import Message

from app.bot import dp, bot
from app.config import DICE_MIN_BET, ADMIN_IDS
from app.db.games import upsert_game
from app.db.transfers import add_transfer
from app.handlers.balance import (
    pending_withdraw_step,
    temp_withdraw,
    pending_transfer_step,
    temp_transfer,
    resolve_user_by_username,
)
from app.services.balances import (
    register_user,
    get_balance,
    change_balance,
)
from app.services.games import (
    games,
    pending_bet_input,
    next_game_id,
    send_games_list,
)
from app.services.raffle import pending_raffle_bet_input, _process_raffle_bet
from app.services.ton import get_ton_rub_rate
from app.utils.formatters import format_rubles


@dp.message()
async def process_text(m: Message):
    register_user(m.from_user)
    uid = m.from_user.id
    text = (m.text or "").strip()

    if text.startswith("/"):
        return

    # 1) ставка для костей
    if pending_bet_input.get(uid):
        if not text.isdigit():
            return await m.answer("Введите корректную ставку (число):")
        bet = int(text)
        if bet < DICE_MIN_BET:
            return await m.answer(f"Минимальная ставка {DICE_MIN_BET} ₽.")
        if bet > get_balance(uid):
            return await m.answer("Недостаточно ₽ на балансе!")

        global next_game_id
        gid = next_game_id
        next_game_id += 1

        games[gid] = {
            "id": gid,
            "creator_id": uid,
            "opponent_id": None,
            "bet": bet,
            "creator_roll": None,
            "opponent_roll": None,
            "winner": None,
            "finished": False,
            "created_at": datetime.now(timezone.utc),
            "finished_at": None,
        }

        change_balance(uid, -bet)
        pending_bet_input.pop(uid)

        await upsert_game(games[gid])

        await m.answer(f"✅ Игра №{gid} создана!")
        return await send_games_list(m.chat.id, uid)

    # 2) вывод — сумма
    if pending_withdraw_step.get(uid) == "amount":
        if not text.isdigit():
            return await m.answer("Введите сумму числом:")
        amount = int(text)
        bal = get_balance(uid)
        if amount <= 0:
            return await m.answer("Сумма должна быть > 0.")
        if amount > bal:
            return await m.answer(
                f"Недостаточно ₽. Ваш баланс: {format_rubles(bal)} ₽."
            )
        temp_withdraw[uid]["amount"] = amount
        pending_withdraw_step[uid] = "details"

        rate = await get_ton_rub_rate()
        ton_amount = amount / rate if rate > 0 else 0
        approx = f"{ton_amount:.4f} TON"
        return await m.answer(
            "💸 Вывод в TON\n"
            f"Сумма: {format_rubles(amount)} ₽ (≈ {approx})\n\n"
            "Напишите комментарий к выводу (например, удобное время, TON-кошелёк, доп. информация):"
        )

    # 3) вывод — реквизиты
    if pending_withdraw_step.get(uid) == "details":
        details = text
        amount = temp_withdraw[uid]["amount"]
        user = m.from_user
        username = user.username
        if username:
            mention = f"@{username}"
            link = f"https://t.me/{username}"
        else:
            mention = f"id {uid}"
            link = f"tg://user?id={uid}"

        rate = await get_ton_rub_rate()
        ton_amount = amount / rate if rate > 0 else 0
        ton_text = f"{ton_amount:.4f} TON"

        msg_admin = (
            "💸 НОВАЯ ЗАЯВКА НА ВЫВОД (TON)\n\n"
            f"👤 Пользователь: {mention}\n"
            f"🆔 user_id: {uid}\n"
            f"🔗 Профиль: {link}\n\n"
            f"💰 Сумма: {format_rubles(amount)} ₽\n"
            f"💎 Эквивалент: {ton_text}\n"
            f"📄 Комментарий: {details}\n\n"
            "После фактической отправки TON уменьшите баланс через /removebalance или /setbalance."
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, msg_admin)
            except Exception:
                pass

        await m.answer(
            "✅ Заявка на вывод отправлена администратору.\n"
            "После обработки вам отправят TON на указанные реквизиты."
        )

        pending_withdraw_step.pop(uid, None)
        temp_withdraw.pop(uid, None)
        return

    # 4) перевод — выбор получателя
    if pending_transfer_step.get(uid) == "target":
        target_id: int | None = None
        if text.startswith("@"):
            target_id = resolve_user_by_username(text)
        elif text.isdigit():
            target_id = int(text)
        else:
            target_id = resolve_user_by_username(text)

        if not target_id:
            return await m.answer(
                "Не удалось найти пользователя.\n"
                "Убедитесь, что он уже писал боту, и введите его ID или @username."
            )
        if target_id == uid:
            return await m.answer("Нельзя переводить самому себе.")

        temp_transfer[uid]["target_id"] = target_id
        pending_transfer_step[uid] = "amount_transfer"
        return await m.answer("Введите сумму ₽ для перевода (минимум 1):")

    # 5) перевод — сумма
    if pending_transfer_step.get(uid) == "amount_transfer":
        if not text.isdigit():
            return await m.answer("Введите сумму числом:")
        amount = int(text)
        if amount <= 0:
            return await m.answer("Сумма должна быть > 0.")
        bal = get_balance(uid)
        if amount > bal:
            return await m.answer(
                f"Недостаточно ₽. Ваш баланс: {format_rubles(bal)} ₽."
            )

        target_id = temp_transfer[uid].get("target_id")
        if not target_id:
            pending_transfer_step.pop(uid, None)
            temp_transfer.pop(uid, None)
            return await m.answer("Ошибка: не найден получатель, попробуйте ещё раз.")

        change_balance(uid, -amount)
        change_balance(target_id, amount)

        await add_transfer(uid, target_id, amount)

        await m.answer(
            "✅ Перевод выполнен.\n"
            f"Вы отправили {format_rubles(amount)} ₽ пользователю ID {target_id}.\n"
            f"Ваш новый баланс: {format_rubles(get_balance(uid))} ₽."
        )
        try:
            await bot.send_message(
                target_id,
                f"🔄 Вам перевели {format_rubles(amount)} ₽ от пользователя ID {uid}.\n"
                f"Ваш новый баланс: {format_rubles(get_balance(target_id))} ₽.",
            )
        except Exception:
            pass

        pending_transfer_step.pop(uid, None)
        temp_transfer.pop(uid, None)
        return

    # 6) ввод суммы для Банкира
    if pending_raffle_bet_input.get(uid):
        if not text.isdigit():
            return await m.answer("Введите сумму числом (₽) для участия в Банкире:")
        amount = int(text)
        pending_raffle_bet_input.pop(uid, None)
        msg_text = await _process_raffle_bet(uid, m.chat.id, amount)
        return await m.answer(msg_text)

    await m.answer("Используйте меню или /start.")
