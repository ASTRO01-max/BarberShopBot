import logging
from typing import List, Optional
from sqlalchemy import select, update
from sql.db import async_session
from sql.models import BarberOrderInbox

logger = logging.getLogger(__name__)

async def inbox_add(order_id: int, barber_tg_id: int) -> Optional[BarberOrderInbox]:
    async with async_session() as session:
        try:
            row = BarberOrderInbox(order_id=order_id, barber_tg_id=barber_tg_id)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row
        except Exception:
            logger.exception("inbox_add failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return None

async def inbox_get_undelivered(barber_tg_id: int) -> List[BarberOrderInbox]:
    async with async_session() as session:
        try:
            res = await session.execute(
                select(BarberOrderInbox)
                .where(
                    BarberOrderInbox.barber_tg_id == barber_tg_id,
                    BarberOrderInbox.is_delivered == False
                )
                .order_by(BarberOrderInbox.id.asc())
            )
            return list(res.scalars().all())
        except Exception:
            logger.exception("inbox_get_undelivered failed")
            return []

async def inbox_mark_delivered(inbox_id: int) -> bool:
    async with async_session() as session:
        try:
            await session.execute(
                update(BarberOrderInbox)
                .where(BarberOrderInbox.id == inbox_id)
                .values(is_delivered=True)
            )
            await session.commit()
            return True
        except Exception:
            logger.exception("inbox_mark_delivered failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return False

async def inbox_mark_seen_by_order(order_id: int, barber_tg_id: int) -> bool:
    async with async_session() as session:
        try:
            await session.execute(
                update(BarberOrderInbox)
                .where(
                    BarberOrderInbox.order_id == order_id,
                    BarberOrderInbox.barber_tg_id == barber_tg_id,
                )
                .values(is_seen=True)
            )
            await session.commit()
            return True
        except Exception:
            logger.exception("inbox_mark_seen_by_order failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return False
