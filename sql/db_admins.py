from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sql.db import async_session
from sql.models import Admins


async def create_admin(data: dict):
    async with async_session() as session:
        try:
            new_admin = Admins(**data)
            session.add(new_admin)
            await session.commit()
            await session.refresh(new_admin)
            return new_admin
        except SQLAlchemyError:
            await session.rollback()
            raise


async def get_admins():
    async with async_session() as session:
        result = await session.execute(select(Admins))
        return result.scalars().all()


async def update_admin(admin_id: int, updates: dict):
    async with async_session() as session:
        admin = await session.get(Admins, admin_id)
        if not admin:
            return None
        for key, val in updates.items():
            setattr(admin, key, val)
        await session.commit()
        return admin


async def delete_admin(admin_id: int):
    async with async_session() as session:
        admin = await session.get(Admins, admin_id)
        if not admin:
            return False
        await session.delete(admin)
        await session.commit()
        return True
