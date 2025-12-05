# admins/barbers_shutdown.py
from aiogram import Router, types, F
from sqlalchemy import select
from sql.db import async_session
from sql.models import Barbers
from .admin_buttons import markup

router = Router()

# 🧾 Barcha barberlarni button ko‘rinishida chiqarish
@router.message(F.text == "💈 Barberni o'cirish")
async def list_barbers_for_delete(message: types.Message):
    async with async_session() as session:
        result = await session.execute(select(Barbers))
        barbers = result.scalars().all()

    if not barbers:
        return await message.answer("📭 Hozircha hech qanday barber mavjud emas.")

    # Har bir barber uchun alohida tugma
    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"💈 {barber.barber_first_name} {barber.barber_last_name} — 📞 {barber.phone or 'N/A'}",
                callback_data=f"delete_barber:{barber.id}"
            )
        ]
        for barber in barbers
    ]

    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🗑 O‘chirmoqchi bo‘lgan barberni tanlang:", reply_markup=markup_inline)


# 🗑 Barberni o‘chirish callback handleri
@router.callback_query(F.data.startswith("delete_barber:"))
async def delete_barber_callback(callback: types.CallbackQuery):
    barber_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        barber = await session.get(Barbers, barber_id)
        if not barber:
            return await callback.answer("❌ Barber topilmadi!", show_alert=True)

        name = barber.barber_first_name
        last_name = barber.barber_last_name
        await session.delete(barber)
        await session.commit()

    await callback.answer(f"✅ '{name}' '{last_name}' barber o‘chirildi!", show_alert=True)

    # 🔄 Qolgan barberlarni yangilab chiqarish
    async with async_session() as session:
        result = await session.execute(select(Barbers))
        barbers = result.scalars().all()

    if not barbers:
        return await callback.message.edit_text("📭 Barcha barberlar o‘chirildi.", reply_markup=None)

    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"💈 {barber.barber_first_name} {barber.barber_last_name} — 📞 {barber.phone or 'N/A'}",
                callback_data=f"delete_barber:{barber.id}"
            )
        ]
        for barber in barbers
    ]
    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text("🗑 O‘chirmoqchi bo‘lgan barberni tanlang:", reply_markup=markup_inline)
