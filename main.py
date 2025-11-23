import asyncio

from app.bot import bot, dp
from app.db.pool import init_db

# Просто импортируем файлы — хендлеры сами регистрируются через dp
import app.handlers.start
import app.handlers.games_menu
import app.handlers.balance
import app.handlers.admin
import app.handlers.profile
import app.handlers.text

async def main():
    await init_db()
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())




