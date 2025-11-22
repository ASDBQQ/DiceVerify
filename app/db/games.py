from typing import Dict, Any, List, Optional, Tuple

async def upsert_game(g: Dict[str, Any]):
    """Создать/обновить игру в таблице games."""
    if not pool:
        return
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO games (
                id, creator_id, opponent_id, bet,
                creator_roll, opponent_roll, winner,
                finished, created_at, finished_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT(id) DO UPDATE SET
                creator_id=EXCLUDED.creator_id,
                opponent_id=EXCLUDED.opponent_id,
                bet=EXCLUDED.bet,
                creator_roll=EXCLUDED.creator_roll,
                opponent_roll=EXCLUDED.opponent_roll,
                winner=EXCLUDED.winner,
                finished=EXCLUDED.finished,
                created_at=EXCLUDED.created_at,
                finished_at=EXCLUDED.finished_at
        """,
            g["id"],                # ← ДОБАВЛЕНО
            g["creator_id"],
            g["opponent_id"],
            g["bet"],
            g.get("creator_roll"),
            g.get("opponent_roll"),
            g.get("winner"),
            int(g.get("finished", False)),
            g["created_at"].isoformat() if g.get("created_at") else None,
            g["finished_at"].isoformat() if g.get("finished_at") else None,
        )


async def get_user_games(uid: int) -> List[Dict[str, Any]]:
    """Получить завершённые игры пользователя (для истории/статистики)."""
    if not pool:
        return []
    async with pool.acquire() as db:
        records = await db.fetch(
            """
            SELECT * FROM games
            WHERE (creator_id = $1 OR opponent_id = $1) AND finished = 1
            ORDER BY finished_at DESC
        """,
            uid,
        )
        return [dict(r) for r in records]


async def get_all_finished_games() -> List[Dict[str, Any]]:
    """Получить все завершённые игры (используется редко)."""
    if not pool:
        return []
    async with pool.acquire() as db:
        records = await db.fetch("SELECT * FROM games WHERE finished = 1")
        return [dict(r) for r in records]


async def get_user_dice_games_count(uid: int, finished_only: bool = True) -> int:
    """Количество игр пользователя в кости."""
    if not pool:
        return 0
    async with pool.acquire() as db:
        query = """
            SELECT COUNT(*) FROM games
            WHERE (creator_id = $1 OR opponent_id = $1)
        """
        params = [uid]
        if finished_only:
            query += " AND finished = 1"

        count = await db.fetchval(query, *params)
        return count if count is not None else 0


async def get_users_profit_and_games_30_days() -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Используется для рейтинга:
    - возвращает список игр за последние 30 дней
    - и список всех user_id из таблицы users.
    """
    if not pool:
        return [], []

    now = datetime.now(timezone.utc)
    delta_30_days = now - timedelta(days=30)

    async with pool.acquire() as db:
        # Игры за 30 дней
        finished_games_records = await db.fetch(
            "SELECT * FROM games WHERE finished = 1 AND finished_at >= $1",
            delta_30_days.isoformat(),
        )
        finished_games = [dict(r) for r in finished_games_records]

        # Все пользователи
        all_uids_records = await db.fetch("SELECT user_id FROM users")
        all_uids = [row["user_id"] for row in all_uids_records]

    return finished_games, all_uids



