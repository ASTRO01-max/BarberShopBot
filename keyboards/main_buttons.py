from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

cancel_order_btn = KeyboardButton(text="❌Buyurtmani bekor qilish")
order_history_btn = KeyboardButton(text="🗂Buyurtmalar tarixi")
user = KeyboardButton(text="Foydalanuvchini saqlash")

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [cancel_order_btn],
        [order_history_btn],
        [user]
    ],
    resize_keyboard=True
)
