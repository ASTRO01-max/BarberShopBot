from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sql.db import async_session
from sql.models import Barbers


async def create_barber(data: dict):
    async with async_session() as session:
        try:
            new_barber = Barbers(**data)
            session.add(new_barber)
            await session.commit()
            await session.refresh(new_barber)
            return new_barber
        except SQLAlchemyError:
            await session.rollback()
            raise


async def get_barbers():
    async with async_session() as session:
        result = await session.execute(select(Barbers))
        return result.scalars().all()


async def update_barber(barber_id: int, updates: dict):
    async with async_session() as session:
        barber = await session.get(Barbers, barber_id)
        if not barber:
            return None
        for key, val in updates.items():
            setattr(barber, key, val)
        await session.commit()
        return barber


async def delete_barber(barber_id: int):
    async with async_session() as session:
        barber = await session.get(Barbers, barber_id)
        if not barber:
            return False
        await session.delete(barber)
        await session.commit()
        return True
