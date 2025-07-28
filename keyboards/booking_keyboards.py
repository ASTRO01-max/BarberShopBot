from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from database.order_utils import get_booked_times

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

def time_keyboard(service_id: str, barber_id: str, date: str):
    builder = InlineKeyboardBuilder()
    all_times = ["10:00", "11:00", "13:00", "15:00", "17:00"]

    booked = get_booked_times(service_id, barber_id, date)
    available = [t for t in all_times if t not in booked]

    if not available:
        return None  # Hech qanday tugma yo‘q

    for time in available:
        builder.button(
            text=time,
            callback_data=f"confirm_{service_id}_{barber_id}_{date}_{time}"
        )
    builder.adjust(2)
    return builder.as_markup()
