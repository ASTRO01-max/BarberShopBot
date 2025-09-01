from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
            [KeyboardButton(text="💈 Servis qo'shish"), KeyboardButton(text="👨‍🎤 Barber qo'shish")],
            [KeyboardButton(text="✉️ Mahsus xabar yuborish"), KeyboardButton(text="🗂 CRN tizimi")],
            [KeyboardButton(text="🔙 Ortga")]
        ],
        resize_keyboard=True
    )


