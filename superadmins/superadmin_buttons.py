from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_barber_menu():
    """Barber asosiy menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 O'z statistikam"),
                KeyboardButton(text="🗓 Ish jadvalim"),
            ],
            [
                KeyboardButton(text="⛔ Bugun ishlamayman"),
                KeyboardButton(text="✉️ Maxsus xabar"),
            ],
            [
                KeyboardButton(text="📋 Bugungi buyurtmalar"),
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
