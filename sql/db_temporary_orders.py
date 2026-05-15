from datetime import date, datetime, time
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from .db import async_session
from .models import (
    BarberServiceDiscounts,
    BarberServices,
    Barbers,
    Order,
    Services,
    TemporaryOrder,
)


logger = logging.getLogger(__name__)

REQUIRED_TEMPORARY_ORDER_FIELDS = (
    "fullname",
    "phonenumber",
    "date",
    "time",
)


class TemporaryOrderError(Exception):
    """Base exception for temporary order finalization errors."""


class TemporaryOrderNotFoundError(TemporaryOrderError):
    """Raised when a booking confirmation has no temporary order to finalize."""


class TemporaryOrderIncompleteError(TemporaryOrderError):
    def __init__(self, missing_fields: list[str]):
        self.missing_fields = tuple(missing_fields)
        super().__init__(
            "temporary order is incomplete: " + ", ".join(sorted(missing_fields))
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


def _barber_full_name(barber: Barbers | None, fallback: str = "") -> str:
    if barber is None:
        return fallback
    first_name = (barber.barber_first_name or "").strip()
    last_name = (barber.barber_last_name or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or fallback or str(barber.id)


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

    return _barber_full_name(barber, str(barber_id_raw)) if barber else str(barber_id_raw)


async def _resolve_barber_service(
    session,
    *,
    barber_service_id: int | str | None = None,
    service_id: int | str | None = None,
    barber_id: int | str | None = None,
) -> BarberServices | None:
    if barber_service_id:
        try:
            return await session.get(
                BarberServices,
                int(barber_service_id),
                options=[selectinload(BarberServices.service), selectinload(BarberServices.barber)],
            )
        except (TypeError, ValueError):
            return None

    if not service_id or not barber_id:
        return None

    try:
        normalized_service_id = int(service_id)
        normalized_barber_id = int(barber_id)
    except (TypeError, ValueError):
        return None

    result = await session.execute(
        select(BarberServices)
        .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
        .where(
            BarberServices.service_id == normalized_service_id,
            BarberServices.barber_id == normalized_barber_id,
        )
        .limit(1)
    )
    return result.scalars().first()


async def _current_price(session, barber_service: BarberServices) -> int:
    discount = await session.scalar(
        select(BarberServiceDiscounts.discounted_price).where(
            BarberServiceDiscounts.barber_service_id == int(barber_service.id)
        )
    )
    return int(discount if discount is not None else barber_service.price)


async def _apply_barber_service_snapshot(
    session,
    order: TemporaryOrder,
    barber_service: BarberServices,
) -> None:
    order.barber_service_id = int(barber_service.id)
    order.service_id = str(barber_service.service_id)
    order.barber_id = str(barber_service.barber_id)
    order.service_name = (
        barber_service.service.name
        if barber_service.service is not None
        else await _resolve_service_name(session, str(barber_service.service_id))
    )
    order.barber_name = _barber_full_name(
        barber_service.barber,
        await _resolve_barber_name(session, str(barber_service.barber_id)) or "",
    )
    order.booked_price = await _current_price(session, barber_service)
    order.booked_duration_minutes = int(barber_service.duration_minutes)


def get_missing_temporary_order_fields(order: TemporaryOrder | None) -> list[str]:
    if order is None:
        return [*REQUIRED_TEMPORARY_ORDER_FIELDS, "barber_service_id"]

    missing = [
        field
        for field in REQUIRED_TEMPORARY_ORDER_FIELDS
        if not getattr(order, field, None)
    ]

    has_barber_service = bool(getattr(order, "barber_service_id", None))
    has_legacy_pair = bool(getattr(order, "service_id", None)) and bool(
        getattr(order, "barber_id", None)
    )
    if not has_barber_service and not has_legacy_pair:
        missing.append("barber_service_id")
    return missing


def is_temporary_order_complete(order: TemporaryOrder | None) -> bool:
    return not get_missing_temporary_order_fields(order)


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

            for key in ("fullname", "phonenumber", "service_id", "barber_id"):
                if key in data:
                    setattr(order, key, data.get(key))

            for key in ("service_name", "barber_name", "booked_price", "booked_duration_minutes"):
                if key in data:
                    setattr(order, key, data.get(key))

            if "barber_service_id" in data:
                order.barber_service_id = data.get("barber_service_id")

            if "service_id" in data and data.get("service_id") is None:
                order.service_name = None
                order.barber_service_id = None
                order.booked_price = None
                order.booked_duration_minutes = None
            if "barber_id" in data and data.get("barber_id") is None:
                order.barber_name = None
                order.barber_service_id = None
                order.booked_price = None
                order.booked_duration_minutes = None

            barber_service = await _resolve_barber_service(
                session,
                barber_service_id=order.barber_service_id,
                service_id=order.service_id,
                barber_id=order.barber_id,
            )
            if barber_service is not None:
                await _apply_barber_service_snapshot(session, order, barber_service)
            else:
                if order.service_id and not order.service_name:
                    order.service_name = await _resolve_service_name(session, order.service_id)
                if order.barber_id and not order.barber_name:
                    order.barber_name = await _resolve_barber_name(session, order.barber_id)

            if "date" in data:
                order.date = _parse_date(data.get("date"))
            if "time" in data:
                order.time = _parse_time(data.get("time"))

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
        commit_failed = False
        try:
            logger.info("Finalizing temporary order for user_id=%s", normalized_user_id)
            result = await session.execute(
                select(TemporaryOrder)
                .where(TemporaryOrder.user_id == normalized_user_id)
                .order_by(TemporaryOrder.id.desc())
                .with_for_update()
            )
            temp_order = result.scalars().first()
            if temp_order is None:
                logger.error(
                    "Temporary order not found during finalization for user_id=%s",
                    normalized_user_id,
                )
                raise TemporaryOrderNotFoundError("temporary order not found")

            missing_fields = get_missing_temporary_order_fields(temp_order)
            if missing_fields:
                logger.error(
                    "Temporary order validation failed for user_id=%s. Missing fields: %s",
                    normalized_user_id,
                    ", ".join(sorted(missing_fields)),
                )
                raise TemporaryOrderIncompleteError(missing_fields)

            barber_service = await _resolve_barber_service(
                session,
                barber_service_id=temp_order.barber_service_id,
                service_id=temp_order.service_id,
                barber_id=temp_order.barber_id,
            )
            if barber_service is None:
                raise TemporaryOrderIncompleteError(["barber_service_id"])

            await _apply_barber_service_snapshot(session, temp_order, barber_service)

            now = datetime.now()
            new_order = Order(
                user_id=normalized_user_id,
                fullname=temp_order.fullname,
                phonenumber=temp_order.phonenumber,
                barber_service_id=int(barber_service.id),
                barber_id=int(barber_service.barber_id),
                service_name=temp_order.service_name or str(barber_service.service_id),
                barber_name=temp_order.barber_name or str(barber_service.barber_id),
                booked_price=int(temp_order.booked_price or barber_service.price),
                booked_duration_minutes=int(
                    temp_order.booked_duration_minutes or barber_service.duration_minutes
                ),
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

            try:
                await session.commit()
            except Exception:
                commit_failed = True
                await session.rollback()
                logger.exception(
                    "DB commit failed while finalizing temporary order for user_id=%s",
                    normalized_user_id,
                )
                raise

            logger.info(
                "Temporary order finalized for user_id=%s order_id=%s",
                normalized_user_id,
                new_order.id,
            )
            return new_order
        except Exception:
            if not commit_failed:
                await session.rollback()
                logger.exception(
                    "finalize_temporary_order failed for user_id=%s",
                    normalized_user_id,
                )
            raise
