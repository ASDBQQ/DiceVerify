# app/services/raffle.py
import asyncio
import random
from datetime import datetime, timezone, timedelta   # ← ДОБАВИТЬ timedelta
from typing import Dict, Any, Set

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.bot import bot
from app.config import (
    RAFFLE_MIN_BET,
    RAFFLE_MAX_BETS_PER_ROUND,
    RAFFLE_TIMER_SECONDS,
    MAIN_ADMIN_ID,
)
from app.db.raffle import upsert_raffle_round, add_raffle_bet
from app.services.balances import change_balance, get_balance, user_usernames
from app.utils.formatters import format_rubles


raffle_round: Dict[str, Any] | None = None
raffle_task: asyncio.Task | None = None
next_raffle_id: int = 1
pending_raffle_bet_input: Dict[int, bool] = {}


def build_raffle_text(uid: int) -> str:
    global raffle_round
    r = raffle_round

    if not r or r.get("finished") or not r.get("bets"):
        return (
            "🎩 Игра «Банкир»\n\n"
            "Сделайте первую ставку, чтобы запустить новый розыгрыш.\n\n"
            f"Минимальная ставка: {RAFFLE_MIN_BET} ₽.\n"
            f"До {RAFFLE_MAX_BETS_PER_ROUND} ставок на игрока за раунд.\n"
            f"После появления минимум 2 участников стартует таймер на {RAFFLE_TIMER_SECONDS} секунд,\n"
            "после чего случайный победитель забирает весь банк (минус 1% комиссии)."
        )

    entry_amount = r.get("entry_amount") or 0
    total_bets = len(r.get("bets", []))
    participants = r.get("participants", set())
    user_bets = r.get("user_bets", {}).get(uid, 0)
    bank = r.get("total_bank", 0)

    timer_line = ""
    draw_at = r.get("draw_at")
    if draw_at:
        seconds_left = int((draw_at - datetime.now(timezone.utc)).total_seconds())
        if seconds_left < 0:
            seconds_left = 0
        timer_line = f"\n⏳ До окончания раунда примерно {seconds_left} сек."
    else:
        need = max(0, 2 - len(participants))
        if need > 0:
            timer_line = f"\nОжидаем ещё {need} участника(ов) для запуска таймера."

    return (
        "🎩 Игра «Банкир» — текущий раунд\n\n"
        f"Фиксированная ставка: {format_rubles(entry_amount)} ₽\n"
        f"Общий банк: {format_rubles(bank)} ₽\n"
        f"Всего ставок: {total_bets}\n"
        f"Участников: {len(participants)}\n"
        f"Ваших ставок: {user_bets}"
        f"{timer_line}"
    )


def build_raffle_menu_keyboard(uid: int) -> InlineKeyboardMarkup:
    quick_buttons = [
        InlineKeyboardButton(
            text=f"{format_rubles(amount)} ₽",
            callback_data=f"raffle_quick:{amount}",
        )
        for amount in [a for a in [10, 100, 1000] if a >= RAFFLE_MIN_BET]
    ]
    rows = []
    if quick_buttons:
        rows.append(quick_buttons)

    rows.append(
        [InlineKeyboardButton(text="✏ Ввести сумму", callback_data="raffle_enter_amount")]
    )

    rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="raffle_refresh"),
            InlineKeyboardButton(text="⬅ Назад", callback_data="menu_games"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_raffle_menu(chat_id: int, uid: int):
    await bot.send_message(
        chat_id,
        build_raffle_text(uid),
        reply_markup=build_raffle_menu_keyboard(uid),
    )


def _ensure_raffle_round() -> Dict[str, Any]:
    global raffle_round, next_raffle_id
    if raffle_round is None or raffle_round.get("finished"):
        raffle_round = {
            "id": next_raffle_id,
            "created_at": datetime.now(timezone.utc),
            "finished_at": None,
            "entry_amount": None,
            "total_bank": 0,
            "bets": [],
            "participants": set(),
            "user_bets": {},
            "winner_id": None,
            "finished": False,
            "draw_at": None,
        }
        next_raffle_id += 1
    return raffle_round


async def _process_raffle_bet(uid: int, chat_id: int, amount: int) -> str:
    global raffle_task
    if amount < RAFFLE_MIN_BET:
        return f"Минимальная ставка в Банкире: {RAFFLE_MIN_BET} ₽."

    bal = get_balance(uid)
    if amount > bal:
        return "Недостаточно ₽ на балансе для этой ставки."

    r = _ensure_raffle_round()

    if r["entry_amount"] is None:
        r["entry_amount"] = amount
    elif amount != r["entry_amount"]:
        return (
            "В этом розыгрыше фиксированная ставка "
            f"{format_rubles(r['entry_amount'])} ₽.\n"
            "Вы можете участвовать только с этой суммой."
        )

    user_bets = r["user_bets"].get(uid, 0)
    if user_bets >= RAFFLE_MAX_BETS_PER_ROUND:
        return (
            "Вы уже сделали максимальное количество ставок в этом раунде "
            f"({RAFFLE_MAX_BETS_PER_ROUND})."
        )

    change_balance(uid, -amount)

    r["total_bank"] += amount
    r["bets"].append(uid)
    r["participants"].add(uid)
    r["user_bets"][uid] = user_bets + 1

    await add_raffle_bet(r["id"], uid, amount)

    if len(r["participants"]) >= 2 and r.get("draw_at") is None:
        r["draw_at"] = datetime.now(timezone.utc) + timedelta(seconds=RAFFLE_TIMER_SECONDS)
        raffle_task = asyncio.create_task(raffle_draw_worker(r["id"]))

    timer_line = ""
    if r.get("draw_at"):
        seconds_left = int((r["draw_at"] - datetime.now(timezone.utc)).total_seconds())
        if seconds_left < 0:
            seconds_left = 0
        timer_line = f"\n⏳ До окончания раунда примерно {seconds_left} сек."
    else:
        need = max(0, 2 - len(r["participants"]))
        if need > 0:
            timer_line = f"\nОжидаем ещё {need} участника(ов) для запуска таймера."

    return (
        "✅ Ставка в игре «Банкир» принята!\n\n"
        f"Сумма ставки: {format_rubles(amount)} ₽\n"
        f"Фиксированная ставка раунда: {format_rubles(r['entry_amount'])} ₽\n"
        f"Всего ставок в раунде: {len(r['bets'])}\n"
        f"Ваших ставок: {r['user_bets'][uid]}\n"
        f"Общий банк: {format_rubles(r['total_bank'])} ₽"
        f"{timer_line}"
    )


async def raffle_draw_worker(raffle_id: int):
    global raffle_round, raffle_task
    await asyncio.sleep(RAFFLE_TIMER_SECONDS)

    r = raffle_round
    if not r or r.get("finished") or r.get("id") != raffle_id:
        return

    await perform_raffle_draw()
    raffle_task = None


async def perform_raffle_draw():
    global raffle_round
    r = raffle_round
    if not r or r.get("finished") or not r.get("bets"):
        return

    participants: Set[int] = r.get("participants", set())
    if len(participants) < 2:
        entry_amount = r.get("entry_amount") or 0
        if entry_amount > 0:
            for uid in r.get("bets", []):
                change_balance(uid, entry_amount)
                try:
                    await bot.send_message(
                        uid,
                        "Розыгрыш «Банкир» отменён: недостаточно участников. "
                        "Ставка возвращена на баланс.",
                    )
                except Exception:
                    pass

        r["finished"] = True
        r["finished_at"] = datetime.now(timezone.utc)
        r["winner_id"] = None

        await upsert_raffle_round(
            {
                "created_at": r.get("created_at"),
                "finished_at": r.get("finished_at"),
                "winner_id": None,
                "total_bank": 0,
            }
        )
        return

    bank = r.get("total_bank", 0)
    winner_uid = random.choice(r["bets"])

    commission = bank // 100
    prize = bank - commission

    change_balance(winner_uid, prize)
    change_balance(MAIN_ADMIN_ID, commission)

    r["finished"] = True
    r["finished_at"] = datetime.now(timezone.utc)
    r["winner_id"] = winner_uid

    await upsert_raffle_round(
        {
            "created_at": r.get("created_at"),
            "finished_at": r.get("finished_at"),
            "winner_id": winner_uid,
            "total_bank": bank,
        }
    )

    winner_username = user_usernames.get(winner_uid)
    if winner_username:
        winner_name = f"@{winner_username}"
    else:
        winner_name = f"ID{winner_uid}"

    common_part = (
        "🎩 Розыгрыш «Банкир» завершён!\n\n"
        f"💰 Общий банк: {format_rubles(bank)} ₽\n"
        f"💸 Комиссия: {format_rubles(commission)} ₽ (1%)\n"
        f"🏆 Победитель: {winner_name}\n"
    )

    for uid in participants:
        if uid == winner_uid:
            personal = (
                f"\n🥳 Поздравляем! Вы выиграли {format_rubles(prize)} ₽ (после комиссии)."
            )
        else:
            personal = "\n😔 В этот раз не повезло. Попробуйте ещё!"

        balance_line = f"\n\n💼 Ваш баланс: {format_rubles(get_balance(uid))} ₽"

        try:
            await bot.send_message(uid, common_part + personal + balance_line)
        except Exception:
            pass

