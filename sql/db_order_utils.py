# sql/db_order_utils.py
from datetime import datetime, date, time
import logging

from sqlalchemy.future import select
from sqlalchemy import delete
from .db import async_session
from .models import Order

logger = logging.getLogger(__name__)

def _parse_date(value):
    """String yoki date -> date obyektiga aylantiradi. Raise ValueError agar noto'g'ri bo'lsa."""
    if value is None:
        raise ValueError("date is required")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Unable to parse date from: {value!r}")

def _parse_time(value):
    """String yoki time -> time obyektiga aylantiradi. Raise ValueError agar noto'g'ri bo'lsa."""
    if value is None:
        raise ValueError("time is required")
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    raise ValueError(f"Unable to parse time from: {value!r}")

async def save_order(order: dict):
    """
    order expected keys:
      - user_id (int or str-able)
      - fullname
      - phonenumber
      - service_id
      - barber_id
      - date (YYYY-MM-DD or datetime.date)
      - time (HH:MM or datetime.time)
    Returns created Order ORM instance.
    """
    async with async_session() as session:
        try:
            # --- Normalizatsiya ---
            raw_uid = order.get("user_id")
            if raw_uid is None:
                raise ValueError("user_id is required")
            user_id = int(raw_uid)

            fullname = order.get("fullname") or "Noma'lum"
            phonenumber = order.get("phonenumber") or order.get("phone") or "Noma'lum"
            service_id = order.get("service_id") or order.get("service")
            barber_id = order.get("barber_id") or order.get("barber")

            date_val = _parse_date(order.get("date"))
            time_val = _parse_time(order.get("time"))

            # ---- Yaratish ----
            now = datetime.now()
            new_order = Order(
                user_id=user_id,
                fullname=fullname,
                phonenumber=phonenumber,
                service_id=service_id,
                barber_id=barber_id,
                date=date_val,
                time=time_val,
                booked_date=now.date(),
                booked_time=now.time(),
            )
            session.add(new_order)
            await session.commit()
            await session.refresh(new_order)
            return new_order

        except Exception as exc:
            await session.rollback()
            logger.exception("save_order failed: %s", exc)
            # Reraising: caller may handle it (telegram handler should catch and reply to user)
            raise


# Qo'shimcha util funksiyalar (keltirilgan siz ishlatgan shaklga mos)
async def load_orders():
    async with async_session() as session:
        result = await session.execute(select(Order))
        return result.scalars().all()


async def get_booked_times(barber_id: str, date_str: str):
    """
    Berilgan barber va sanaga band qilingan vaqtlarni qaytaradi
    """
    try:
        # string → datetime.date
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"❌ Noto‘g‘ri sana formati: {date_str}, kerak: DD-MM-YYYY")

    async with async_session() as session:
        result = await session.execute(
            select(Order.time).where(
                Order.barber_id == barber_id,
                Order.date == date_obj   # endi DATE bilan solishtiriladi
            )
        )
        times = result.scalars().all()
        print(times)
        return [t.strftime("%H:%M") for t in times]


async def delete_last_order_by_user(user_id: int, order_date: date = None):
    """
    Foydalanuvchining eng so‘nggi (yoki bugungi) buyurtmasini o‘chiradi.
    """
    async with async_session() as session:
        query = select(Order).where(Order.user_id == user_id)
        if order_date:
            query = query.where(Order.date == order_date)

        query = query.order_by(Order.id.desc())
        result = await session.execute(query)
        order = result.scalars().first()

        if not order:
            return None

        await session.delete(order)
        await session.commit()
        return order
