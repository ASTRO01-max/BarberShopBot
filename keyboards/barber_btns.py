from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# from keyboards.barber_btns import barber_nav_keyboard

# Pagination tugmalari
def barber_nav_keyboard(index: int, total: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"barber_prev_{index}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"barber_next_{index}")
            ],
            [
                InlineKeyboardButton(text="🗓️ Navbat olish", callback_data="book")
            ],
            [
                InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")
            ],
        ]
    )

