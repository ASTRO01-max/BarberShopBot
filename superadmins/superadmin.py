#superadmins/superadmin.py
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select

from sql.db import async_session
from sql.models import Barbers
from .panel_presence import touch_barber
from .order_realtime_notify import flush_undelivered_to_barber
from .superadmin_buttons import get_barber_inline_menu, get_barber_menu

router = Router()

async def is_barber(tg_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none() is not None


async def get_barber_by_tg_id(tg_id: int):
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none()


@router.message(Command("barber"))
async def barber_entry(message: types.Message):
    tg_id = message.from_user.id

    if not await is_barber(tg_id):
        return await message.answer(
            "⛔ <b>Ruxsat yo'q</b>\n\n"
            "Siz barber sifatida ro'yxatdan o'tmagansiz.\n"
            "Iltimos, admin bilan bog'laning.",
            parse_mode="HTML"
        )

    touch_barber(tg_id)
    await flush_undelivered_to_barber(message.bot, tg_id)

    barber = await get_barber_by_tg_id(tg_id)

    await message.answer(
        f"👋 <b>Xush kelibsiz, {barber.barber_first_name}!</b>\n"
        f"💈 Barber paneli tayyor.",
        parse_mode="HTML",
        reply_markup=get_barber_menu()
    )
    await message.answer(
        "Tezkor boshqaruv bo'limlari:",
        reply_markup=get_barber_inline_menu(),
    )


@router.callback_query(F.data == "barber_menu")
async def back_to_barber_menu(callback: types.CallbackQuery):
    touch_barber(callback.from_user.id)

    sent = False
    try:
        await callback.message.edit_text(
            "💈 Barber paneli",
            reply_markup=get_barber_inline_menu()
        )
        sent = True
    except Exception:
        # edit qilib bo'lmasa, pastda yangi xabar yuboramiz
        pass

    if not sent:
        await callback.message.answer("💈 Barber paneli", reply_markup=get_barber_inline_menu())

    await callback.answer()
