# superadmins/own_statistics.py
from aiogram import Router, types, F
from sqlalchemy import select, func, and_
from datetime import date, timedelta
from sql.db import async_session
from sql.models import Order, Barbers
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_back_to_menu_keyboard

router = Router()


@router.message(F.text == "📊 O'z statistikam")
async def show_barber_statistics(message: types.Message):
    """Barber o'z statistikasini ko'rish"""
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")
    
    barber_name = f"{barber.barber_first_name} {barber.barber_last_name or ''}"
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    async with async_session() as session:
        # Jami statistika
        total_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.barber_id == barber_name)
        )
        
        # Bugungi buyurtmalar
        today_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_name,
                    Order.date == today
                )
            )
        )
        
        # Kutilayotgan buyurtmalar (kelajak)
        pending_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_name,
                    Order.date >= today
                )
            )
        )
        
        # Yakunlangan buyurtmalar (o'tmish)
        finished_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_name,
                    Order.date < today
                )
            )
        )
        
        # Haftalik statistika
        week_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_name,
                    Order.date >= week_ago,
                    Order.date <= today
                )
            )
        )
        
        # Oylik statistika
        month_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_name,
                    Order.date >= month_ago,
                    Order.date <= today
                )
            )
        )
        
        # Noyob mijozlar soni
        unique_clients = await session.scalar(
            select(func.count(func.distinct(Order.user_id))).where(
                Order.barber_id == barber_name
            )
        )
    
    text = (
        f"📊 <b>Statistika - {barber.barber_first_name}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📈 Umumiy ko'rsatkichlar:</b>\n"
        f"📦 Jami buyurtmalar: <b>{total_orders or 0}</b>\n"
        f"✅ Yakunlangan: <b>{finished_orders or 0}</b>\n"
        f"⏳ Kutilayotgan: <b>{pending_orders or 0}</b>\n"
        f"👥 Mijozlar: <b>{unique_clients or 0}</b>\n\n"
        f"<b>📅 Vaqt bo'yicha:</b>\n"
        f"📅 Bugun: <b>{today_orders or 0}</b>\n"
        f"📆 Hafta: <b>{week_orders or 0}</b>\n"
        f"📊 Oy: <b>{month_orders or 0}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )
