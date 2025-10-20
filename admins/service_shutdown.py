from aiogram import Router, types, F
from sqlalchemy import select
from sql.db import async_session
from sql.models import Services
from .admin_buttons import markup

router = Router()

# 🧾 Barcha servislarni button ko‘rinishida chiqarish
@router.message(F.text == "💈 Servisni o'chirish")
async def list_services_for_delete(message: types.Message):
    async with async_session() as session:
        result = await session.execute(select(Services))
        services = result.scalars().all()

    if not services:
        return await message.answer("📭 Hozircha hech qanday xizmat mavjud emas.")

    # Har bir xizmat uchun alohida tugma yaratamiz
    buttons = [
        [types.InlineKeyboardButton(text=f"💈 {srv.name} — {srv.price} so‘m", callback_data=f"delete_service:{srv.id}")]
        for srv in services
    ]

    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🗑 O‘chirmoqchi bo‘lgan xizmatni tanlang:", reply_markup=markup_inline)


# 🗑 Xizmatni o‘chirish callback handleri
@router.callback_query(F.data.startswith("delete_service:"))
async def delete_service_callback(callback: types.CallbackQuery):
    service_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        service = await session.get(Services, service_id)
        if not service:
            return await callback.answer("❌ Xizmat topilmadi!", show_alert=True)

        name = service.name
        await session.delete(service)
        await session.commit()

    await callback.answer(f"✅ '{name}' xizmati o‘chirildi!", show_alert=True)

    # Xabarni yangilaymiz (interaktivlik uchun)
    async with async_session() as session:
        result = await session.execute(select(Services))
        services = result.scalars().all()

    if not services:
        return await callback.message.edit_text("📭 Barcha xizmatlar o‘chirildi.", reply_markup=None)

    # Qolgan xizmatlar ro‘yxatini qayta chiqarish
    buttons = [
        [types.InlineKeyboardButton(text=f"💈 {srv.name} — {srv.price} so‘m", callback_data=f"delete_service:{srv.id}")]
        for srv in services
    ]
    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text("🗑 O‘chirmoqchi bo‘lgan xizmatni tanlang:", reply_markup=markup_inline)
