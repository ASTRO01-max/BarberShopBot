#superadmins/superadmin.py
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select

from sql.db_barbers_expanded import add_service_to_barber, get_barber_services
from sql.db import async_session
from sql.models import Barbers, Services
from .panel_presence import touch_barber
from .order_realtime_notify import flush_undelivered_to_barber

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
    from .superadmin_buttons import get_barber_menu

    await message.answer(
        f"👋 <b>Xush kelibsiz, {barber.barber_first_name}!</b>\n"
        f"💈 Barber paneli tayyor.",
        parse_mode="HTML",
        reply_markup=get_barber_menu()
    )


@router.callback_query(F.data == "barber_menu")
async def back_to_barber_menu(callback: types.CallbackQuery):
    from .superadmin_buttons import get_barber_menu
    touch_barber(callback.from_user.id)

    sent = False
    try:
        await callback.message.edit_text(
            "💈 Barber paneli",
            reply_markup=get_barber_menu()
        )
        sent = True
    except Exception:
        # edit qilib bo'lmasa, pastda yangi xabar yuboramiz
        pass

    if not sent:
        await callback.message.answer("💈 Barber paneli", reply_markup=get_barber_menu())

    await callback.answer()


@router.message(F.text == "➕ Xizmat kiritish")
async def show_add_service_menu(message: types.Message):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        services = result.scalars().all()

    if not services:
        await message.answer("⚠️ Hozircha xizmatlar mavjud emas.")
        return

    selected_services = await get_barber_services(barber.id)
    from .superadmin_buttons import get_add_service_keyboard

    await message.answer(
        "Quyidagi xizmatlardan o'zingiz bajara oladiganlarini tanlang:",
        reply_markup=get_add_service_keyboard(services, selected_services),
    )


@router.callback_query(F.data.startswith("barber_add_service_"))
async def add_barber_service(callback: types.CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parts = callback.data.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    service_id = int(parts[1])

    async with async_session() as session:
        service = await session.get(Services, service_id)
        if not service:
            await callback.answer("❌ Xizmat topilmadi.", show_alert=True)
            return

        result = await session.execute(select(Services).order_by(Services.id.asc()))
        services = result.scalars().all()

    is_added = await add_service_to_barber(barber.id, service_id)
    selected_services = await get_barber_services(barber.id)

    from .superadmin_buttons import get_add_service_keyboard

    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_add_service_keyboard(services, selected_services)
        )
    except Exception:
        pass

    if is_added:
        await callback.answer("✅ Xizmat muvaffaqiyatli qo'shildi.")
    else:
        await callback.answer("⚠️ Bu xizmat allaqachon qo'shilgan.", show_alert=True)

