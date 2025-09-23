from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database.users_utils import get_user   # foydalanuvchi tekshirish uchun

# Asosiy menu tugmalari
cancel_order_btn = KeyboardButton(text="❌Buyurtmani bekor qilish")
order_history_btn = KeyboardButton(text="🗂Buyurtmalar tarixi")

# keyboard = ReplyKeyboardMarkup(
#     keyboard=[
#         [cancel_order_btn],
#         [order_history_btn],
#     ],
#     resize_keyboard=True
# )

phone_request_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

def get_dynamic_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    Foydalanuvchining mavjudligiga qarab tugmalarni qaytaradi:
    - Agar foydalanuvchi yo‘q → '📥 Foydalanuvchini saqlash'
    - Agar foydalanuvchi mavjud → '📥 Foydalanuvchi ma'lumotlarini o‘zgartirish'
    """
    user = get_user(user_id)

    # Asosiy tugmalar
    buttons = [
        [cancel_order_btn],
        [order_history_btn],
    ]

    # Dinamik tugma qo‘shamiz
    if user:
        buttons.append([KeyboardButton(text="📥Foydalanuvchi ma'lumotlarini o'zgartirish")])
    else:
        buttons.append([KeyboardButton(text="📥Foydalanuvchini saqlash")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)