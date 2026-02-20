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

cancel_order_btn = KeyboardButton(text="❌ Buyurtmani bekor qilish")
order_history_btn = KeyboardButton(text="🗂 Buyurtmalar tarixi")
user_database_btn = KeyboardButton(text="📥 Foydalanuvchi ma'lumotlari")


async def get_dynamic_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    user = await get_user(user_id)

    # Agar foydalanuvchi bazada mavjud bo‘lmasa — tugmalar chiqmaydi
    if not user:
        return ReplyKeyboardMarkup(
            keyboard=[],
            resize_keyboard=True
        )

    # Agar mavjud bo‘lsa — barcha tugmalar chiqadi
    buttons = [
        [cancel_order_btn],
        [order_history_btn],
        [user_database_btn],
    ]

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )

