#handlers/main_btn_handle/common.py
from datetime import date

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from sql.db import async_session
from sql.models import Order, Services, Barbers

USER_ORDERS_PER_PAGE = 5
CANCEL_ORDERS_PER_PAGE = 1

def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _prepare_order_cards(orders):
    if not orders:
        return []

    service_ids = {_to_int(o.service_id) for o in orders}
    service_ids.discard(None)
    barber_ids = {_to_int(o.barber_id) for o in orders}
    barber_ids.discard(None)

    services_by_id = {}
    barbers_by_id = {}
    async with async_session() as session:
        if service_ids:
            result = await session.execute(select(Services).where(Services.id.in_(service_ids)))
            services_by_id = {s.id: s for s in result.scalars().all()}
        if barber_ids:
            result = await session.execute(select(Barbers).where(Barbers.id.in_(barber_ids)))
            barbers_by_id = {b.id: b for b in result.scalars().all()}

    order_cards = []
    for o in orders:
        service_id = _to_int(o.service_id)
        service_name = (
            services_by_id[service_id].name
            if service_id is not None and service_id in services_by_id
            else str(o.service_id)
        )

        barber_name = (getattr(o, "barber_id_name", "") or "").strip()
        if not barber_name:
            barber_id = _to_int(o.barber_id)
            if barber_id is not None and barber_id in barbers_by_id:
                barber = barbers_by_id[barber_id]
                barber_name = " ".join(
                    part for part in [barber.barber_first_name, barber.barber_last_name] if part
                ).strip()
                barber_name = barber_name or str(o.barber_id)
            else:
                barber_name = str(o.barber_id)

        date_text = o.date.strftime("%Y-%m-%d") if hasattr(o.date, "strftime") else str(o.date)
        time_text = o.time.strftime("%H:%M") if hasattr(o.time, "strftime") else str(o.time)

        order_cards.append(
            {
                "date": date_text,
                "time": time_text,
                "barber": barber_name,
                "service": service_name,
            }
        )

    return order_cards


async def _fetch_user_orders(user_id: int, only_today: bool = False):
    async with async_session() as session:
        query = select(Order).where(Order.user_id == user_id)
        if only_today:
            query = query.where(Order.booked_date == date.today())
        query = query.order_by(Order.booked_date.desc(), Order.booked_time.desc(), Order.id.desc())
        result = await session.execute(query)
        return result.scalars().all()


def get_user_orders_page(order_cards, page: int):
    """
    Foydalanuvchi buyurtmalarini sahifalab chiqarish
    """
    start = page * USER_ORDERS_PER_PAGE
    end = start + USER_ORDERS_PER_PAGE
    sliced = order_cards[start:end]

    text = "📋 *Sizning barcha buyurtmalaringiz:*\n\n"
    for idx, o in enumerate(sliced, start=start + 1):
        text += (
            f"📌 *Buyurtma {idx}*\n"
            f"📅 Sana: {o['date']}\n"
            f"⏰ Vaqt: {o['time']}\n"
            f"💈 Barber: {o['barber']}\n"
            f"✂️ Xizmat: {o['service']}\n\n"
        )

    # Tugmalar (pagination + qaytish)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"user_prev:{page-1}"))
    if end < len(order_cards):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"user_next:{page+1}"))

    nav_row = buttons if buttons else []
    back_row = [InlineKeyboardButton(text="📂 Bugungi buyurtmalarga qaytish", callback_data="back_to_today")]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, back_row] if nav_row else [back_row])
    return text, inline_kb


def _format_dt(value, fmt):
    return value.strftime(fmt) if hasattr(value, "strftime") else str(value)
