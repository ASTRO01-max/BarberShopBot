from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy import update

from sql.db import async_session
from sql.models import Barbers
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_schedule_keyboard
from utils.states import BarberPage

router = Router()


def _format_work_time(work_time) -> str:
    if isinstance(work_time, str) and work_time.strip():
        return work_time.strip()
    return "Kiritilmagan"


def _parse_time_range(text: str):
    """
    Qabul qilinadigan format: 09:00-18:00
    """
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
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return None
    return barber


async def _get_barber_or_alert(callback: types.CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return None
    return barber


async def _render_schedule_text(barber: Barbers) -> str:
    work_days = barber.work_days or "Kiritilmagan"
    work_time = _format_work_time(barber.work_time)
    return (
        "<b>🗓 Ish jadvali</b>\n\n"
        f"📅 Ish kunlari: <b>{work_days}</b>\n"
        f"⏰ Ish vaqti: <b>{work_time}</b>\n\n"
        "O'zgartirish uchun quyidagi tugmalardan foydalaning:"
    )


async def _show_schedule_exact(
    *,
    bot,
    chat_id: int,
    barber: Barbers,
    message_id: int | None,
):
    """
    Talab bo'yicha: faqat 1 ta natija.
    - Agar message_id bo'lsa: o'sha xabarni edit qiladi (yangi xabar chiqmaydi)
    - Bo'lmasa: bitta yangi jadval xabarini yuboradi
    """
    text = await _render_schedule_text(barber)
    kb = get_schedule_keyboard()

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return
        except Exception:
            pass

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


# 1) Jadvalni ko'rsatish
@router.message(F.text == "🗓 Ish jadvalim")
async def show_work_schedule(message: types.Message, state: FSMContext):
    await state.clear()

    barber = await _get_barber_or_message(message)
    if not barber:
        return

    text = await _render_schedule_text(barber)
    sent = await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())

    # ✅ /cancel uchun aynan shu jadval xabarining id sini saqlab qo'yamiz
    await state.update_data(schedule_msg_id=sent.message_id)


# 2) Ish kunlarini o'zgartirishni so'rash
@router.callback_query(F.data == "barber_change_days")
async def ask_work_days(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    await state.set_state(BarberPage.waiting_for_work_days)

    # ✅ /cancel aynan shu xabarni (edit qilinganini) jadvalga qaytarishi uchun
    await state.update_data(schedule_msg_id=callback.message.message_id)

    await callback.answer()
    await callback.message.edit_text(
        "<b>📅 Yangi ish kunlaringizni kiriting:</b>\n\n"
        "Namuna:\n"
        "Dushanba-Juma\n"
        "Dushanba-Shanba\n"
        "Har kuni\n"
        "Dushanba, Chorshanba, Juma\n\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML",
    )


# 3) Ish vaqtini o'zgartirishni so'rash
@router.callback_query(F.data == "barber_change_time")
async def ask_work_time(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    await state.set_state(BarberPage.waiting_for_work_time)

    await state.update_data(schedule_msg_id=callback.message.message_id)

    await callback.answer()
    await callback.message.edit_text(
        "<b>⏰ Yangi ish vaqtingizni kiriting:</b>\n\n"
        "Format: <code>09:00-18:00</code>\n\n"
        "Namuna:\n"
        "09:00-18:00\n"
        "10:00-20:00\n"
        "08:30-17:30\n\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML",
    )


# 4) Tanaffus vaqtini o'zgartirishni so'rash
@router.callback_query(F.data == "barber_change_break")
async def ask_break_time(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    await state.set_state(BarberPage.waiting_for_break_time)

    await state.update_data(schedule_msg_id=callback.message.message_id)

    await callback.answer()
    await callback.message.edit_text(
        "<b>⏸️ Yangi tanaffus vaqtingizni kiriting:</b>\n\n"
        "Format: <code>13:00-14:00</code>\n\n"
        "Namuna:\n"
        "12:00-13:00\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML",
    )


# ✅ Bitta universal /cancel (faqat BarberPage state'larida ishlaydi)
@router.message(
    F.text == "/cancel",
    StateFilter(
        BarberPage.waiting_for_work_days,
        BarberPage.waiting_for_work_time,
        BarberPage.waiting_for_break_time,
    ),
)
async def cancel_to_schedule_exact(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    data = await state.get_data()
    schedule_msg_id = data.get("schedule_msg_id")

    # ✅ Avval jadvalni chiqaramiz (faqat bitta natija)
    await _show_schedule_exact(
        bot=message.bot,
        chat_id=message.chat.id,
        barber=barber,
        message_id=schedule_msg_id,
    )

    # ✅ Keyin FSM to'liq tozalanadi
    await state.clear()

    # ✅ Qo'shimcha xabar chiqmasligi uchun /cancel ni o'chirib yuboramiz (muvaffaqiyatsiz bo'lsa ham jim)
    try:
        await message.delete()
    except Exception:
        pass


# 6) Save - tanaffus vaqti
@router.message(BarberPage.waiting_for_break_time)
async def save_break_time(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    breakdown_text = message.text.strip().lower()
    if breakdown_text in {"yo'q", "yoq"}:
        new_value = None
    else:
        parsed = _parse_time_range(message.text.strip())
        if not parsed:
            await message.answer(
                "❌ Noto'g'ri format.\n\n"
                "To'g'ri format: <code>13:00-14:00</code>\n"
                "Agar tanaffus bo'lmasa: <code>yo'q</code>",
                parse_mode="HTML",
            )
            return
        start, end = parsed
        new_value = f"{start}-{end}"

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(breakdown=new_value)
        )
        await session.commit()
        refreshed = await session.get(Barbers, barber.id)

    await state.clear()

    display_value = new_value if new_value else "yo'q"
    await message.answer(
        f"✅ <b>Tanaffus vaqti yangilandi!</b>\n\n"
        f"Yangi tanaffus vaqti: <b>{display_value}</b>",
        parse_mode="HTML",
    )

    text = await _render_schedule_text(refreshed or barber)
    await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())


# 8) Save - ish kunlari
@router.message(BarberPage.waiting_for_work_days)
async def save_work_days(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    work_days = message.text.strip()
    if len(work_days) < 3:
        await message.answer("❌ Ish kunlari juda qisqa. Qaytadan kiriting:")
        return

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_days=work_days)
        )
        await session.commit()
        refreshed = await session.get(Barbers, barber.id)

    await state.clear()

    await message.answer(
        f"✅ <b>Ish kunlari yangilandi!</b>\n\n"
        f"Yangi ish kunlari: <b>{work_days}</b>",
        parse_mode="HTML",
    )

    text = await _render_schedule_text(refreshed or barber)
    await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())


# 10) Save - ish vaqti
@router.message(BarberPage.waiting_for_work_time)
async def save_work_time(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    work_time_text = message.text.strip()
    parsed = _parse_time_range(work_time_text)
    if not parsed:
        await message.answer(
            "❌ Noto'g'ri format.\n\nTo'g'ri format: <code>09:00-18:00</code>",
            parse_mode="HTML",
        )
        return

    start, end = parsed
    new_value = f"{start}-{end}"

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(work_time=new_value)
        )
        await session.commit()
        refreshed = await session.get(Barbers, barber.id)

    await state.clear()

    await message.answer(
        f"✅ <b>Ish vaqti yangilandi!</b>\n\n"
        f"Yangi ish vaqti: <b>{new_value}</b>",
        parse_mode="HTML",
    )

    text = await _render_schedule_text(refreshed or barber)
    await message.answer(text, parse_mode="HTML", reply_markup=get_schedule_keyboard())
