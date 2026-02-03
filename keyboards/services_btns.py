from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Pagination tugmalari
def services_nav_keyboard(index: int, total: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"services_prev_{index}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"services_next_{index}")
            ],
            [
                InlineKeyboardButton(text="🗓️ Navbat olish", callback_data="book")
            ],
            [
                InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")
            ],
        ]
    )
