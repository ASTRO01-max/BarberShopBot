#keyboards/booking_keyboards.py
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sqlalchemy.future import select
from sqlalchemy import or_
from sql.db import async_session
from sql.models import Services, Barbers
from utils.emoji_map import SERVICE_EMOJIS
from sql.db_order_utils import get_booked_times

def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")]
        ]
    )

# Haftaning kunlari nomlari (uzbekcha)
WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# Oy nomlari (uzbekcha)
MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"
]

async def service_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    try:
        async with async_session() as session:
            result = await session.execute(select(Services))
            services = result.scalars().all()

        if not services:
            builder.button(text="❌ Xizmatlar mavjud emas", callback_data="no_services")
        else:
            for s in services:
                emoji = SERVICE_EMOJIS.get(s.name, "🔹")
                builder.button(
                    text=f"{emoji} {s.name}",   # ✅ emoji textda
                    callback_data=f"service_{s.name}"  # ✅ callback_data faqat matn
                )

        builder.adjust(1)
        return builder.as_markup()

    except Exception:
        builder.button(text="⚠️ Ma'lumot yuklashda xatolik", callback_data="error_services")
        builder.adjust(1)
        return builder.as_markup()


def _default_time_slots():
    return [f"{h:02d}:00" for h in range(9, 18)]


def _build_time_slots(work_time: dict):
    if not isinstance(work_time, dict):
        return _default_time_slots()

    start = work_time.get("from")
    end = work_time.get("to")
    if not (isinstance(start, str) and isinstance(end, str)):
        return _default_time_slots()

    try:
        start_dt = datetime.strptime(start, "%H:%M")
        end_dt = datetime.strptime(end, "%H:%M")
    except ValueError:
        return _default_time_slots()

    if start_dt >= end_dt:
        return _default_time_slots()

    slots = []
    current = start_dt
    while current < end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(hours=1)
    return slots or _default_time_slots()


async def barber_keyboard(service_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Barbers).where(
                    or_(Barbers.is_paused.is_(False), Barbers.is_paused.is_(None))
                )
            )
            barbers = result.scalars().all()

        if not barbers:
            builder.button(text="❌ Sartaroshlar mavjud emas", callback_data="no_barbers")
        else:
            for b in barbers:
                builder.button(
                    text=f"{b.barber_first_name} {b.barber_last_name or ''}",
                    callback_data=f"barber_{service_id}_{b.id}"   # ← Siz xohlagan format
                )

        builder.adjust(1)
        return builder.as_markup()

    except Exception:
        builder.button(text="⚠️ Ma'lumot yuklashda xatolik", callback_data="error_barbers")
        builder.adjust(1)
        return builder.as_markup()


async def date_keyboard(service_id: str, barber_id: str) -> InlineKeyboardMarkup:
    from sql.db_order_utils import get_booked_times

    now = datetime.now()
    builder = InlineKeyboardBuilder()

    async with async_session() as session:
        barber = None
        try:
            barber = await session.get(Barbers, int(barber_id))
        except (TypeError, ValueError):
            barber = None

    if barber and barber.is_paused:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="ў?? Boў??sh sana yoў??q", callback_data="no_dates")]
            ]
        )

    all_times = _build_time_slots(getattr(barber, "work_time", None))

    for i in range(7):
        current_day = now + timedelta(days=i)
        date_str = current_day.strftime("%Y-%m-%d")

        booked = await get_booked_times(barber_id, date_str)
        available = [t for t in all_times if t not in booked]

        # ❌ AGAR VAQT YO‘Q → SANANI HAM CHIQARMAYMIZ
        if not available:
            continue

        day = current_day.day
        month = MONTHS[current_day.month - 1]
        weekday = WEEKDAYS[current_day.weekday()]
        text = f"{day}-{month} {weekday}"

        builder.button(
            text=text,
            callback_data=f"date_{service_id}_{barber_id}_{date_str}"
        )

    if not builder.buttons:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Bo‘sh sana yo‘q", callback_data="no_dates")]
            ]
        )

    builder.adjust(1)
    return builder.as_markup()


async def time_keyboard(service_id: str, barber_id: str, date: str) -> InlineKeyboardMarkup:
    async with async_session() as session:
        barber = None
        try:
            barber = await session.get(Barbers, int(barber_id))
        except (TypeError, ValueError):
            barber = None

    if barber and barber.is_paused:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ў?? Bo'sh vaqtlar yo'q", callback_data="no_times")]
        ])

    all_times = _build_time_slots(getattr(barber, "work_time", None))

    from sql.db_order_utils import get_booked_times
    booked = await get_booked_times(barber_id, date)
    available = [t for t in all_times if t not in booked]

    if not available:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bo'sh vaqtlar yo'q", callback_data="no_times")]
        ])

    markup = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for i, t in enumerate(available, start=1):
        row.append(
            InlineKeyboardButton(
                text=t,
                callback_data=f"confirm_{service_id}_{barber_id}_{date}_{t}"
            )
        )
        if i % 2 == 0:
            markup.inline_keyboard.append(row)
            row = []
    if row:
        markup.inline_keyboard.append(row)

    return markup
