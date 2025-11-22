# app/services/ton.py
import asyncio
import re
from datetime import datetime, timezone
from typing import Dict, Set

import aiohttp

from app.config import (
    TON_WALLET_ADDRESS,
    TONAPI_RATES_URL,
    TON_RUB_CACHE_TTL,
    MAIN_ADMIN_ID,
)
from app.db.deposits import add_ton_deposit
# change_balance и get_balance теперь awaitable
from app.services.balances import change_balance, get_balance 
from app.utils.formatters import format_rubles
from app.bot import bot
from app.db.pool import redis_pool # <-- НОВОЕ


# Кэш курса TON→RUB
_ton_rate_cache: Dict[str, float | datetime] = {
    "value": 0.0,
    "updated": datetime.fromtimestamp(0, tz=timezone.utc),
}

# processed_ton_tx: Set[str] = set() # <-- УДАЛЕНО: теперь в Redis


async def get_ton_rub_rate() -> float:
    """Возвращает кэшированный курс TON → RUB."""
    # [EXISTING CODE: Логика получения курса остается прежней]
    now = datetime.now(timezone.utc)
    cached_value = _ton_rate_cache["value"]
    updated: datetime = _ton_rate_cache["updated"]  # type: ignore

    if cached_value and (now - updated).total_seconds() < TON_RUB_CACHE_TTL:
        return float(cached_value)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TONAPI_RATES_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    rate = data["rates"]["TON"]["prices"]["RUB"]
                    _ton_rate_cache["value"] = rate
                    _ton_rate_cache["updated"] = now
                    return float(rate)
    except Exception as e:
        print(f"Ошибка получения курса TON: {e}")
        return float(cached_value)

    return float(cached_value)


async def ton_deposit_worker():
    """Фоновый воркер для проверки TON-пополнений."""
    while True:
        try:
            # TODO: Реализовать получение последних транзакций с TON_WALLET_ADDRESS
            transactions = []
            
            # ВРЕМЕННЫЙ КОД:
            # if not transactions:
            #     print("Воркер TON: Нет новых транзакций (заглушка).")
            #     await asyncio.sleep(5)
            #     continue
            # КОНЕЦ ВРЕМЕННОГО КОДА

            for tx_data in transactions:
                # ... (Парсинг данных)
                comment = tx_data.get("comment", "")
                match = re.search(r"ID(\d+)", comment)
                if not match:
                    continue
                
                user_id = int(match.group(1))
                ton_amount = tx_data["amount"] / (10**9) # Пример: конвертация из nanoTON
                tx_hash = tx_data["hash"]

                # Проверка, была ли транзакция уже обработана (через Redis SET)
                if await redis_pool.sismember("processed_ton_tx", tx_hash): # <-- ИЗМЕНЕНИЕ
                    continue

                rate = await get_ton_rub_rate()
                coins = int(ton_amount * rate)

                if coins <= 0:
                    # Отмечаем как обработанную, чтобы не проверять снова
                    await redis_pool.sadd("processed_ton_tx", tx_hash) # <-- ИЗМЕНЕНИЕ
                    continue

                # Зачисление ₽
                await change_balance(user_id, coins) # change_balance теперь ASYNC

                # Отмечаем как обработанную
                await redis_pool.sadd("processed_ton_tx", tx_hash) # <-- ИЗМЕНЕНИЕ

                # Запись в БД
                await add_ton_deposit(tx_hash, user_id, ton_amount, coins, comment)

                # Уведомления
                try:
                    await bot.send_message(
                        user_id,
                        "💎 <b>Пополнение через TON успешно!</b>\\n\\n"
                        f"Получено: {ton_amount:.4f} TON\\n"
                        f"Курс: 1 TON ≈ {rate:.2f} ₽\\n"
                        f"Зачислено: {format_rubles(coins)} ₽\\n"
                        f"Текущий баланс: {format_rubles(await get_balance(user_id))} ₽", # <-- ИЗМЕНЕНИЕ
                    )
                except:
                    pass

                try:
                    await bot.send_message(
                        MAIN_ADMIN_ID,
                        "💎 <b>Новое пополнение TON</b>\\n"
                        f"User ID: {user_id}\\n"
                        f"Комментарий: {comment}\\n"
                        f"TON: {ton_amount:.4f}\\n"
                        f"₽: {format_rubles(coins)}",
                    )
                except:
                    pass

        except Exception as e:
            print(f"Ошибка в TON-воркере: {e}")

        await asyncio.sleep(5)

