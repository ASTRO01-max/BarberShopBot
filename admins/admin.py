#admins/admin.py
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Admins
# from sql.models import Barbers
from .admin_buttons import markup

router = Router()

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    user_tg_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(
            select(Admins).where(Admins.tg_id == user_tg_id)
            # select(Barbers).where(Barbers.tg_id == user_tg_id)
        )
        admin = result.scalars().first()

    if not admin:
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")

    await message.answer(f"🔐 Xush kelibsiz, {admin.admin_fullname or 'Admin'}!", reply_markup=markup)
