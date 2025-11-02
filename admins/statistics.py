# admins/statistics.py
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date
from sqlalchemy import select, func, and_
from sql.db import async_session
from sql.models import Order, Barbers

router = Router()


# --- Faqat matnli xabarlar uchun filter ---
@router.message(F.sticker)
async def ignore_stickers(message: types.Message):
    """Stiker yuborilganda database bilan ishlamaslik"""
    await message.answer("⚠️ Iltimos, stiker emas, faqat matn yuboring.")


# --- Umumiy statistika menyusi ---
@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    """Admin uchun umumiy statistika va barberlar ro‘yxatini ko‘rsatish"""
    async with async_session() as session:
        total_orders = await session.scalar(select(func.count(Order.id)))
        total_users = await session.scalar(select(func.count(func.distinct(Order.user_id))))
        today = date.today()
        today_orders = await session.scalar(select(func.count(Order.id)).where(Order.date == today))
        today_users = await session.scalar(
            select(func.count(func.distinct(Order.user_id))).where(Order.date == today)
        )
        barbers = (await session.execute(select(Barbers))).scalars().all()

    buttons = []
    if barbers:
        for b in barbers:
            # Barber ID ni faqat son sifatida uzatamiz (str emas)
            buttons.append([
                InlineKeyboardButton(
                    text=f"💈 {b.barber_fullname}",
                    callback_data=f"barber_stats:{b.id}"
                )
            ])
    else:
        buttons = [[InlineKeyboardButton(text="❌ Barberlar mavjud emas", callback_data="none")]]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"📊 <b>Umumiy Statistika</b>\n\n"
        f"📦 <b>Jami buyurtmalar:</b> {total_orders or 0}\n"
        f"👥 <b>Foydalanuvchilar soni:</b> {total_users or 0}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {today_orders or 0}\n"
        f"🙋‍♂️ <b>Bugungi foydalanuvchilar:</b> {today_users or 0}\n\n"
        f"💈 <b>Barberlar bo‘yicha statistika:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )


# --- Har bir barber bo‘yicha statistika ---
@router.callback_query(F.data.startswith("barber_stats:"))
async def barber_stats(callback: types.CallbackQuery):
    """Alohida barber statistikasi"""
    try:
        # ID ni son sifatida o‘qib olamiz
        _, barber_id_str = callback.data.split(":")
        barber_id = int(barber_id_str)
    except Exception:
        return await callback.answer("❌ Noto‘g‘ri barber ID!", show_alert=True)

    today = date.today()

    async with async_session() as session:
        barber = await session.get(Barbers, barber_id)
        if not barber:
            return await callback.answer("❌ Barber topilmadi!", show_alert=True)

        total_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.barber_id == barber_id)
        )
        today_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(Order.barber_id == barber_id, Order.date == today)
            )
        )
        upcoming_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(Order.barber_id == barber_id, Order.date > today)
            )
        )

    back_button = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_stats")]]
    )

    await callback.message.edit_text(
        f"💈 <b>{barber.barber_fullname}</b> statistikasi:\n\n"
        f"📦 <b>Jami buyurtmalar:</b> {total_orders or 0}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {today_orders or 0}\n"
        f"⏳ <b>Kutilayotgan buyurtmalar:</b> {upcoming_orders or 0}",
        reply_markup=back_button,
        parse_mode="HTML"
    )
    await callback.answer()


# --- Orqaga qaytish funksiyasi ---
@router.callback_query(F.data == "back_to_stats")
async def back_to_stats(callback: types.CallbackQuery):
    """Orqaga tugmasi bosilganda umumiy statistikaga qaytish"""
    await callback.message.delete()
    await show_stats(callback.message)
