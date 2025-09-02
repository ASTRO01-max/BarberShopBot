from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Asosiy keyboard
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

phone_request_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True  # yuborilgach, avtomatik yopiladi
)
