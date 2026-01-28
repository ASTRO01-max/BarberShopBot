# admins/admin_buttons.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

markup = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
        [KeyboardButton(text="💈 Servis qo'shish"), KeyboardButton(text="💈 Servisni o'chirish")],
        [KeyboardButton(text="💈 Barber qo'shish"), KeyboardButton(text="💈 Barberni o'cirish")],
        [KeyboardButton(text="ℹ️ Kontakt/Info kiritish"), KeyboardButton(text="✏️ Kontakt/Info tahrirlash")],
        [KeyboardButton(text="✉️ Mahsus xabar yuborish")],
    ],
    resize_keyboard=True
)
