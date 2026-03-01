# admins/admin_buttons.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

ADMIN_MENU_TEXT = "👨‍💻 Admin"
ADMIN_ADD_TEXT = "➕ Admin qo'shish"
ADMIN_DEL_TEXT = "➖ Admin o'chirish"
ADMIN_ADD_CB = "admin:add"
ADMIN_DEL_CB = "admin:del"
ADMIN_CANCEL_TEXT = "❌ Bekor qilish"
ADMIN_CANCEL_CB = "admin:cancel"

SERVICE_MENU_TEXT = "💈 Servis"
SERVICE_ADD_TEXT = "➕ Servis qo'shish"
SERVICE_DEL_TEXT = "➖ Servis o'chirish"
SERVICE_ADD_CB = "service:add"
SERVICE_DEL_CB = "service:del"

BARBER_MENU_TEXT = "💈 Barber"
BARBER_ADD_TEXT = "➕ Barber qo'shish"
BARBER_DEL_TEXT = "➖ Barber o'chirish"
BARBER_ADD_CB = "barber:add"
BARBER_DEL_CB = "barber:del"

INFO_MENU_TEXT = "ℹ️ Info"
INFO_ADD_TEXT = "ℹ️ Info kiritish"
INFO_EDIT_TEXT = "✏️ Info tahrirlash"
INFO_ADD_CB = "info:add"
INFO_EDIT_CB = "info:edit"


def get_admin_inline_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ADMIN_ADD_TEXT, callback_data=ADMIN_ADD_CB)],
            [InlineKeyboardButton(text=ADMIN_DEL_TEXT, callback_data=ADMIN_DEL_CB)],
        ]
    )


def get_admin_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ADMIN_CANCEL_TEXT, callback_data=ADMIN_CANCEL_CB)],
        ]
    )


def get_service_inline_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=SERVICE_ADD_TEXT, callback_data=SERVICE_ADD_CB)],
            [InlineKeyboardButton(text=SERVICE_DEL_TEXT, callback_data=SERVICE_DEL_CB)],
        ]
    )


def get_barber_inline_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BARBER_ADD_TEXT, callback_data=BARBER_ADD_CB)],
            [InlineKeyboardButton(text=BARBER_DEL_TEXT, callback_data=BARBER_DEL_CB)],
        ]
    )


def get_info_inline_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=INFO_ADD_TEXT, callback_data=INFO_ADD_CB)],
            [InlineKeyboardButton(text=INFO_EDIT_TEXT, callback_data=INFO_EDIT_CB)],
        ]
    )


markup = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
        [KeyboardButton(text=SERVICE_MENU_TEXT), KeyboardButton(text=BARBER_MENU_TEXT)],
        [KeyboardButton(text=INFO_MENU_TEXT), KeyboardButton(text=ADMIN_MENU_TEXT)],
        [KeyboardButton(text="✉️ Mahsus xabar yuborish")],
    ],
    resize_keyboard=True
)
