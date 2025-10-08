from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sql.db_order_utils import get_booked_times

from database.static_data import services, barbers

def back_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")]
        ]
    )

def service_keyboard():
    builder = InlineKeyboardBuilder()
    for key, (name, _, _) in services.items():
        builder.button(text=name, callback_data=f"service_{key}")
    builder.adjust(1)
    return builder.as_markup()

def barber_keyboard(service_id):
    builder = InlineKeyboardBuilder()
    for b in barbers:
        builder.button(text=b['name'], callback_data=f"barber_{service_id}_{b['id']}")
    builder.adjust(1)
    return builder.as_markup()

def date_keyboard(service_id, barber_id):
    now = datetime.now()
    builder = InlineKeyboardBuilder()
    for i in range(3):
        day = (now.date() + timedelta(days=i)).strftime("%Y-%m-%d")
        builder.button(text=day, callback_data=f"date_{service_id}_{barber_id}_{day}")
    builder.adjust(1)
    return builder.as_markup()

async def time_keyboard(service_id: str, barber_id: str, date: str) -> InlineKeyboardMarkup:
    all_times = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

    from sql.db_order_utils import get_booked_times
    booked = await get_booked_times(barber_id, date)

    available = [t for t in all_times if t not in booked]

    if not available:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bo'sh vaqtlar yo'q", callback_data="no_times")]
        ])

    # Aiogram 3.x uchun to‘g‘ri usul
    markup = InlineKeyboardMarkup(inline_keyboard=[])

    row = []
    for i, t in enumerate(available, start=1):
        row.append(
            InlineKeyboardButton(
                text=t,
                callback_data=f"confirm_{service_id}_{barber_id}_{date}_{t}"
            )
        )
        if i % 2 == 0:  # har 2ta tugmadan keyin yangi qatordan
            markup.inline_keyboard.append(row)
            row = []

    if row:
        markup.inline_keyboard.append(row)

    return markup