# database/order_utils.py
from sqlalchemy.future import select
from sqlalchemy import delete
from .db import async_session
from .models import Order

async def save_order(order: dict):
    async with async_session() as session:
        new_order = Order(
            user_id=order.get("user_id"),
            fullname=order.get("fullname"),
            phonenumber=order.get("phonenumber"),
            service_id=order.get("service_id"),
            barber_id=order.get("barber_id"),
            date=order.get("date"),
            time=order.get("time"),
        )
        session.add(new_order)
        await session.commit()

async def get_booked_times(service_id: str, barber_id: str, date: str) -> list:
    async with async_session() as session:
        result = await session.execute(
            select(Order.time).where(
                Order.service_id == service_id,
                Order.barber_id == barber_id,
                Order.date == date
            )
        )
        return [row[0] for row in result.all()]

async def delete_last_order_by_user(user_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())
        )
        last_order = result.scalars().first()

        if not last_order:
            return None

        await session.delete(last_order)
        await session.commit()
        return last_order
