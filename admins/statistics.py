# admins/statistics.py
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date
from sqlalchemy import select, func, and_
from sqlalchemy.exc import SQLAlchemyError
from sql.db import async_session
from sql.models import Order, Barbers

router = Router()


# --- Stiker yuborilganda javob ---
@router.message(F.sticker)
async def ignore_stickers(message: types.Message):
    """Stiker yuborilganda javob qaytaradi"""
    await message.answer("⚠️ Iltimos, stiker emas, faqat matn yuboring.")


# --- 📊 Umumiy statistika menyusi ---
@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    """Admin uchun umumiy statistika va barcha barberlarni ko‘rsatish"""
    today = date.today()

    try:
        async with async_session() as session:
            # --- Asosiy umumiy statistikalar ---
            total_orders = await session.scalar(select(func.count(Order.id)))
            total_users = await session.scalar(select(func.count(func.distinct(Order.user_id))))
            today_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.booked_date == today)
            )
            today_users = await session.scalar(
                select(func.count(func.distinct(Order.user_id))).where(Order.booked_date == today)
            )

            # --- Barberlar ro‘yxati ---
            barbers = (await session.execute(select(Barbers))).scalars().all()

        # --- Tugmalarni tayyorlash ---
        buttons = []
        if barbers:
            for barber in barbers:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💈 {barber.barber_fullname}",
                        callback_data=f"barber_stats:{barber.id}"
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

    except SQLAlchemyError as e:
        await message.answer("❌ Ma'lumotlarni olishda xatolik yuz berdi.")
        print(f"[STATISTICS ERROR] {e}")


# --- 💈 Alohida barber statistikasi ---
@router.callback_query(F.data.startswith("barber_stats:"))
async def barber_stats(callback: types.CallbackQuery):
    """Alohida barber statistikasi"""
    try:
        _, barber_id_str = callback.data.split(":")
        barber_id = int(barber_id_str)
    except Exception:
        return await callback.answer("❌ Noto‘g‘ri barber ID!", show_alert=True)

    today = date.today()

    try:
        async with async_session() as session:
            barber = await session.get(Barbers, barber_id)
            if not barber:
                return await callback.answer("❌ Barber topilmadi!", show_alert=True)

            # --- Statistika hisoblash ---
            total_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.barber_id == barber_id)
            )
            today_orders = await session.scalar(
                select(func.count(Order.id)).where(
                    and_(Order.barber_id == barber_id, Order.booked_date == today)
                )
            )

        # --- Orqaga tugmasi ---
        back_button = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_stats")]]
        )

        # --- Natijani chiqarish ---
        await callback.message.edit_text(
            f"💈 <b>{barber.barber_fullname}</b> statistikasi:\n\n"
            f"📦 <b>Jami buyurtmalar:</b> {total_orders or 0}\n"
            f"📅 <b>Bugungi buyurtmalar:</b> {today_orders or 0}",
            reply_markup=back_button,
            parse_mode="HTML"
        )
        await callback.answer()

    except SQLAlchemyError as e:
        await callback.answer("❌ Ma'lumotni olishda xatolik yuz berdi.", show_alert=True)
        print(f"[BARBER_STATS ERROR] {e}")


# --- ⬅️ Orqaga qaytish ---
@router.callback_query(F.data == "back_to_stats")
async def back_to_stats(callback: types.CallbackQuery):
    """Orqaga tugmasi bosilganda umumiy statistikaga qaytish"""
    try:
        await callback.message.delete()
        await show_stats(callback.message)
        await callback.answer()
    except Exception:
        await callback.answer("❌ Qaytishda xatolik yuz berdi.", show_alert=True)


# --- ❌ Foydasiz callbacklar uchun ---
@router.callback_query(F.data == "none")
async def none_callback(callback: types.CallbackQuery):
    """‘Barberlar mavjud emas’ tugmasi bosilganda"""
    await callback.answer("ℹ️ Hozircha maʼlumot yo‘q.", show_alert=True)
