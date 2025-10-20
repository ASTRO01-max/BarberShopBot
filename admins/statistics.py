#admins/statistics.py
from aiogram import Router, types, F
from datetime import date
from sqlalchemy import select, func
from sql.db import async_session
from sql.models import Order

router = Router()

@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    # 1️⃣ Ma'lumotlarni olish
    async with async_session() as session:
        # Jami buyurtmalar soni
        total_orders = await session.scalar(select(func.count(Order.id)))

        # Jami foydalanuvchilar soni (unikal user_id lar)
        total_users = await session.scalar(
            select(func.count(func.distinct(Order.user_id)))
        )

        # Bugungi sana
        today = date.today()

        # Bugungi buyurtmalar soni
        today_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.date == today)
        )

        # Bugungi foydalanuvchilar soni (unikal)
        today_users = await session.scalar(
            select(func.count(func.distinct(Order.user_id))).where(Order.date == today)
        )

    # 2️⃣ Natijani chiroyli shaklda chiqarish
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"📦 <b>Jami buyurtmalar:</b> {total_orders}\n"
        f"👥 <b>Foydalanuvchilar soni:</b> {total_users}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {today_orders}\n"
        f"🙋‍♂️ <b>Bugungi foydalanuvchilar:</b> {today_users}",
        parse_mode="HTML"
    )
