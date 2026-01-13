# superadmins/pause_today.py
from aiogram import Router, types, F
from sqlalchemy import update, select, and_, func  # ✅ func qo'shildi
from datetime import date
from sql.db import async_session
from sql.models import Barbers, Order
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_pause_confirm_keyboard

router = Router()


@router.message(F.text == "⛔ Bugun ishlamayman")
async def ask_pause_confirmation(message: types.Message):
    """Bugungi ishni to'xtatish tasdiqlanishi"""
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")
    
    if barber.is_paused:
        return await message.answer("Pause already active for today.")

    # Bugungi buyurtmalar sonini tekshirish
    today = date.today()
    barber_key = str(barber.id)
    
    async with async_session() as session:
        orders_count = await session.scalar(
            select(func.count(Order.id)).where(
                and_(
                    Order.barber_id == barber_key,
                    Order.date == today
                )
            )
        )
    
    text = (
        f"⚠️ <b>Diqqat</b>\n\n"
        f"Bugungi ishni to'xtatmoqchimisiz?\n"
        f"📋 Bugungi buyurtmalar: <b>{orders_count or 0}</b>\n\n"
    )
    
    if orders_count and orders_count > 0:
        text += (
            f"⚠️ <b>Eslatma:</b> Sizda bugun {orders_count} ta buyurtma bor.\n"
            f"Ish to'xtatilsa, mijozlarga xabar yuboriladi.\n\n"
        )
    
    text += f"Davom ettirishni xohlaysizmi?"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_pause_confirm_keyboard()
    )


@router.callback_query(F.data == "barber_pause_confirm")
async def confirm_pause_today(callback: types.CallbackQuery):
    """Bugungi ishni to'xtatishni tasdiqlash"""
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)
        return
    
    today = date.today()
    barber_key = str(barber.id)
    
    # Bugungi buyurtmalarni olish
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(
                and_(
                    Order.barber_id == barber_key,
                    Order.date == today
                )
            )
        )
        orders = result.scalars().all()
    
    # Mijozlarga xabar yuborish
    notified = 0
    for order in orders:
        try:
            await callback.bot.send_message(
                chat_id=order.user_id,
                text=(
                    f"⚠️ <b>Muhim xabar!</b>\n\n"
                    f"Hurmatli {order.fullname}!\n\n"
                    f"Kechirasiz, {barber.barber_first_name} usta bugun "
                    f"ishlamasligi sababli, sizning bugungi ({order.time.strftime('%H:%M')}) "
                    f"navbatingiz bekor qilindi.\n\n"
                    f"Iltimos, boshqa kun yoki boshqa ustadan navbat oling.\n\n"
                    f"Noqulaylik uchun uzr so'raymiz. 🙏"
                ),
                parse_mode="HTML"
            )
            notified += 1
        except Exception:
            continue
    
    # Buyurtmalarni o'chirish
    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(is_paused=True)
        )
        for order in orders:
            await session.delete(order)
        await session.commit()
    
    await callback.message.edit_text(
        f"✅ <b>Bugungi ish to'xtatildi</b>\n\n"
        f"📋 O'chirilgan buyurtmalar: <b>{len(orders)}</b>\n"
        f"📨 Xabarnoma yuborildi: <b>{notified}</b>\n\n"
        f"Ertaga yana faol bo'lishingiz mumkin.",
        parse_mode="HTML"
    )
    
    await callback.answer("✅ Bugungi ish to'xtatildi")


@router.callback_query(F.data == "barber_menu")
async def back_to_barber_menu(callback: types.CallbackQuery):
    """Barber menyusiga qaytish"""
    from .superadmin_buttons import get_barber_menu
    
    await callback.message.delete()
    await callback.message.answer(
        "💈 Barber paneliga xush kelibsiz",
        reply_markup=get_barber_menu()
    )
    await callback.answer()
