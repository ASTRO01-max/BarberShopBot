import asyncio
import logging
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import ServiceDiscounts, Services
from utils.discounts import calculate_discounted_price, normalize_discount_percent
from utils.service_pricing import attach_service_discount_snapshot
from utils.validators import INT32_MAX

DISCOUNT_SCOPE_ALL = "all"
DISCOUNT_SCOPE_SINGLE = "single"
SERVICE_DISCOUNT_TIMEZONE = ZoneInfo("Asia/Tashkent")
DEFAULT_SERVICE_DISCOUNT_DURATION = timedelta(hours=24)
SERVICE_DISCOUNT_EXPIRY_CHECK_INTERVAL_SECONDS = 1.0

logger = logging.getLogger(__name__)


def _get_discount_now() -> datetime:
    return datetime.now(SERVICE_DISCOUNT_TIMEZONE)


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
        ServiceDiscounts.end_at < current_date,
        and_(
            ServiceDiscounts.end_at == current_date,
            ServiceDiscounts.end_time <= current_time,
        ),
    )


async def _expire_service_discounts_in_session(session) -> int:
    result = await session.execute(
        delete(ServiceDiscounts).where(_build_expired_discount_condition())
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
            logger.exception("Failed to clear expired service discounts.")
        await asyncio.sleep(poll_interval)


def normalize_service_price(value: object) -> int | None:
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


def _normalize_discount_scope(scope: str) -> str:
    normalized_scope = (scope or "").strip().lower()
    if normalized_scope == DISCOUNT_SCOPE_ALL:
        return DISCOUNT_SCOPE_ALL
    return DISCOUNT_SCOPE_SINGLE


async def create_service(data: dict) -> Services | None:
    async with async_session() as session:
        try:
            if "price" in data:
                price = normalize_service_price(data.get("price"))
                if price is None:
                    return None
                data = dict(data)
                data["price"] = price

            new_service = Services(**data)
            session.add(new_service)
            await session.commit()
            await session.refresh(new_service)
            attach_service_discount_snapshot(
                new_service,
                discount_percent=None,
                discounted_price=None,
            )
            return new_service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def _load_discount_map(
    session,
    service_ids: Iterable[int],
) -> dict[int, ServiceDiscounts]:
    normalized_ids = sorted({int(service_id) for service_id in service_ids})
    if not normalized_ids:
        return {}

    result = await session.execute(
        select(ServiceDiscounts).where(ServiceDiscounts.service_id.in_(normalized_ids))
    )
    return {
        int(discount.service_id): discount
        for discount in result.scalars().all()
    }


def _apply_service_discount_snapshots(
    services: Iterable[Services],
    discount_map: Mapping[int, ServiceDiscounts],
) -> list[Services]:
    service_list = list(services)
    for service in service_list:
        discount = discount_map.get(int(service.id))
        attach_service_discount_snapshot(
            service,
            discount_percent=(discount.discount_percent if discount else None),
            discounted_price=(int(discount.discounted_price) if discount else None),
        )
    return service_list


async def attach_discounts_to_services(services: Iterable[Services]) -> list[Services]:
    service_list = list(services)
    if not service_list:
        return service_list

    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        discount_map = await _load_discount_map(
            session,
            (int(service.id) for service in service_list),
        )
    return _apply_service_discount_snapshots(service_list, discount_map)


async def get_services() -> list[Services]:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(select(Services))
        services = list(result.scalars().all())
        discount_map = await _load_discount_map(
            session,
            (int(service.id) for service in services),
        )
        return _apply_service_discount_snapshots(services, discount_map)


async def list_services_ordered() -> list[Services]:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        services = list(result.scalars().all())
        discount_map = await _load_discount_map(
            session,
            (int(service.id) for service in services),
        )
        return _apply_service_discount_snapshots(services, discount_map)


async def list_discounted_services_ordered() -> list[Services]:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        result = await session.execute(
            select(Services)
            .join(ServiceDiscounts, ServiceDiscounts.service_id == Services.id)
            .order_by(Services.id.asc())
        )
        services = list(result.scalars().all())
        discount_map = await _load_discount_map(
            session,
            (int(service.id) for service in services),
        )
        return _apply_service_discount_snapshots(services, discount_map)


async def has_global_discount_on_all_services() -> bool:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        total_services = await session.scalar(select(func.count(Services.id)))
        total_services = int(total_services or 0)
        if total_services <= 0:
            return False

        total_discounts = await session.scalar(select(func.count(ServiceDiscounts.id)))
        total_discounts = int(total_discounts or 0)
        if total_discounts != total_services:
            return False

        non_global_count = await session.scalar(
            select(func.count(ServiceDiscounts.id)).where(
                ServiceDiscounts.applied_scope != DISCOUNT_SCOPE_ALL
            )
        )
        return int(non_global_count or 0) == 0


async def count_services() -> int:
    async with async_session() as session:
        total = await session.scalar(select(func.count(Services.id)))
    return int(total or 0)


async def get_service_by_id(service_id: int) -> Services | None:
    async with async_session() as session:
        await _sync_expired_service_discounts(session, commit=True)
        service = await session.get(Services, service_id)
        if service is None:
            return None

        discount_map = await _load_discount_map(session, [int(service.id)])
        return _apply_service_discount_snapshots([service], discount_map)[0]


async def service_name_exists(
    name: str,
    *,
    exclude_service_id: int | None = None,
) -> bool:
    normalized_name = (name or "").strip().lower()
    if not normalized_name:
        return False

    async with async_session() as session:
        query = select(Services.id).where(func.lower(Services.name) == normalized_name)
        if exclude_service_id is not None:
            query = query.where(Services.id != exclude_service_id)

        existing_id = await session.scalar(query)
    return existing_id is not None


async def update_service(service_id: int, updates: dict) -> Services | None:
    async with async_session() as session:
        try:
            await _sync_expired_service_discounts(session, commit=False)
            service = await session.get(Services, service_id)
            if not service:
                return None

            updates = dict(updates)
            discount = await _load_discount_map(session, [int(service.id)])
            current_discount = discount.get(int(service.id))

            if "price" in updates:
                price = normalize_service_price(updates.get("price"))
                if price is None:
                    return None
                updates["price"] = price

            if "name" in updates and isinstance(updates["name"], str):
                updates["name"] = updates["name"].strip()

            for key, value in updates.items():
                setattr(service, key, value)

            if "price" in updates and current_discount is not None:
                current_discount.discounted_price = calculate_discounted_price(
                    int(service.price),
                    current_discount.discount_percent,
                )

            await session.commit()
            await session.refresh(service)
            if current_discount is not None:
                await session.refresh(current_discount)

            attach_service_discount_snapshot(
                service,
                discount_percent=(
                    current_discount.discount_percent if current_discount else None
                ),
                discounted_price=(
                    int(current_discount.discounted_price)
                    if current_discount is not None
                    else None
                ),
            )
            return service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def set_service_discount(
    service_id: int,
    discount_percent: object,
    *,
    applied_scope: str = DISCOUNT_SCOPE_SINGLE,
    end_at: date | None = None,
    end_time: time | None = None,
) -> Services | None:
    percent = normalize_discount_percent(discount_percent)
    normalized_scope = _normalize_discount_scope(applied_scope)
    if end_at is None or end_time is None:
        end_at, end_time = calculate_service_discount_expiry()

    async with async_session() as session:
        try:
            await _sync_expired_service_discounts(session, commit=False)
            service = await session.get(Services, service_id)
            if service is None:
                return None

            discount_map = await _load_discount_map(session, [int(service.id)])
            discount = discount_map.get(int(service.id))
            discounted_price = calculate_discounted_price(int(service.price), percent)

            if discount is None:
                discount = ServiceDiscounts(
                    service_id=int(service.id),
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
            await session.refresh(service)
            await session.refresh(discount)
            attach_service_discount_snapshot(
                service,
                discount_percent=discount.discount_percent,
                discounted_price=int(discount.discounted_price),
            )
            return service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def bulk_set_service_discount(
    service_ids: Iterable[int],
    discount_percent: object,
    *,
    applied_scope: str = DISCOUNT_SCOPE_ALL,
    end_at: date | None = None,
    end_time: time | None = None,
) -> int:
    normalized_ids = sorted({int(service_id) for service_id in service_ids})
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
                select(Services)
                .where(Services.id.in_(normalized_ids))
                .order_by(Services.id.asc())
            )
            services = list(result.scalars().all())
            discount_map = await _load_discount_map(
                session,
                (int(service.id) for service in services),
            )

            for service in services:
                discounted_price = calculate_discounted_price(int(service.price), percent)
                discount = discount_map.get(int(service.id))
                if discount is None:
                    session.add(
                        ServiceDiscounts(
                            service_id=int(service.id),
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
            return len(services)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def clear_service_discount(service_id: int) -> bool:
    async with async_session() as session:
        try:
            result = await session.execute(
                delete(ServiceDiscounts).where(ServiceDiscounts.service_id == int(service_id))
            )
            await session.commit()
            return bool(result.rowcount)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def clear_all_service_discounts() -> int:
    async with async_session() as session:
        try:
            result = await session.execute(delete(ServiceDiscounts))
            await session.commit()
            return int(result.rowcount or 0)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def bulk_update_service_prices(price_updates: Mapping[int, int]) -> int:
    if not price_updates:
        return 0

    normalized_updates: dict[int, int] = {}
    for service_id, price in price_updates.items():
        normalized_price = normalize_service_price(price)
        if normalized_price is None:
            raise ValueError(f"Invalid price for service {service_id}")
        normalized_updates[int(service_id)] = normalized_price

    async with async_session() as session:
        try:
            result = await session.execute(
                select(Services)
                .where(Services.id.in_(normalized_updates.keys()))
                .order_by(Services.id.asc())
            )
            services = list(result.scalars().all())

            for service in services:
                service.price = normalized_updates[int(service.id)]

            await session.commit()
            return len(services)
        except SQLAlchemyError:
            await session.rollback()
            raise


async def delete_service(service_id: int) -> bool:
    async with async_session() as session:
        try:
            service = await session.get(Services, service_id)
            if not service:
                return False

            await session.delete(service)
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            raise
