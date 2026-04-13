from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.db_info import INFO_SINGLETON_ID, ensure_info_row
from sql.models import InfoProfileSettings

ALLOWED_INFO_HIDDEN_FIELDS = {
    "telegram",
    "instagram",
    "website",
    "phone_number",
    "phone_number2",
    "region",
    "district",
    "street",
    "address_text",
    "work_time_text",
}


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
        if field not in ALLOWED_INFO_HIDDEN_FIELDS or field in seen:
            continue
        seen.add(field)
        normalized.append(field)
    return normalized


async def get_info_hidden_fields() -> list[str]:
    await ensure_info_row()
    async with async_session() as session:
        result = await session.execute(
            select(InfoProfileSettings.hidden_fields).where(
                InfoProfileSettings.info_id == INFO_SINGLETON_ID
            )
        )
        hidden_fields = result.scalar_one_or_none()
    return _normalize_hidden_fields(hidden_fields)


async def set_info_hidden_fields(hidden_fields) -> list[str]:
    await ensure_info_row()
    normalized_hidden_fields = _normalize_hidden_fields(hidden_fields)

    async with async_session() as session:
        try:
            result = await session.execute(
                select(InfoProfileSettings).where(
                    InfoProfileSettings.info_id == INFO_SINGLETON_ID
                )
            )
            settings = result.scalars().first()
            if settings is None:
                settings = InfoProfileSettings(
                    info_id=INFO_SINGLETON_ID,
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


async def set_info_field_visibility(field_key: str, hidden: bool) -> list[str]:
    if field_key not in ALLOWED_INFO_HIDDEN_FIELDS:
        return await get_info_hidden_fields()

    hidden_fields = set(await get_info_hidden_fields())
    if hidden:
        hidden_fields.add(field_key)
    else:
        hidden_fields.discard(field_key)
    return await set_info_hidden_fields(sorted(hidden_fields))
