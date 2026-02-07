# sql/db_info.py
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sql.db import async_session
from sql.models import Info


INFO_SINGLETON_ID = 1  # odatda bitta qatordan foydalanamiz


async def get_info() -> Info | None:
    async with async_session() as session:
        return await session.get(Info, INFO_SINGLETON_ID)


async def ensure_info_row() -> Info:
    """
    info jadvalida 1 ta row bo'lishini kafolatlaydi.
    """
    async with async_session() as session:
        obj = await session.get(Info, INFO_SINGLETON_ID)
        if obj:
            return obj
        obj = Info(id=INFO_SINGLETON_ID)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj


async def update_info_fields(updates: dict) -> Info:
    """
    Bir nechta ustunni birdan yangilash.
    """
    async with async_session() as session:
        obj = await session.get(Info, INFO_SINGLETON_ID)
        if not obj:
            obj = Info(id=INFO_SINGLETON_ID)
            session.add(obj)
            await session.flush()

        for k, v in updates.items():
            setattr(obj, k, v)

        try:
            await session.commit()
            await session.refresh(obj)
            return obj
        except SQLAlchemyError:
            await session.rollback()
            raise


async def update_info_field(field: str, value) -> Info:
    return await update_info_fields({field: value})
