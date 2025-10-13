from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Services, Barbers
from utils.emoji_map import SERVICE_EMOJIS


def back_button() -> InlineKeyboardMarkup:
    """Orqaga qaytish tugmasi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")]
        ]
    )


async def service_keyboard() -> InlineKeyboardMarkup:
    """
    Xizmatlar ro‘yxatini bazadan olib, inline button shaklida qaytaradi.
    """
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


async def barber_keyboard(service_id: str) -> InlineKeyboardMarkup:
    """
    Sartaroshlar ro‘yxatini bazadan olib, tanlangan xizmat uchun inline buttonlar yaratadi.
    """
    builder = InlineKeyboardBuilder()
    try:
        async with async_session() as session:
            result = await session.execute(select(Barbers))
            barbers = result.scalars().all()

        if not barbers:
            builder.button(text="❌ Sartaroshlar mavjud emas", callback_data="no_barbers")
        else:
            for b in barbers:
                builder.button(
                    text=b.barber_fullname,
                    callback_data=f"barber_{service_id}_{b.barber_fullname}"  # ⚠️ id o‘rniga nom ishlatildi
                )

        builder.adjust(1)
        return builder.as_markup()

    except Exception:
        builder.button(text="⚠️ Ma'lumot yuklashda xatolik", callback_data="error_barbers")
        builder.adjust(1)
        return builder.as_markup()


def date_keyboard(service_id: str, barber_id: str) -> InlineKeyboardMarkup:
    """
    Keyingi 3 kunlik sana tanlash uchun tugmalar.
    """
    now = datetime.now()
    builder = InlineKeyboardBuilder()
    for i in range(3):
        day = (now.date() + timedelta(days=i)).strftime("%Y-%m-%d")
        builder.button(text=day, callback_data=f"date_{service_id}_{barber_id}_{day}")
    builder.adjust(1)
    return builder.as_markup()


async def time_keyboard(service_id: str, barber_id: str, date: str) -> InlineKeyboardMarkup:
    """
    Tanlangan sana bo‘yicha mavjud vaqtlar tugmalari.
    """
    all_times = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

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
