#admins/admin_buttons.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
            [KeyboardButton(text="💈 Servis qo'shish"), KeyboardButton(text="💈 Servisni o'chirish")], 
            [KeyboardButton(text="💈 Barber qo'shish"), KeyboardButton(text="💈 Barberni o'cirish")],
            [KeyboardButton(text="✉️ Mahsus xabar yuborish")],
            # [KeyboardButton(text="🔙 Ortga")]
        ],
        resize_keyboard=True    
    )


