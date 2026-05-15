from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.db_barber_services import service_discount_expiry_worker
from sql.models import Services


async def create_service(data: dict) -> Services | None:
    clean_data = {
        "name": (data.get("name") or "").strip(),
        "photo": data.get("photo"),
    }
    if not clean_data["name"]:
        return None

    async with async_session() as session:
        try:
            service = Services(**clean_data)
            session.add(service)
            await session.commit()
            await session.refresh(service)
            return service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def get_services() -> list[Services]:
    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        return list(result.scalars().all())


async def list_services_ordered() -> list[Services]:
    return await get_services()


async def count_services() -> int:
    async with async_session() as session:
        total = await session.scalar(select(func.count(Services.id)))
    return int(total or 0)


async def get_service_by_id(service_id: int) -> Services | None:
    async with async_session() as session:
        return await session.get(Services, int(service_id))


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
            query = query.where(Services.id != int(exclude_service_id))
        existing_id = await session.scalar(query)
    return existing_id is not None


async def update_service(service_id: int, updates: dict) -> Services | None:
    allowed_updates = {}
    if "name" in updates:
        name = (updates.get("name") or "").strip()
        if not name:
            return None
        allowed_updates["name"] = name
    if "photo" in updates:
        allowed_updates["photo"] = updates.get("photo")

    async with async_session() as session:
        try:
            service = await session.get(Services, int(service_id))
            if service is None:
                return None

            for key, value in allowed_updates.items():
                setattr(service, key, value)

            await session.commit()
            await session.refresh(service)
            return service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def delete_service(service_id: int) -> bool:
    async with async_session() as session:
        try:
            service = await session.get(Services, int(service_id))
            if service is None:
                return False
            await session.delete(service)
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            raise
