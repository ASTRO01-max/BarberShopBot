# sql/db_users_utils.py
import logging
from typing import Optional, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .db import async_session
from .models import User

logger = logging.getLogger(__name__)


async def save_user(data: Dict) -> Optional[User]:
    """
    Saqlaydi yoki mavjud bo'lsa yangilaydi. Qaytaradi: User yoki None.
    Kutilgan data keys: "tg_id" (yoki "id"), "fullname", "phone" yoki "phonenumber"
    """
    try:
        tg_id = int(data.get("tg_id") or data.get("id"))
    except Exception:
        logger.error("save_user: tg_id topilmadi yoki noto'g'ri: %s", data)
        return None

    fullname = data.get("fullname")
    phone = data.get("phone") or data.get("phonenumber")

    async with async_session() as session:
        try:
            # Avval mavjud foydalanuvchini qidiradi
            res = await session.execute(select(User).where(User.tg_id == tg_id))
            user = res.scalar_one_or_none()

            if user:
                changed = False
                if fullname and user.fullname != fullname:
                    user.fullname = fullname
                    changed = True
                if phone and user.phone != phone:
                    user.phone = phone
                    changed = True

                if changed:
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                return user

            # Agar yo'q bo'lsa — yangi yozuv yaratamiz
            new_user = User(tg_id=tg_id, fullname=fullname, phone=phone)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user

        except Exception as e:
            logger.exception("save_user: DB error")
            try:
                await session.rollback()
            except Exception:
                pass
            return None


async def get_user_by_tg_id(tg_id: int) -> Optional[User]:
    """Telegram ID bo'yicha userni oladi"""
    try:
        tg_id = int(tg_id)
    except Exception:
        return None

    async with async_session() as session:
        try:
            res = await session.execute(select(User).where(User.tg_id == tg_id))
            return res.scalar_one_or_none()
        except Exception:
            logger.exception("get_user_by_tg_id: DB error")
            return None


# backward-compatibility alias (ko'p joylarda get_user nomi ishlatilgan bo'lsa)
async def get_user(user_id: int) -> Optional[User]:
    return await get_user_by_tg_id(user_id)


async def update_user(user_id: int, new_fullname: Optional[str] = None, new_phone: Optional[str] = None) -> bool:
    """
    Foydalanuvchi ma'lumotlarini yangilaydi (tg_id bo'yicha).
    Qaytaradi True/False.
    """
    try:
        tg_id = int(user_id)
    except Exception:
        return False

    async with async_session() as session:
        try:
            res = await session.execute(select(User).where(User.tg_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                return False

            updated = False
            if new_fullname and user.fullname != new_fullname:
                user.fullname = new_fullname
                updated = True
            if new_phone and user.phone != new_phone:
                user.phone = new_phone
                updated = True

            if updated:
                session.add(user)
                await session.commit()
            return True

        except Exception:
            logger.exception("update_user: DB error")
            try:
                await session.rollback()
            except Exception:
                pass
            return False


async def delete_user(user_id: int) -> bool:
    """
    Foydalanuvchini tg_id bo'yicha o'chiradi.
    """
    try:
        tg_id = int(user_id)
    except Exception:
        return False

    async with async_session() as session:
        try:
            res = await session.execute(select(User).where(User.tg_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                return False

            await session.delete(user)
            await session.commit()
            return True
        except Exception:
            logger.exception("delete_user: DB error")
            try:
                await session.rollback()
            except Exception:
                pass
            return False
