#keyboards/start_btns.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

start_button = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Boshlash", callback_data="start_bot")
        ]
    ]
)
