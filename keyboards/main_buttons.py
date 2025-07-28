from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

cancel_order_btn = KeyboardButton(text="❌Buyurtmani bekor qilish")
order_history_btn = KeyboardButton(text="🗂Buyurtmalar tarixi")

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [cancel_order_btn],
        [order_history_btn]
    ],
    resize_keyboard=True
)
