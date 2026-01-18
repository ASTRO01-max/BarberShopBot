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
    # endi work_time string bo'ladi: "09:00-18:00"
    if isinstance(work_time, str) and work_time.strip():
        return work_time.strip()
    return "09:00-18:00"



def _parse_time_range(text: str):
    if "-" not in text:
        return None
    parts = [p.strip() for p in text.split("-")]
    if len(parts) != 2:
        return None
    start, end = parts
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
            return None
        if (sh * 60 + sm) >= (eh * 60 + em):
            return None
    except Exception:
        return None
    return start, end


async def _get_barber_or_message(message: types.Message):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await message.answer("Bu bo'lim faqat barberlar uchun.")
        return None
    return barber


async def _get_barber_or_alert(callback: types.CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return None
    return barber


@router.message(F.text == "🗓 Ish jadvalim")
async def show_work_schedule(message: types.Message):
    barber = await _get_barber_or_message(message)
    if not barber:
        return

    work_days = barber.work_days or "Kiritilmagan"
    work_time = _format_work_time(barber.work_time)

    text = (
        "<b>Ish jadvali</b>\n\n"
        f"Ish kunlari: <b>{work_days}</b>\n"
        f"Ish vaqti: <b>{work_time}</b>\n\n"
        "O'zgartirish uchun quyidagi tugmalardan foydalaning."
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())


@router.callback_query(F.data == "barber_change_days")
async def ask_work_days(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_days)

    await callback.message.edit_text(
        "<b>Yangi ish kunlaringizni kiriting:</b>\n\n"
        "Namuna:\n"
        "Dushanba-Juma\n"
        "Har kuni\n"
        "Dushanba, Chorshanba, Juma\n\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML",
    )


@router.message(BarberScheduleStates.waiting_for_work_days, F.text == "/cancel")
async def cancel_work_days(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    await state.clear()
    await message.answer("Jarayon bekor qilindi.")


@router.message(BarberScheduleStates.waiting_for_work_days)
async def save_work_days(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    work_days = message.text.strip()
    if len(work_days) < 3:
        await message.answer("Juda qisqa. Qaytadan kiriting:")
        return

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_days=work_days)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"<b>Ish kunlari yangilandi!</b>\n\nYangi jadval: <b>{work_days}</b>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "barber_change_time")
async def ask_work_time(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await callback.answer()
    await state.set_state(BarberScheduleStates.waiting_for_work_time)

    await callback.message.edit_text(
        "<b>Yangi ish vaqtingizni kiriting:</b>\n\n"
        "Format: <code>09:00-18:00</code>\n\n"
        "Namuna:\n"
        "09:00-18:00\n"
        "10:00-20:00\n"
        "08:30-17:30\n\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML",
    )


@router.message(BarberScheduleStates.waiting_for_work_time, F.text == "/cancel")
async def cancel_work_time(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    await state.clear()
    await message.answer("Jarayon bekor qilindi.")


@router.message(BarberScheduleStates.waiting_for_work_time)
async def save_work_time(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    work_time_text = message.text.strip()
    parsed = _parse_time_range(work_time_text)
    if not parsed:
        await message.answer(
            "Noto'g'ri format.\n\nTo'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML",
        )
        return

    start, end = parsed

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_time=f"{start}-{end}")
        )

        await session.commit()

    await state.clear()
    await message.answer(
        f"<b>Ish vaqti yangilandi!</b>\n\nYangi vaqt: <b>{work_time_text}</b>",
        parse_mode="HTML",
    )
