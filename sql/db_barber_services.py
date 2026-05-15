import asyncio
import logging
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from sql.db import async_session
from sql.models import BarberServiceDiscounts, BarberServices, Barbers, Services
from utils.discounts import calculate_discounted_price, normalize_discount_percent
from utils.service_pricing import attach_service_discount_snapshot
from utils.validators import INT32_MAX

logger = logging.getLogger(__name__)

DISCOUNT_SCOPE_ALL = "all"
DISCOUNT_SCOPE_SINGLE = "single"
SERVICE_DISCOUNT_TIMEZONE = ZoneInfo("Asia/Tashkent")
DEFAULT_SERVICE_DISCOUNT_DURATION = timedelta(hours=24)
SERVICE_DISCOUNT_EXPIRY_CHECK_INTERVAL_SECONDS = 1.0
MAX_DURATION_MINUTES = 24 * 60


def normalize_money(value: object) -> int | None:
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized.isdigit():
            return None
        value = int(normalized)

    if not isinstance(value, int):
        return None

    if value < 0 or value > INT32_MAX:
        return None
    return value


def normalize_duration_minutes(value: object) -> int | None:
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized.isdigit():
            return None
        value = int(normalized)

    if not isinstance(value, int):
        return None

    if value <= 0 or value > MAX_DURATION_MINUTES:
        return None
    return value


def _normalize_id(value: object) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _get_discount_now() -> datetime:
    return datetime.now(SERVICE_DISCOUNT_TIMEZONE)


def _normalize_discount_scope(scope: str) -> str:
    normalized_scope = (scope or "").strip().lower()
    if normalized_scope == DISCOUNT_SCOPE_ALL:
        return DISCOUNT_SCOPE_ALL
    return DISCOUNT_SCOPE_SINGLE


def calculate_service_discount_expiry(
    start_at: datetime | None = None,
) -> tuple[date, time]:
    local_start_at = start_at or _get_discount_now()
    if local_start_at.tzinfo is None:
        local_start_at = local_start_at.replace(tzinfo=SERVICE_DISCOUNT_TIMEZONE)
    else:
        local_start_at = local_start_at.astimezone(SERVICE_DISCOUNT_TIMEZONE)

    expires_at = (local_start_at + DEFAULT_SERVICE_DISCOUNT_DURATION).replace(
        microsecond=0
    )
    return expires_at.date(), expires_at.time().replace(tzinfo=None)


def format_service_discount_expiry(end_at: date, end_time: time) -> str:
    return f"{end_at.strftime('%d.%m.%Y')} {end_time.strftime('%H:%M:%S')}"


def _build_expired_discount_condition(current_at: datetime | None = None):
    local_now = current_at or _get_discount_now()
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=SERVICE_DISCOUNT_TIMEZONE)
    else:
        local_now = local_now.astimezone(SERVICE_DISCOUNT_TIMEZONE)

    current_date = local_now.date()
    current_time = local_now.time().replace(tzinfo=None)
    return or_(
        BarberServiceDiscounts.end_at < current_date,
        and_(
            BarberServiceDiscounts.end_at == current_date,
            BarberServiceDiscounts.end_time <= current_time,
        ),
    )


async def _expire_service_discounts_in_session(session) -> int:
    result = await session.execute(
        delete(BarberServiceDiscounts).where(_build_expired_discount_condition())
    )
    return int(result.rowcount or 0)


async def _sync_expired_service_discounts(session, *, commit: bool) -> int:
    removed_count = await _expire_service_discounts_in_session(session)
    if commit and removed_count:
        await session.commit()
    return removed_count


async def clear_expired_service_discounts() -> int:
    async with async_session() as session:
        try:
            removed_count = await _expire_service_discounts_in_session(session)
            if removed_count:
                await session.commit()
            return removed_count
        except SQLAlchemyError:
            await session.rollback()
            raise


async def service_discount_expiry_worker(
    poll_interval: float = SERVICE_DISCOUNT_EXPIRY_CHECK_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            await clear_expired_service_discounts()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to clear expired barber-service discounts.")
        await asyncio.sleep(poll_interval)


async def _load_discount_map(
    session,
    barber_service_ids: Iterable[int],
) -> dict[int, BarberServiceDiscounts]:
    normalized_ids = sorted({int(item_id) for item_id in barber_service_ids})
    if not normalized_ids:
        return {}

    result = await session.execute(
        select(BarberServiceDiscounts).where(
            BarberServiceDiscounts.barber_service_id.in_(normalized_ids)
        )
    )
    return {
        int(discount.barber_service_id): discount
        for discount in result.scalars().all()
    }


def _apply_discount_snapshots(
    barber_services: Iterable[BarberServices],
    discount_map: Mapping[int, BarberServiceDiscounts],
) -> list[BarberServices]:
    items = list(barber_services)
    for item in items:
        discount = discount_map.get(int(item.id))
        attach_service_discount_snapshot(
            item,
            discount_percent=(discount.discount_percent if discount else None),
            discounted_price=(int(discount.discounted_price) if discount else None),
        )
    return items


async def attach_discounts_to_barber_services(
    barber_services: Iterable[BarberServices],
) -> list[BarberServices]:
    items = list(barber_services)
    if not items:
        return items

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        discount_map = await _load_discount_map(
            session,
            (int(item.id) for item in items),
        )
    return _apply_discount_snapshots(items, discount_map)


async def create_barber_service(
    barber_id: int,
    service_id: int,
    price: object,
    duration_minutes: object,
) -> BarberServices | None:
    normalized_barber_id = _normalize_id(barber_id)
    normalized_service_id = _normalize_id(service_id)
    normalized_price = normalize_money(price)
    normalized_duration = normalize_duration_minutes(duration_minutes)
    if (
        normalized_barber_id is None
        or normalized_service_id is None
        or normalized_price is None
        or normalized_duration is None
    ):
        return None

    async with async_session() as session:
        try:
            barber = await session.get(Barbers, normalized_barber_id)
            service = await session.get(Services, normalized_service_id)
            if barber is None or service is None:
                return None

            existing = await session.scalar(
                select(BarberServices.id).where(
                    BarberServices.barber_id == normalized_barber_id,
                    BarberServices.service_id == normalized_service_id,
                )
            )
            if existing is not None:
                return None

            item = BarberServices(
                barber_id=normalized_barber_id,
                service_id=normalized_service_id,
                price=normalized_price,
                duration_minutes=normalized_duration,
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            attach_service_discount_snapshot(
                item,
                discount_percent=None,
                discounted_price=None,
            )
            return item
        except IntegrityError:
            await session.rollback()
            return None
        except SQLAlchemyError:
            await session.rollback()
            raise


async def update_barber_service(
    barber_service_id: int,
    updates: dict[str, object],
) -> BarberServices | None:
    normalized_id = _normalize_id(barber_service_id)
    if normalized_id is None:
        return None

    async with async_session() as session:
        try:
            await _sync_expired_service_discounts(session, commit=False)
            item = await session.get(
                BarberServices,
                normalized_id,
                options=[selectinload(BarberServices.service), selectinload(BarberServices.barber)],
            )
            if item is None:
                return None

            discount_map = await _load_discount_map(session, [int(item.id)])
            current_discount = discount_map.get(int(item.id))

            clean_updates: dict[str, int] = {}
            if "price" in updates:
                price = normalize_money(updates.get("price"))
                if price is None:
                    return None
                clean_updates["price"] = price
            if "duration_minutes" in updates:
                duration = normalize_duration_minutes(updates.get("duration_minutes"))
                if duration is None:
                    return None
                clean_updates["duration_minutes"] = duration

            for key, value in clean_updates.items():
                setattr(item, key, value)

            if "price" in clean_updates and current_discount is not None:
                current_discount.discounted_price = calculate_discounted_price(
                    int(item.price),
                    current_discount.discount_percent,
                )

            await session.commit()
            await session.refresh(item)
            if current_discount is not None:
                await session.refresh(current_discount)
            attach_service_discount_snapshot(
                item,
                discount_percent=(current_discount.discount_percent if current_discount else None),
                discounted_price=(
                    int(current_discount.discounted_price)
                    if current_discount is not None
                    else None
                ),
            )
            return item
        except SQLAlchemyError:
            await session.rollback()
            raise


async def delete_barber_service(barber_service_id: int) -> bool:
    normalized_id = _normalize_id(barber_service_id)
    if normalized_id is None:
        return False

    async with async_session() as session:
        try:
            item = await session.get(BarberServices, normalized_id)
            if item is None:
                return False
            await session.delete(item)
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            raise


async def delete_barber_service_by_pair(barber_id: int, service_id: int) -> bool:
    item = await get_barber_service_by_pair(barber_id, service_id)
    if item is None:
        return False
    return await delete_barber_service(int(item.id))


async def get_barber_service_by_id(barber_service_id: int) -> BarberServices | None:
    normalized_id = _normalize_id(barber_service_id)
    if normalized_id is None:
        return None

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        item = await session.get(
            BarberServices,
            normalized_id,
            options=[selectinload(BarberServices.service), selectinload(BarberServices.barber)],
        )
        if item is None:
            return None
        discount_map = await _load_discount_map(session, [int(item.id)])
        return _apply_discount_snapshots([item], discount_map)[0]


async def get_barber_service_by_pair(
    barber_id: int | str,
    service_id: int | str,
) -> BarberServices | None:
    normalized_barber_id = _normalize_id(barber_id)
    normalized_service_id = _normalize_id(service_id)
    if normalized_barber_id is None or normalized_service_id is None:
        return None

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(BarberServices)
            .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
            .where(
                BarberServices.barber_id == normalized_barber_id,
                BarberServices.service_id == normalized_service_id,
            )
            .limit(1)
        )
        item = result.scalars().first()
        if item is None:
            return None
        discount_map = await _load_discount_map(session, [int(item.id)])
        return _apply_discount_snapshots([item], discount_map)[0]


async def barber_has_service(barber_id: int | str, service_id: int | str) -> bool:
    return await get_barber_service_by_pair(barber_id, service_id) is not None


async def get_barber_services(barber_id: int | str) -> list[BarberServices]:
    normalized_barber_id = _normalize_id(barber_id)
    if normalized_barber_id is None:
        return []

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(BarberServices)
            .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
            .where(BarberServices.barber_id == normalized_barber_id)
            .order_by(BarberServices.id.asc())
        )
        items = list(result.scalars().all())
        discount_map = await _load_discount_map(session, (int(item.id) for item in items))
        return _apply_discount_snapshots(items, discount_map)


async def list_barber_services_ordered() -> list[BarberServices]:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(BarberServices)
            .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
            .join(Services, Services.id == BarberServices.service_id)
            .join(Barbers, Barbers.id == BarberServices.barber_id)
            .order_by(Services.name.asc(), Barbers.barber_first_name.asc(), BarberServices.id.asc())
        )
        items = list(result.scalars().all())
        discount_map = await _load_discount_map(session, (int(item.id) for item in items))
        return _apply_discount_snapshots(items, discount_map)


async def get_barber_services_by_service(service_id: int | str) -> list[BarberServices]:
    normalized_service_id = _normalize_id(service_id)
    if normalized_service_id is None:
        return []

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(BarberServices)
            .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
            .join(Barbers, Barbers.id == BarberServices.barber_id)
            .where(
                BarberServices.service_id == normalized_service_id,
                or_(Barbers.is_paused.is_(False), Barbers.is_paused.is_(None)),
            )
            .order_by(Barbers.id.asc())
        )
        items = list(result.scalars().all())
        discount_map = await _load_discount_map(session, (int(item.id) for item in items))
        return _apply_discount_snapshots(items, discount_map)


async def get_barbers_by_service(service_id: int | str) -> list[Barbers]:
    items = await get_barber_services_by_service(service_id)
    return [item.barber for item in items if item.barber is not None]


async def get_barber_ids_by_service(service_id: int | str) -> list[int]:
    return [int(barber.id) for barber in await get_barbers_by_service(service_id)]


async def list_discounted_barber_services_ordered() -> list[BarberServices]:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(BarberServices)
            .options(selectinload(BarberServices.service), selectinload(BarberServices.barber))
            .join(
                BarberServiceDiscounts,
                BarberServiceDiscounts.barber_service_id == BarberServices.id,
            )
            .join(Services, Services.id == BarberServices.service_id)
            .join(Barbers, Barbers.id == BarberServices.barber_id)
            .order_by(Services.name.asc(), Barbers.barber_first_name.asc(), BarberServices.id.asc())
        )
        items = list(result.scalars().all())
        discount_map = await _load_discount_map(session, (int(item.id) for item in items))
        return _apply_discount_snapshots(items, discount_map)


async def has_global_discount_on_all_services() -> bool:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        total_items = await session.scalar(select(func.count(BarberServices.id)))
        total_items = int(total_items or 0)
        if total_items <= 0:
            return False

        total_discounts = await session.scalar(select(func.count(BarberServiceDiscounts.id)))
        total_discounts = int(total_discounts or 0)
        if total_discounts != total_items:
            return False

        non_global_count = await session.scalar(
            select(func.count(BarberServiceDiscounts.id)).where(
                BarberServiceDiscounts.applied_scope != DISCOUNT_SCOPE_ALL
            )
        )
        return int(non_global_count or 0) == 0


async def set_barber_service_discount(
    barber_service_id: int,
    discount_percent: object,
    *,
    applied_scope: str = DISCOUNT_SCOPE_SINGLE,
    end_at: date | None = None,
    end_time: time | None = None,
) -> BarberServices | None:
    normalized_id = _normalize_id(barber_service_id)
    if normalized_id is None:
        return None

    percent = normalize_discount_percent(discount_percent)
    normalized_scope = _normalize_discount_scope(applied_scope)
    if end_at is None or end_time is None:
        end_at, end_time = calculate_service_discount_expiry()

    async with async_session() as session:
        try:
            await _sync_expired_service_discounts(session, commit=False)
            item = await session.get(
                BarberServices,
                normalized_id,
                options=[selectinload(BarberServices.service), selectinload(BarberServices.barber)],
            )
            if item is None:
                return None

            discount_map = await _load_discount_map(session, [int(item.id)])
            discount = discount_map.get(int(item.id))
            discounted_price = calculate_discounted_price(int(item.price), percent)

            if discount is None:
                discount = BarberServiceDiscounts(
                    barber_service_id=int(item.id),
                    discount_percent=percent,
                    discounted_price=discounted_price,
                    applied_scope=normalized_scope,
                    end_at=end_at,
                    end_time=end_time,
                )
                session.add(discount)
            else:
                discount.discount_percent = percent
                discount.discounted_price = discounted_price
                discount.applied_scope = normalized_scope
                discount.end_at = end_at
                discount.end_time = end_time

            await session.commit()
            await session.refresh(item)
            await session.refresh(discount)
            attach_service_discount_snapshot(
                item,
                discount_percent=discount.discount_percent,
                discounted_price=int(discount.discounted_price),
            )
            return item
        except SQLAlchemyError:
            await session.rollback()
            raise


async def bulk_set_barber_service_discount(
    barber_service_ids: Iterable[int],
    discount_percent: object,
    *,
    applied_scope: str = DISCOUNT_SCOPE_ALL,
    end_at: date | None = None,
    end_time: time | None = None,
) -> int:
    normalized_ids = sorted(
        item_id for item_id in (_normalize_id(value) for value in barber_service_ids) if item_id
    )
    if not normalized_ids:
        return 0

    percent = normalize_discount_percent(discount_percent)
    normalized_scope = _normalize_discount_scope(applied_scope)
    if end_at is None or end_time is None:
        end_at, end_time = calculate_service_discount_expiry()

    async with async_session() as session:
        try:
            await _sync_expired_service_discounts(session, commit=False)
            result = await session.execute(
                select(BarberServices)
                .where(BarberServices.id.in_(normalized_ids))
                .order_by(BarberServices.id.asc())
            )
            items = list(result.scalars().all())
            discount_map = await _load_discount_map(session, (int(item.id) for item in items))

            for item in items:
                discounted_price = calculate_discounted_price(int(item.price), percent)
                discount = discount_map.get(int(item.id))
                if discount is None:
                    session.add(
                        BarberServiceDiscounts(
                            barber_service_id=int(item.id),
                            discount_percent=percent,
                            discounted_price=discounted_price,
                            applied_scope=normalized_scope,
                            end_at=end_at,
                            end_time=end_time,
                        )
                    )
                else:
                    discount.discount_percent = percent
                    discount.discounted_price = discounted_price
                    discount.applied_scope = normalized_scope
                    discount.end_at = end_at
                    discount.end_time = end_time

            await session.commit()
            return len(items)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def clear_barber_service_discount(barber_service_id: int) -> bool:
    normalized_id = _normalize_id(barber_service_id)
    if normalized_id is None:
        return False

    async with async_session() as session:
        try:
            result = await session.execute(
                delete(BarberServiceDiscounts).where(
                    BarberServiceDiscounts.barber_service_id == normalized_id
                )
            )
            await session.commit()
            return bool(result.rowcount)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def clear_all_service_discounts() -> int:
    async with async_session() as session:
        try:
            result = await session.execute(delete(BarberServiceDiscounts))
            await session.commit()
            return int(result.rowcount or 0)
        except SQLAlchemyError:
            await session.rollback()
            raise
