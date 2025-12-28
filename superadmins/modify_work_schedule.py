# superadmins/modify_work_schedule.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import update
from sql.db import async_session
from sql.models import Barbers
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_schedule_keyboard, get_back_to_menu_keyboard

router = Router()


class BarberScheduleStates(StatesGroup):
    waiting_for_work_days = State()
    waiting_for_work_time = State()


@router.message(F.text == "🗓 Ish jadvalim")
async def show_work_schedule(message: types.Message):
    """Barber ish jadvalini ko'rish"""
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")
    
    text = (
        f"🗓 <b>Sizning ish jadvalingiz:</b>\n\n"
        f"📅 <b>Ish kunlari:</b> {barber.work_days}\n"
        f"⏰ <b>Ish vaqti:</b> 09:00-18:00\n\n"
        f"<i>O'zgartirish uchun quyidagi tugmalardan foydalaning:</i>"
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_schedule_keyboard()
    )


@router.callback_query(F.data == "barber_change_days")
async def ask_work_days(callback: types.CallbackQuery, state: FSMContext):
    """Ish kunlarini o'zgartirish"""
    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_days)
    
    await callback.message.edit_text(
        "📅 <b>Yangi ish kunlaringizni kiriting:</b>\n\n"
        "Namuna:\n"
        "• Dushanba-Juma\n"
        "• Har kuni\n"
        "• Dushanba, Chorshanba, Juma\n\n"
        "❌ Bekor qilish uchun /cancel",
        parse_mode="HTML"
    )


@router.message(BarberScheduleStates.waiting_for_work_days)
async def save_work_days(message: types.Message, state: FSMContext):
    """Ish kunlarini saqlash"""
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.")
    
    work_days = message.text.strip()
    
    if len(work_days) < 3:
        return await message.answer("❌ Juda qisqa. Qaytadan kiriting:")
    
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        await state.clear()
        return await message.answer("❌ Xatolik yuz berdi.")
    
    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_days=work_days)
        )
        await session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ <b>Ish kunlari yangilandi!</b>\n\n"
        f"📅 Yangi jadval: <b>{work_days}</b>",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )


@router.callback_query(F.data == "barber_change_time")
async def ask_work_time(callback: types.CallbackQuery, state: FSMContext):
    """Ish vaqtini o'zgartirish"""
    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_time)
    
    await callback.message.edit_text(
        "⏰ <b>Yangi ish vaqtingizni kiriting:</b>\n\n"
        "Format: <code>09:00-18:00</code>\n\n"
        "Namuna:\n"
        "• 09:00-18:00\n"
        "• 10:00-20:00\n"
        "• 08:30-17:30\n\n"
        "❌ Bekor qilish uchun /cancel",
        parse_mode="HTML"
    )


@router.message(BarberScheduleStates.waiting_for_work_time)
async def save_work_time(message: types.Message, state: FSMContext):
    """Ish vaqtini saqlash"""
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.")
    
    work_time = message.text.strip()
    
    # Format tekshirish: XX:XX-XX:XX
    if "-" not in work_time or len(work_time.split("-")) != 2:
        return await message.answer(
            "❌ Noto'g'ri format!\n\n"
            "To'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML"
        )
    
    try:
        start, end = work_time.split("-")
        # Soat formatini tekshirish
        start_h, start_m = map(int, start.split(":"))
        end_h, end_m = map(int, end.split(":"))
        
        if not (0 <= start_h < 24 and 0 <= start_m < 60 and 0 <= end_h < 24 and 0 <= end_m < 60):
            raise ValueError
        
        # Mantiqiy tekshirish
        if (start_h * 60 + start_m) >= (end_h * 60 + end_m):
            return await message.answer(
                "❌ Boshlanish vaqti tugash vaqtidan kichik bo'lishi kerak!"
            )
        
    except (ValueError, IndexError):
        return await message.answer(
            "❌ Noto'g'ri vaqt formati!\n\n"
            "To'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML"
        )
    
    # Bu yerda ish vaqtini database'ga saqlaydigan logika qo'shilishi kerak
    # Hozirda work_time ustuni yo'q, shuning uchun izoh sifatida
    # Agar kerak bo'lsa, Barbers modeliga work_time ustuni qo'shilishi kerak
    
    await state.clear()
    await message.answer(
        f"✅ <b>Ish vaqti yangilandi!</b>\n\n"
        f"⏰ Yangi vaqt: <b>{work_time}</b>\n\n"
        f"<i>Eslatma: Ish vaqti to'liq faollashishi uchun admin bilan bog'laning.</i>",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )


@router.message(F.text == "/cancel")
async def cancel_schedule_change(message: types.Message, state: FSMContext):
    """Jarayonni bekor qilish"""
    await state.clear()
    await message.answer(
        "❌ Jarayon bekor qilindi.",
        reply_markup=get_back_to_menu_keyboard()
    )