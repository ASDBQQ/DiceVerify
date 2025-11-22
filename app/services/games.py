# app/services/games.py
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.bot import bot
from app.config import (
    HISTORY_LIMIT,
    HISTORY_PAGE_SIZE,
    MAIN_ADMIN_ID,
)
from app.db.games import (
    get_user_games,
    get_users_profit_and_games_30_days,
    get_user_dice_games_count,
    upsert_game,
)
from app.services.balances import change_balance, get_balance, user_usernames
from app.utils.formatters import format_rubles


# Активные игры и служебные флаги
games: Dict[int, Dict[str, Any]] = {}
pending_bet_input: Dict[int, bool] = {}
next_game_id: int = 1


def build_games_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = []

    rows.append(
        [
            InlineKeyboardButton(text="✅Создать игру", callback_data="create_game"),
            InlineKeyboardButton(text="🔄Обновить", callback_data="refresh_games"),
        ]
    )

    active = [g for g in games.values() if g["opponent_id"] is None]
    active.sort(key=lambda x: x["id"], reverse=True)

    for g in active:
        txt = f"🎲Игра #{g['id']} | {format_rubles(g['bet'])} ₽"
        if g["creator_id"] == uid:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{txt} (Вы)", callback_data=f"game_my:{g['id']}"
                    )
                ]
            )
        else:
            rows.append(
                [InlineKeyboardButton(text=txt, callback_data=f"game_open:{g['id']}")]
            )

    rows.append(
        [
            InlineKeyboardButton(text="📋 Мои игры", callback_data="my_games:0"),
            InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating"),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games"),
            InlineKeyboardButton(text="🐼 Помощь", callback_data="help"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_games_text() -> str:
    return "Создайте игру или выберите уже имеющуюся:"


async def send_games_list(chat_id: int, uid: int):
    await bot.send_message(
        chat_id,
        build_games_text(),
        reply_markup=build_games_keyboard(uid),
    )


def calculate_profit(uid: int, g: Dict[str, Any]) -> int:
    bet = g["bet"]
    if g["winner"] == "draw":
        return 0
    creator = uid == g["creator_id"]
    if g["winner"] == "creator" and creator:
        return bet
    if g["winner"] == "opponent" and not creator:
        return bet
    return -bet


async def build_user_stats_and_history(uid: int):
    now = datetime.now(timezone.utc)
    finished = await get_user_games(uid)

    stats = {
        "month": {"games": 0, "profit": 0},
        "week": {"games": 0, "profit": 0},
        "day": {"games": 0, "profit": 0},
    }

    for g in finished:
        if not g.get("finished_at"):
            continue
        finished_at = datetime.fromisoformat(g["finished_at"])
        delta = now - finished_at
        p = calculate_profit(uid, g)

        if delta <= timedelta(days=30):
            stats["month"]["games"] += 1
            stats["month"]["profit"] += p
        if delta <= timedelta(days=7):
            stats["week"]["games"] += 1
            stats["week"]["profit"] += p
        if delta <= timedelta(days=1):
            stats["day"]["games"] += 1
            stats["day"]["profit"] += p

    def ps(v: int) -> str:
        return ("+" if v > 0 else "") + format_rubles(v)

    stats_text = (
        f"🎲 Кости за месяц: {stats['month']['games']}\n"
        f"└ 💸 Профит: {ps(stats['month']['profit'])} ₽\n\n"
        f"🎲 За неделю: {stats['week']['games']}\n"
        f"└ 💸 Профит: {ps(stats['week']['profit'])} ₽\n\n"
        f"🎲 За сутки: {stats['day']['games']}\n"
        f"└ 💸 Профит: {ps(stats['day']['profit'])} ₽"
    )

    history: List[Dict[str, Any]] = []
    for g in finished[:HISTORY_LIMIT]:
        if uid == g["creator_id"]:
            my = g["creator_roll"]
            opp = g["opponent_roll"]
        else:
            my = g["opponent_roll"]
            opp = g["creator_roll"]

        profit = calculate_profit(uid, g)
        if profit > 0:
            emoji, text = "🟩", "Победа"
        elif profit < 0:
            emoji, text = "🟥", "Проигрыш"
        else:
            emoji, text = "⚪", "Ничья"

        history.append(
            {"bet": g["bet"], "emoji": emoji, "text": text, "my": my, "opp": opp}
        )

    return stats_text, history


def build_history_keyboard(history: List[Dict[str, Any]], page: int) -> InlineKeyboardMarkup:
    rows = []

    total = len(history)
    if total == 0:
        rows.append(
            [InlineKeyboardButton(text="История пуста", callback_data="ignore")]
        )
        rows.append(
            [InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games")]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    pages = (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
    page = max(0, min(page, pages - 1))

    start = page * HISTORY_PAGE_SIZE
    end = start + HISTORY_PAGE_SIZE

    for h in history[start:end]:
        text = (
            f"{format_rubles(h['bet'])} ₽ | "
            f"{h['emoji']} {h['text']} | {h['my']}:{h['opp']}"
        )
        rows.append([InlineKeyboardButton(text=text, callback_data="ignore")])

    if pages > 1:
        rows.append(
            [
                InlineKeyboardButton(text="<<", callback_data="my_games:0"),
                InlineKeyboardButton(
                    text="<", callback_data=f"my_games:{max(0, page - 1)}"
                ),
                InlineKeyboardButton(
                    text=f"{page + 1}/{pages}", callback_data="ignore"
                ),
                InlineKeyboardButton(
                    text=">", callback_data=f"my_games:{min(pages - 1, page + 1)}"
                ),
                InlineKeyboardButton(
                    text=">>", callback_data=f"my_games:{pages - 1}"
                ),
            ]
        )

    rows.append([InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_rating_text(requesting_uid: int) -> str:
    now = datetime.now(timezone.utc)
    finished_games, all_uids = await get_users_profit_and_games_30_days()

    user_stats: Dict[int, Dict[str, int]] = {}

    for g in finished_games:
        finished_at = datetime.fromisoformat(g["finished_at"])
        if (now - finished_at) > timedelta(days=30):
            continue

        for uid in (g["creator_id"], g["opponent_id"]):
            if uid is None:
                continue
            stats = user_stats.setdefault(uid, {"profit": 0, "games": 0})
            stats["profit"] += calculate_profit(uid, g)
            stats["games"] += 1

    top_list = sorted(
        user_stats.items(),
        key=lambda x: (x[1]["profit"], -x[1]["games"]),
        reverse=True,
    )

    top_lines = []
    place_emoji = ["🥇", "🥈", "🥉"]

    for i, (uid, stats) in enumerate(top_list[:3]):
        profit = format_rubles(stats["profit"])
        games_count = format_rubles(stats["games"])
        username = user_usernames.get(uid) or f"ID{uid}"
        top_lines.append(
            f"{place_emoji[i]} {username} - {profit} ₽ за {games_count} игр"
        )

    if not top_lines:
        return "🏆 Рейтинг пока пуст — ещё нет завершённых игр за 30 дней."

    user_place = None
    total_players = len(top_list)
    user_profit = user_stats.get(requesting_uid, {"profit": 0, "games": 0})

    for i, (uid, stats) in enumerate(top_list):
        if uid == requesting_uid:
            user_place = i + 1
            break

    lines = ["🏆 ТОП 3 игроков в кости:\n"]
    lines.extend(top_lines)
    lines.append("\n")

    if user_place:
        profit = format_rubles(user_profit["profit"])
        games_count = format_rubles(user_profit["games"])
        sign = "+" if user_profit["profit"] >= 0 else ""
        lines.append(
            f"Ваше место в рейтинге: {user_place} из {total_players} "
            f"({sign}{profit} ₽ за {games_count} игр)"
        )
    else:
        games_count_total = await get_user_dice_games_count(requesting_uid)
        if games_count_total > 0:
            lines.append(
                "Ваше место в рейтинге: Нет данных за последние 30 дней."
            )
        else:
            lines.append(
                "Ваше место в рейтинге: Нет данных (нет завершённых игр)."
            )

    lines.append("\nДанные приведены за последние 30 дней.")

    return "\n".join(lines)


async def telegram_roll(uid: int) -> int:
    msg = await bot.send_dice(uid, emoji="🎲")
    # В оригинале было небольшое ожидание
    return msg.dice.value


async def play_game(gid: int):
    g = games.get(gid)
    if not g:
        return

    c = g["creator_id"]
    o = g["opponent_id"]
    bet = g["bet"]

    # 🎲 Перебрасываем, пока не будет победитель
    while True:
        cr = await telegram_roll(c)
        orr = await telegram_roll(o)

        # Ждём окончания анимации: в telegram_roll уже есть sleep(3)

        if cr != orr:
            break  # победитель найден → выходим из цикла

    g["creator_roll"] = cr
    g["opponent_roll"] = orr
    g["finished"] = True
    g["finished_at"] = datetime.now(timezone.utc)

    bank = bet * 2
    commission = bank // 100
    prize = bank - commission

    # 🏆 Победитель
    if cr > orr:
        winner = "creator"
        change_balance(c, prize)
    else:
        winner = "opponent"
        change_balance(o, prize)

    # Комиссия админу
    change_balance(MAIN_ADMIN_ID, commission)

    g["winner"] = winner

    # Сохраняем в БД
    await upsert_game(g)

    # Сообщения
    for user in (c, o):
        is_creator = (user == c)
        your = cr if is_creator else orr
        their = orr if is_creator else cr

        result_text = (
            "🥳 Поздравляем с победой!"
            if (winner == "creator" and is_creator)
            or (winner == "opponent" and not is_creator)
            else "😔 К сожалению, вы проиграли!"
        )

        bank_text = (
            f"💰 Банк: {format_rubles(bank)} ₽\n"
            f"💸 Комиссия: {format_rubles(commission)} ₽ (1%)"
        )

        txt = (
            f"🏁 Кости #{gid}\n"
            f"{bank_text}\n\n"
            f"🫵 Ваш результат: {your}\n"
            f"🎲 Результат соперника: {their}\n\n"
            f"{result_text}\n"
            f"💼 Баланс: {format_rubles(get_balance(user))} ₽"
        )

        await bot.send_message(user, txt)


