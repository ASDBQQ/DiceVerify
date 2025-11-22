# app/utils/keyboards.py
from aiogram import types


def bottom_menu() -> types.ReplyKeyboardMarkup:
    """Главное меню, которое всегда под сообщениями."""
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="🕹 Игры"),
                types.KeyboardButton(text="💼 Баланс"),
            ],
            [
                types.KeyboardButton(text="🎁 Розыгрыш"),
                types.KeyboardButton(text="👤 Профиль"),
            ],
            [types.KeyboardButton(text="🌐 Поддержка")],
        ],
        resize_keyboard=True,
    )
