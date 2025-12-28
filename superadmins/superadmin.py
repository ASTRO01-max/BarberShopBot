# superadmins/superadmin.py
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Barbers

router = Router()


async def is_barber(tg_id: int) -> bool:
    """Foydalanuvchi barber ekanligini tekshirish"""
    async with async_session() as session:
        result = await session.execute(
            select(Barbers).where(Barbers.tg_id == tg_id)
        )
        return result.scalar() is not None


async def get_barber_by_tg_id(tg_id: int):
    """Telegram ID bo'yicha barberni olish"""
    async with async_session() as session:
        result = await session.execute(
            select(Barbers).where(Barbers.tg_id == tg_id)
        )
        return result.scalar()


@router.message(Command("barber"))
async def barber_entry(message: types.Message):
    """Barber paneliga kirish"""
    tg_id = message.from_user.id

    if not await is_barber(tg_id):
        return await message.answer(
            "❌ Siz barber sifatida ro'yxatdan o'tmagansiz.\n"
            "Iltimos, admin bilan bog'laning."
        )

    barber = await get_barber_by_tg_id(tg_id)
    
    from .superadmin_buttons import get_barber_menu
    await message.answer(
        f"👋 Xush kelibsiz, {barber.barber_first_name}!\n\n"
        f"💈 Barber paneliga xush kelibsiz.",
        reply_markup=get_barber_menu()
    )