# sql/db_order_utils.py
from datetime import date, datetime, time
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from .db import async_session
from .models import BarberServiceDiscounts, BarberServices, Order

logger = logging.getLogger(__name__)


def _parse_date(value):
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


def _barber_name(barber) -> str:
    if barber is None:
        return "Noma'lum barber"
    full_name = " ".join(
        part for part in [barber.barber_first_name, barber.barber_last_name] if part
    ).strip()
    return full_name or str(barber.id)


async def _resolve_barber_service(session, order: dict) -> BarberServices | None:
    barber_service_id = order.get("barber_service_id")
    if barber_service_id:
        try:
            return await session.get(
                BarberServices,
                int(barber_service_id),
                options=[selectinload(BarberServices.service), selectinload(BarberServices.barber)],
            )
        except (TypeError, ValueError):
            return None

    service_id = order.get("service_id") or order.get("service")
    barber_id = order.get("barber_id") or order.get("barber")
    if not service_id or not barber_id:
        return None

    try:
        service_id_int = int(service_id)
        barber_id_int = int(barber_id)
    except (TypeError, ValueError):
        return None

    result = await session.execute(
        select(BarberServices)
        .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
        .where(
            BarberServices.service_id == service_id_int,
            BarberServices.barber_id == barber_id_int,
        )
        .limit(1)
    )
    return result.scalars().first()


async def _current_price(session, barber_service: BarberServices) -> int:
    discounted_price = await session.scalar(
        select(BarberServiceDiscounts.discounted_price).where(
            BarberServiceDiscounts.barber_service_id == int(barber_service.id)
        )
    )
    return int(discounted_price if discounted_price is not None else barber_service.price)


async def save_order(order: dict):
    async with async_session() as session:
        try:
            raw_uid = order.get("user_id")
            if raw_uid is None:
                raise ValueError("user_id is required")
            user_id = int(raw_uid)

            barber_service = await _resolve_barber_service(session, order)
            if barber_service is None:
                raise ValueError("barber_service_id or valid service_id/barber_id is required")

            fullname = order.get("fullname") or "Noma'lum"
            phonenumber = order.get("phonenumber") or order.get("phone") or "Noma'lum"
            date_val = _parse_date(order.get("date"))
            time_val = _parse_time(order.get("time"))

            now = datetime.now()
            new_order = Order(
                user_id=user_id,
                fullname=fullname,
                phonenumber=phonenumber,
                barber_service_id=int(barber_service.id),
                barber_id=int(barber_service.barber_id),
                service_name=(
                    order.get("service_name")
                    or (barber_service.service.name if barber_service.service else str(barber_service.service_id))
                ),
                barber_name=(
                    order.get("barber_name")
                    or order.get("barber_id_name")
                    or _barber_name(barber_service.barber)
                ),
                booked_price=int(order.get("booked_price") or await _current_price(session, barber_service)),
                booked_duration_minutes=int(
                    order.get("booked_duration_minutes") or barber_service.duration_minutes
                ),
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
            raise


async def load_orders():
    async with async_session() as session:
        result = await session.execute(select(Order))
        return result.scalars().all()


async def get_booked_times(barber_id: str | int, date_str: str):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"❌ Noto'g'ri sana formati: {date_str}, kerak: YYYY-MM-DD")

    async with async_session() as session:
        result = await session.execute(
            select(Order.time).where(
                Order.barber_id == int(barber_id),
                Order.date == date_obj,
            )
        )
        times = result.scalars().all()
        return [t.strftime("%H:%M") for t in times]


async def delete_last_order_by_user(user_id: int, order_date: date = None):
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
