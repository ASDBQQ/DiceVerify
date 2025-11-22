# app/services/games.py
import asyncio
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

    # 🔧 ТУТ ГЛАВНОЕ: помощь теперь только по костям
    rows.append(
        [
            InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games"),
            InlineKeyboardButton(text="🐼 Помощь", callback_data="help_dice"),
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
    if g["winner"] == "creator" and not creator:
        return -bet
    if g["winner"] == "opponent" and creator:
        return -bet
    return 0


async def build_user_stats_and_history(
    uid: int,
) -> tuple[str, List[Dict[str, Any]]]:
    finished = await get_user_games(uid)
    finished = finished[:HISTORY_LIMIT]

    stats = {
        "month": {"games": 0, "profit": 0},
        "week": {"games": 0, "profit": 0},
        "day": {"games": 0, "profit": 0},
    }

    now = datetime.now(timezone.utc)

    for g in finished:
        finished_at = g["finished_at"]
        if not finished_at:
            continue
        if isinstance(finished_at, str):
            finished_at = datetime.fromisoformat(finished_at)
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)

        diff = now - finished_at
        profit = calculate_profit(uid, g)

        if diff <= timedelta(days=30):
            stats["month"]["games"] += 1
            stats["month"]["profit"] += profit
        if diff <= timedelta(days=7):
            stats["week"]["games"] += 1
            stats["week"]["profit"] += profit
        if diff <= timedelta(days=1):
            stats["day"]["games"] += 1
            stats["day"]["profit"] += profit

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
        creator = g["creator_id"] == uid
        opp_id = g["opponent_id"] if creator else g["creator_id"]
        opp_name = user_usernames.get(opp_id, f"ID{opp_id}")
        bet = g["bet"]
        res = g["winner"]

        if res == "draw":
            emoji = "🤝"
            text = f"Ничья с {opp_name} ({format_rubles(bet)} ₽)"
        elif (res == "creator" and creator) or (res == "opponent" and not creator):
            emoji = "✅"
            text = f"Победа над {opp_name} (+{format_rubles(bet)} ₽)"
        else:
            emoji = "❌"
            text = f"Поражение от {opp_name} (-{format_rubles(bet)} ₽)"

        my = g["creator_roll"] if creator else g["opponent_roll"]
        opp = g["opponent_roll"] if creator else g["creator_roll"]

        history.append(
            {"bet": bet, "emoji": emoji, "text": text, "my": my, "opp": opp}
        )

    return stats_text, history


def build_history_keyboard(
    history: List[Dict[str, Any]], page: int
) -> InlineKeyboardMarkup:
    rows = []

    total = len(history)
    if total == 0:
        rows.append([InlineKeyboardButton(text="История пуста", callback_data="ignore")])
        rows.append([InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    pages = (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
    page = max(0, min(page, pages - 1))

    start = page * HISTORY_PAGE_SIZE
    end = start + HISTORY_PAGE_SIZE

    for h in history[start:end]:
        text = (
            f"{format_rubles(h['bet'])} ₽ | "
            f"{h['emoji']} | "
            f"Вы: {h['my']} | "
            f"Соперник: {h['opp']}"
        )
        rows.append([InlineKeyboardButton(text=text, callback_data="ignore")])

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"my_games:{page - 1}")
        )
    if page < pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"my_games:{page + 1}")
        )
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_rating_text(requesting_uid: int) -> str:
    stats = await get_users_profit_and_games_30_days()
    if not stats:
        return "🏆 Рейтинг пока пуст — за последние 30 дней не было завершённых игр."

    sorted_stats = sorted(
        stats.items(), key=lambda x: (x[1]["profit"], -x[1]["games"]), reverse=True
    )

    lines = ["🏆 ТОП-3 игроков в кости за последние 30 дней:\n"]
    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, s) in enumerate(sorted_stats[:3]):
        username = user_usernames.get(uid) or f"ID{uid}"
        profit = s["profit"]
        games_count = s["games"]
        sign = "+" if profit > 0 else ""
        lines.append(
            f"{medals[i]} {username} — {sign}{format_rubles(profit)} ₽ за {games_count} игр"
        )

    # найти место запрашивающего игрока
    user_place = None
    total_players = len(sorted_stats)
    user_profit = stats.get(requesting_uid, {"profit": 0, "games": 0})

    for i, (uid, _) in enumerate(sorted_stats):
        if uid == requesting_uid:
            user_place = i + 1
            break

    lines.append("\n")

    if user_place:
        profit = format_rubles(user_profit["profit"])
        games_count = user_profit["games"]
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
    # Если захочешь — можно добавить задержку здесь
    # await asyncio.sleep(3)
    return msg.dice.value


async def play_game(gid: int):
    """
    Логика игры в кости:
    - бросок кубика каждому
    - при ничьей — переброс
    - результат показывается ПОСЛЕ окончания анимации
    """
    g = games.get(gid)
    if not g:
        return

    c = g["creator_id"]
    o = g["opponent_id"]
    bet = g["bet"]

    # 🎲 Перебрасываем, пока не будет победитель
    while True:
        # броски выполняются параллельно
        creator_roll_msg = await bot.send_dice(c, emoji="🎲")
        opponent_roll_msg = await bot.send_dice(o, emoji="🎲")

        # Значения кубиков
        cr = creator_roll_msg.dice.value
        orr = opponent_roll_msg.dice.value

        # ❗ Ждём окончания анимации кубика (примерно 3 секунды)
        await asyncio.sleep(3)

        if cr != orr:
            break  # победитель найден — выходим из цикла
        # иначе — ничья, перебрасываем

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

    # Отправляем уведомления игрокам
    for user in (c, o):
        is_creator = user == c
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






