#keyboards/main_menu.py
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu():
    builder = InlineKeyboardBuilder()
    buttons = [
        ("🗓️ Navbat olish", "book"),
        ("💈 Xizmatlar", "services"),
        ("💈 Barberlar", "barbers"),
        ("📞 Bog'lanish", "contact")
    ]
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    builder.adjust(1)
    return builder.as_markup()
