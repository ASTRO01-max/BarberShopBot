# keyboards/main_menu.py
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu():
    builder = InlineKeyboardBuilder()
    buttons = [
        ("🗓️ Navbat", "book"),
        ("💈 Xizmatlar", "services"),
        ("💈 Barberlar", "barbers"),
        ("ℹ️ Ma'lumotlar", "contact")
    ]
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()
