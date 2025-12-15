#keyboards/main_buttons.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sql.db_users_utils import get_user

phone_request_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

cancel_order_btn = KeyboardButton(text="❌Buyurtmani bekor qilish")
order_history_btn = KeyboardButton(text="🗂Buyurtmalar tarixi")

async def get_dynamic_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    user = await get_user(user_id)

    buttons = [
        [cancel_order_btn],
        [order_history_btn],
    ]

    if user:
        buttons.append([
            KeyboardButton(text="📥Foydalanuvchi ma'lumotlarini o'zgartirish"),
            KeyboardButton(text="❌ Foydalanuvchi ma'lumotlarini o‘chirish")
        ])
    else:
        buttons.append([KeyboardButton(text="📥Foydalanuvchini saqlash")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
