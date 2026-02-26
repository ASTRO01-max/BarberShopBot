# sql/db_barbers_expanded.py
import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import BarberExpanded


def _normalize_barber_id(barber_id) -> int | None:
    try:
        value = int(barber_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _normalize_service_id(service_id) -> int | None:
    try:
        value = int(service_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_barber_includes(raw_value) -> list[int]:
    if raw_value is None:
        return []

    parsed = raw_value
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if not candidate:
            return []

        if candidate.startswith("[") and candidate.endswith("]"):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = candidate
        else:
            parsed = candidate

    items: list = []
    if isinstance(parsed, (list, tuple, set)):
        items = list(parsed)
    elif isinstance(parsed, str):
        items = [part.strip() for part in parsed.split(",") if part.strip()]
    else:
        return []

    normalized: list[int] = []
    seen: set[int] = set()
    for item in items:
        sid = _normalize_service_id(item)
        if sid is None or sid in seen:
            continue
        seen.add(sid)
        normalized.append(sid)
    return normalized


def _normalize_service_ids(service_ids) -> list[int]:
    if service_ids is None:
        return []
    return _parse_barber_includes(service_ids)


async def get_barber_services(barber_id):
    normalized_barber_id = _normalize_barber_id(barber_id)
    if normalized_barber_id is None:
        return []

    async with async_session() as session:
        result = await session.execute(
            select(BarberExpanded.barber_includes).where(
                BarberExpanded.barber_id == normalized_barber_id
            )
        )
        barber_includes = result.scalar_one_or_none()
    return _parse_barber_includes(barber_includes)


async def set_barber_services(barber_id, service_ids: list[int]):
    normalized_barber_id = _normalize_barber_id(barber_id)
    if normalized_barber_id is None:
        return []

    normalized_service_ids = _normalize_service_ids(service_ids)

    async with async_session() as session:
        try:
            result = await session.execute(
                select(BarberExpanded).where(
                    BarberExpanded.barber_id == normalized_barber_id
                )
            )
            expanded = result.scalars().first()

            if expanded is None:
                expanded = BarberExpanded(
                    barber_id=normalized_barber_id,
                    barber_includes=normalized_service_ids,
                )
                session.add(expanded)
            else:
                expanded.barber_includes = normalized_service_ids

            await session.commit()
            return normalized_service_ids
        except SQLAlchemyError:
            await session.rollback()
            raise


async def add_service_to_barber(barber_id, service_id):
    normalized_barber_id = _normalize_barber_id(barber_id)
    normalized_service_id = _normalize_service_id(service_id)
    if normalized_barber_id is None or normalized_service_id is None:
        return False

    async with async_session() as session:
        try:
            result = await session.execute(
                select(BarberExpanded).where(
                    BarberExpanded.barber_id == normalized_barber_id
                )
            )
            expanded = result.scalars().first()

            if expanded is None:
                expanded = BarberExpanded(
                    barber_id=normalized_barber_id,
                    barber_includes=[normalized_service_id],
                )
                session.add(expanded)
                await session.commit()
                return True

            includes = _parse_barber_includes(expanded.barber_includes)
            if normalized_service_id in includes:
                return False

            includes.append(normalized_service_id)
            expanded.barber_includes = includes
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            raise


async def remove_service_from_barber(barber_id, service_id):
    normalized_barber_id = _normalize_barber_id(barber_id)
    normalized_service_id = _normalize_service_id(service_id)
    if normalized_barber_id is None or normalized_service_id is None:
        return False

    async with async_session() as session:
        try:
            result = await session.execute(
                select(BarberExpanded).where(
                    BarberExpanded.barber_id == normalized_barber_id
                )
            )
            expanded = result.scalars().first()
            if expanded is None:
                return False

            includes = _parse_barber_includes(expanded.barber_includes)
            if normalized_service_id not in includes:
                return False

            expanded.barber_includes = [sid for sid in includes if sid != normalized_service_id]
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            raise


async def get_barbers_by_service(service_id):
    normalized_service_id = _normalize_service_id(service_id)
    if normalized_service_id is None:
        return []

    async with async_session() as session:
        result = await session.execute(
            select(BarberExpanded.barber_id, BarberExpanded.barber_includes)
        )
        rows = result.all()

    barber_ids: list[int] = []
    seen: set[int] = set()
    for barber_id, barber_includes in rows:
        normalized_barber_id = _normalize_barber_id(barber_id)
        if normalized_barber_id is None:
            continue

        includes = _parse_barber_includes(barber_includes)
        if normalized_service_id not in includes:
            continue

        if normalized_barber_id in seen:
            continue
        seen.add(normalized_barber_id)
        barber_ids.append(normalized_barber_id)

    return barber_ids
