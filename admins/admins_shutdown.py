# admins/admins_shutdown.py
from aiogram import Router, types, F
from sqlalchemy import select

from sql.db import async_session
from sql.models import Admins
from .admin_buttons import ADMIN_DEL_CB

router = Router()


@router.callback_query(F.data == ADMIN_DEL_CB)
async def start_delete_admin(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(Admins))
        admins = result.scalars().all()

    if not admins:
        await callback.answer()
        return await callback.message.answer("📭 Hozircha admin mavjud emas.")

    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"👨‍💻 {admin.admin_fullname or admin.tg_id} — {admin.tg_id}",
                callback_data=f"delete_admin:{admin.id}",
            )
        ]
        for admin in admins
    ]

    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(
        "🗑 O'chirmoqchi bo'lgan adminni tanlang:",
        reply_markup=markup_inline,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_admin:"))
async def delete_admin_callback(callback: types.CallbackQuery):
    admin_id = int(callback.data.split(":", 1)[1])

    async with async_session() as session:
        admin = await session.get(Admins, admin_id)
        if not admin:
            return await callback.answer("❌ Admin topilmadi!", show_alert=True)

        name = admin.admin_fullname or str(admin.tg_id)
        await session.delete(admin)
        await session.commit()

    await callback.answer(f"✅ '{name}' admin o'chirildi!", show_alert=True)

    async with async_session() as session:
        result = await session.execute(select(Admins))
        admins = result.scalars().all()

    if not admins:
        return await callback.message.edit_text("📭 Barcha adminlar o'chirildi.", reply_markup=None)

    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"👨‍💻 {adm.admin_fullname or adm.tg_id} — {adm.tg_id}",
                callback_data=f"delete_admin:{adm.id}",
            )
        ]
        for adm in admins
    ]
    markup_inline = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🗑 O'chirmoqchi bo'lgan adminni tanlang:",
        reply_markup=markup_inline,
    )
