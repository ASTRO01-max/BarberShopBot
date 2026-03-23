# superadmins/superadmin_buttons.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_todays_orders_keyboard(order_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text="🔔 Bildirishnoma yuborish",
                callback_data=f"todays_notify_{order_id}"
            )
        ]
    ]

    nav_row = []
    if total_pages > 1:
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"todays_orders_page_{page - 1}"
                )
            )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text="Keyingi ➡️",
                    callback_data=f"todays_orders_page_{page + 1}"
                )
            )

    if nav_row:
        inline_keyboard.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


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
                KeyboardButton(text="➕ Xizmatlarimni kiritish")
            ],
        ],
        resize_keyboard=True,
    )


def get_barber_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Profil", callback_data="barber_profile_open")]
        ]
    )


def get_barber_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Rasmni o'zgartirish",
                    callback_data="barber_profile_edit_photo",
                ),
                InlineKeyboardButton(
                    text="✏️ Ma'lumotni o'zgartirish",
                    callback_data="barber_profile_edit_info",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Panelga qaytish", callback_data="barber_menu")],
        ]
    )


def get_barber_profile_fields_keyboard(hidden_fields: set[str] | None = None) -> InlineKeyboardMarkup:
    hidden = hidden_fields or set()

    def label(emoji: str, text: str, hidden_key: str | None = None) -> str:
        if hidden_key and hidden_key in hidden:
            return f"🙈 {text}"
        return f"{emoji} {text}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Ism familiya", callback_data="barber_profile_field_name")],
            [
                InlineKeyboardButton(
                    text=label("💼", "Tajriba", "experience"),
                    callback_data="barber_profile_field_experience",
                ),
                InlineKeyboardButton(
                    text=label("📞", "Aloqa", "phone"),
                    callback_data="barber_profile_field_phone",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label("📅", "Ish kunlari", "work_days"),
                    callback_data="barber_profile_field_work_days",
                ),
                InlineKeyboardButton(
                    text=label("⏰", "Ish vaqti", "work_time"),
                    callback_data="barber_profile_field_work_time",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label("⏸️", "Tanaffus", "breakdown"),
                    callback_data="barber_profile_field_breakdown",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Profilga qaytish", callback_data="barber_profile_open")],
        ]
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
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="barber_pause_confirm"),
                InlineKeyboardButton(text="✖️ Bekor qilish", callback_data="barber_pause_cancel"),
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

def get_back_statistics_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Statistikaga qaytish",
                    callback_data="back_statistics"
                )
            ]
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


def get_add_service_keyboard(services, selected_service_ids: list[int] | None = None) -> InlineKeyboardMarkup:
    selected = {int(sid) for sid in (selected_service_ids or [])}
    inline_keyboard = []

    for service in services:
        service_id = int(service.id)
        prefix = "✅ " if service_id in selected else ""
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{service.name}",
                    callback_data=f"barber_add_service_{service_id}",
                )
            ]
        )

    inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="barber_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

