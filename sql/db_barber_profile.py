from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import BarberProfileSettings


ALLOWED_HIDDEN_FIELDS = {
    "experience",
    "work_days",
    "work_time",
    "breakdown",
    "phone",
}


def _normalize_barber_id(barber_id) -> int | None:
    try:
        value = int(barber_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _normalize_hidden_fields(raw_value) -> list[str]:
    if not raw_value:
        return []

    if isinstance(raw_value, str):
        items = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        items = list(raw_value)
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        field = str(item).strip()
        if field not in ALLOWED_HIDDEN_FIELDS or field in seen:
            continue
        seen.add(field)
        normalized.append(field)
    return normalized


async def get_barber_hidden_fields(barber_id) -> list[str]:
    normalized_barber_id = _normalize_barber_id(barber_id)
    if normalized_barber_id is None:
        return []

    async with async_session() as session:
        result = await session.execute(
            select(BarberProfileSettings.hidden_fields).where(
                BarberProfileSettings.barber_id == normalized_barber_id
            )
        )
        hidden_fields = result.scalar_one_or_none()

    return _normalize_hidden_fields(hidden_fields)


async def set_barber_hidden_fields(barber_id, hidden_fields) -> list[str]:
    normalized_barber_id = _normalize_barber_id(barber_id)
    if normalized_barber_id is None:
        return []

    normalized_hidden_fields = _normalize_hidden_fields(hidden_fields)

    async with async_session() as session:
        try:
            settings = await session.get(BarberProfileSettings, normalized_barber_id)
            if settings is None:
                settings = BarberProfileSettings(
                    barber_id=normalized_barber_id,
                    hidden_fields=normalized_hidden_fields,
                )
                session.add(settings)
            else:
                settings.hidden_fields = normalized_hidden_fields

            await session.commit()
            return normalized_hidden_fields
        except SQLAlchemyError:
            await session.rollback()
            raise


async def set_barber_field_visibility(barber_id, field_key: str, hidden: bool) -> list[str]:
    if field_key not in ALLOWED_HIDDEN_FIELDS:
        return await get_barber_hidden_fields(barber_id)

    hidden_fields = set(await get_barber_hidden_fields(barber_id))
    if hidden:
        hidden_fields.add(field_key)
    else:
        hidden_fields.discard(field_key)
    return await set_barber_hidden_fields(barber_id, sorted(hidden_fields))
