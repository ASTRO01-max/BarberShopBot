from aiogram import types
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Services
from keyboards.booking_keyboards import back_button
from utils.emoji_map import SERVICE_EMOJIS

async def show_services(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(Services))
        services = result.scalars().all()

    if not services:
        await callback.message.edit_text(
            "⚠️ Hozircha xizmatlar mavjud emas.",
            reply_markup=back_button()
        )
        return

    text = "💈 <b>Xizmatlar ro'yxati:</b>\n\n"
    for s in services:
        emoji = SERVICE_EMOJIS.get(s.name, "🔹")  # Emoji topilmasa, default ishlaydi
        text += f"{emoji} <i>{s.name}</i>\n💵 {s.price} so'm\n🕒 {s.duration}\n───────────────\n"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_button())
