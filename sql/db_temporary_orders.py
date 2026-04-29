from datetime import date, datetime, time
import logging

from sqlalchemy import delete, select

from .db import async_session
from .models import Barbers, Order, Services, TemporaryOrder


logger = logging.getLogger(__name__)

REQUIRED_TEMPORARY_ORDER_FIELDS = (
    "fullname",
    "phonenumber",
    "service_id",
    "barber_id",
    "date",
    "time",
)


def _parse_date(value):
    if value is None:
        return None
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
        return None
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


async def _resolve_service_name(session, service_id_raw: str | None) -> str | None:
    if not service_id_raw:
        return None

    service = None
    try:
        if str(service_id_raw).isdigit():
            service = await session.get(Services, int(str(service_id_raw)))
    except (TypeError, ValueError):
        service = None

    if service is None:
        result = await session.execute(select(Services).where(Services.name == str(service_id_raw)))
        service = result.scalars().first()

    return service.name if service else str(service_id_raw)


async def _resolve_barber_name(session, barber_id_raw: str | None) -> str | None:
    if not barber_id_raw:
        return None

    barber = None
    try:
        if str(barber_id_raw).isdigit():
            barber = await session.get(Barbers, int(str(barber_id_raw)))
    except (TypeError, ValueError):
        barber = None

    if not barber:
        return str(barber_id_raw)

    first_name = (barber.barber_first_name or "").strip()
    last_name = (barber.barber_last_name or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or str(barber_id_raw)


def is_temporary_order_complete(order: TemporaryOrder | None) -> bool:
    if order is None:
        return False
    return all(getattr(order, field, None) for field in REQUIRED_TEMPORARY_ORDER_FIELDS)


async def get_temporary_order(user_id: int) -> TemporaryOrder | None:
    try:
        normalized_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    async with async_session() as session:
        result = await session.execute(
            select(TemporaryOrder)
            .where(TemporaryOrder.user_id == normalized_user_id)
            .order_by(TemporaryOrder.id.desc())
        )
        return result.scalars().first()


async def upsert_temporary_order(data: dict) -> TemporaryOrder:
    raw_user_id = data.get("user_id")
    if raw_user_id is None:
        raise ValueError("user_id is required")

    user_id = int(raw_user_id)
    now = datetime.now()

    async with async_session() as session:
        try:
            result = await session.execute(
                select(TemporaryOrder)
                .where(TemporaryOrder.user_id == user_id)
                .order_by(TemporaryOrder.id.desc())
            )
            order = result.scalars().first()
            if order is None:
                order = TemporaryOrder(user_id=user_id)
                session.add(order)

            if "is_for_other" in data:
                order.is_for_other = bool(data.get("is_for_other"))
            elif order.is_for_other is None:
                order.is_for_other = False

            if "current_state" in data:
                order.current_state = data.get("current_state")

            if "selected_barber_locked" in data:
                order.selected_barber_locked = bool(data.get("selected_barber_locked"))
            elif order.selected_barber_locked is None:
                order.selected_barber_locked = False

            for key in ("fullname", "phonenumber", "service_id", "service_name", "barber_id", "barber_id_name"):
                if key in data:
                    setattr(order, key, data.get(key))

            if "service_id" in data and data.get("service_id") is None:
                order.service_name = None
            if "barber_id" in data and data.get("barber_id") is None:
                order.barber_id_name = None

            if "date" in data:
                order.date = _parse_date(data.get("date"))
            if "time" in data:
                order.time = _parse_time(data.get("time"))

            if order.service_id and not order.service_name:
                order.service_name = await _resolve_service_name(session, order.service_id)
            if order.barber_id and not order.barber_id_name:
                order.barber_id_name = await _resolve_barber_name(session, order.barber_id)

            if "booked_date" in data:
                order.booked_date = _parse_date(data.get("booked_date"))
            else:
                order.booked_date = now.date()

            if "booked_time" in data:
                order.booked_time = _parse_time(data.get("booked_time"))
            else:
                order.booked_time = now.time()

            await session.commit()
            await session.refresh(order)
            return order
        except Exception:
            await session.rollback()
            logger.exception("upsert_temporary_order failed")
            raise


async def delete_temporary_order(user_id: int) -> bool:
    try:
        normalized_user_id = int(user_id)
    except (TypeError, ValueError):
        return False

    async with async_session() as session:
        try:
            result = await session.execute(
                delete(TemporaryOrder)
                .where(TemporaryOrder.user_id == normalized_user_id)
                .returning(TemporaryOrder.id)
            )
            deleted_row = result.first()
            await session.commit()
            return bool(deleted_row)
        except Exception:
            await session.rollback()
            logger.exception("delete_temporary_order failed")
            raise


async def finalize_temporary_order(user_id: int) -> Order:
    try:
        normalized_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id is required") from exc

    async with async_session() as session:
        try:
            result = await session.execute(
                select(TemporaryOrder)
                .where(TemporaryOrder.user_id == normalized_user_id)
                .order_by(TemporaryOrder.id.desc())
            )
            temp_order = result.scalars().first()
            if temp_order is None:
                raise ValueError("temporary order not found")

            missing_fields = [
                field
                for field in REQUIRED_TEMPORARY_ORDER_FIELDS
                if not getattr(temp_order, field, None)
            ]
            if missing_fields:
                raise ValueError(
                    "temporary order is incomplete: " + ", ".join(sorted(missing_fields))
                )

            service_name = temp_order.service_name or await _resolve_service_name(
                session,
                temp_order.service_id,
            )
            barber_name = temp_order.barber_id_name or await _resolve_barber_name(
                session,
                temp_order.barber_id,
            )

            now = datetime.now()
            new_order = Order(
                user_id=normalized_user_id,
                fullname=temp_order.fullname,
                phonenumber=temp_order.phonenumber,
                service_id=temp_order.service_id,
                service_name=service_name or str(temp_order.service_id),
                barber_id=temp_order.barber_id,
                barber_id_name=barber_name or str(temp_order.barber_id),
                date=temp_order.date,
                time=temp_order.time,
                booked_date=now.date(),
                booked_time=now.time(),
            )
            session.add(new_order)
            await session.flush()

            await session.execute(
                delete(TemporaryOrder).where(TemporaryOrder.user_id == normalized_user_id)
            )

            await session.commit()
            await session.refresh(new_order)
            return new_order
        except Exception:
            await session.rollback()
            logger.exception("finalize_temporary_order failed")
            raise
