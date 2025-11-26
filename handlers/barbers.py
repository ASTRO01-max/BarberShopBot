from aiogram import types
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Barbers
from keyboards.booking_keyboards import back_button


async def show_barbers(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(Barbers))
        barbers = result.scalars().all()

    if not barbers:
        await callback.message.edit_text(
            "⚠️ Hozircha ustalar mavjud emas.",
            reply_markup=back_button()
        )
        return

    text = "💈 <b>Bizning ustalar ro'yxati:</b>\n\n"
    for b in barbers:
        text += (
            f"💈 <b>{b.barber_first_name} {b.barber_last_name}</b>\n"
            f"💼 <i>Tajribasi:</i> {b.experience}\n"
            f"📅 <i>Ish kunlari:</i> {b.work_days}\n"
            f"📞 <i>Telefon:</i> <code>{b.phone}</code>\n"
            "───────────────\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_button(),
        parse_mode="HTML"
    )
