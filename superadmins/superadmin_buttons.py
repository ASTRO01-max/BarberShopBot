#superadmins/superadmin_buttons.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_barber_menu(hide_pause: bool = False):
    """Barber asosiy menyusi"""
    second_row = []
    if not hide_pause:
        second_row.append(KeyboardButton(text="⛔ Bugun ishlamayman"))
    second_row.append(KeyboardButton(text="📢 Maxsus xabar"))

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 O'z statistikam"),
                KeyboardButton(text="🗓 Ish jadvalim"),
            ],
            second_row,
            [
                KeyboardButton(text="📅 Bugungi buyurtmalar"),
            ],
        ],
        resize_keyboard=True,
    )


def get_schedule_keyboard():
    """Ish jadvali sozlamalari"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ Ish vaqtini o'zgartirish",
                    callback_data="barber_change_time",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Ish kunlarini o'zgartirish",
                    callback_data="barber_change_days",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏸️ Tanaffus vaqtini o'zgartirish",
                    callback_data="barber_change_break"
                )
            ],
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="barber_menu"),
            ],
        ]
    )


def get_pause_confirm_keyboard():
    """Bugungi ishni to'xtatish tasdiqlash"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, to'xtataman", callback_data="barber_pause_confirm")
            ],
            [
                InlineKeyboardButton(text="❌ Yo'q, bekor qilish", callback_data="barber_menu")
            ],
        ]
    )

def get_pause_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Tugatish", callback_data="barber_pause_close")
            ],
        ]
    )


def get_order_actions_keyboard(order_id: int, client_tg_id: int = None, phone: str = None):
    """Buyurtma bilan ishlash tugmalari"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔔 Eslatma yuborish",
                callback_data=f"barber_notify_{order_id}",
            )
        ]
    ]

    contact_row = []
    if phone:
        contact_row.append(
            InlineKeyboardButton(text="📞 Qo'ng'iroq", url=f"tel:{phone}")
        )
    if client_tg_id:
        contact_row.append(
            InlineKeyboardButton(text="💬 Chat", url=f"tg://user?id={client_tg_id}")
        )

    if contact_row:
        buttons.append(contact_row)

    buttons.append(
        [InlineKeyboardButton(text="✅ Yakunlash", callback_data=f"barber_complete_{order_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)
