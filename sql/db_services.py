#sql/db_services.py
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sql.db import async_session
from sql.models import Services
from utils.validators import INT32_MAX


def _normalize_price(value):
    if isinstance(value, str):
        if not value.isdigit():
            return None
        value = int(value)
    if not isinstance(value, int):
        return None
    if value < 0 or value > INT32_MAX:
        return None
    return value

async def create_service(data: dict):
    async with async_session() as session:
        try:
            if "price" in data:
                price = _normalize_price(data.get("price"))
                if price is None:
                    return None
                data = dict(data)
                data["price"] = price
            new_service = Services(**data)
            session.add(new_service)
            await session.commit()
            await session.refresh(new_service)
            return new_service
        except SQLAlchemyError:
            await session.rollback()
            raise


async def get_services():
    async with async_session() as session:
        result = await session.execute(select(Services))
        return result.scalars().all()


async def update_service(service_id: int, updates: dict):
    async with async_session() as session:
        service = await session.get(Services, service_id)
        if not service:
            return None
        if "price" in updates:
            price = _normalize_price(updates.get("price"))
            if price is None:
                return None
            updates = dict(updates)
            updates["price"] = price
        for key, val in updates.items():
            setattr(service, key, val)
        await session.commit()
        return service


async def delete_service(service_id: int):
    async with async_session() as session:
        service = await session.get(Services, service_id)
        if not service:
            return False
        await session.delete(service)
        await session.commit()
        return True
