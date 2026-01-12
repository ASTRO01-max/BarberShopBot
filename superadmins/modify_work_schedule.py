from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import update
from sql.db import async_session
from sql.models import Barbers
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_schedule_keyboard

router = Router()


class BarberScheduleStates(StatesGroup):
    waiting_for_work_days = State()
    waiting_for_work_time = State()


def _format_work_time(work_time) -> str:
    # work_time: {"from": "09:00", "to": "18:00"} yoki None
    if isinstance(work_time, dict) and work_time.get("from") and work_time.get("to"):
        return f'{work_time["from"]}-{work_time["to"]}'
    return "09:00-18:00"  # default ko'rinish


@router.message(F.text == "🗓 Ish jadvalim")
async def show_work_schedule(message: types.Message):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    text = (
        f"🗓 <b>Ish jadvali</b>\n\n"
        f"📅 <b>Ish kunlari:</b> {barber.work_days}\n"
        f"⏰ <b>Ish vaqti:</b> {_format_work_time(barber.work_time)}\n\n"
        f"<i>O'zgartirish uchun quyidagi tugmalardan foydalaning.</i>"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())


@router.callback_query(F.data == "barber_change_days")
async def ask_work_days(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_days)

    await callback.message.edit_text(
        "📅 <b>Yangi ish kunlaringizni kiriting:</b>\n\n"
        "Namuna:\n"
        "• Dushanba-Juma\n"
        "• Har kuni\n"
        "• Dushanba, Chorshanba, Juma\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode="HTML"
    )


@router.message(BarberScheduleStates.waiting_for_work_days)
async def save_work_days(message: types.Message, state: FSMContext):
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
        parse_mode="HTML"
    )


@router.callback_query(F.data == "barber_change_time")
async def ask_work_time(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_time)

    await callback.message.edit_text(
        "⏰ <b>Yangi ish vaqtingizni kiriting:</b>\n\n"
        "Format: <code>09:00-18:00</code>\n\n"
        "Namuna:\n"
        "• 09:00-18:00\n"
        "• 10:00-20:00\n"
        "• 08:30-17:30\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode="HTML"
    )


@router.message(BarberScheduleStates.waiting_for_work_time)
async def save_work_time(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.")

    work_time = message.text.strip()
    if "-" not in work_time or len(work_time.split("-")) != 2:
        return await message.answer(
            "❌ Noto'g'ri format!\n\nTo'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML"
        )

    try:
        start, end = [x.strip() for x in work_time.split("-")]
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))

        if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
            raise ValueError

        if (sh * 60 + sm) >= (eh * 60 + em):
            return await message.answer("❌ Boshlanish vaqti tugash vaqtidan kichik bo'lishi kerak!")
    except Exception:
        return await message.answer(
            "❌ Noto'g'ri vaqt formati!\n\nTo'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML"
        )

    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    if not barber:
        await state.clear()
        return await message.answer("❌ Xatolik yuz berdi.")

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_time={"from": start, "to": end})
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Ish vaqti yangilandi!</b>\n\n"
        f"⏰ Yangi vaqt: <b>{work_time}</b>",
        parse_mode="HTML"
    )


@router.message(F.text == "/cancel")
async def cancel_schedule_change(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")
