# superadmins/todays_orders.py
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from sqlalchemy import select, and_
from datetime import date, datetime

from sql.db import async_session
from sql.models import Order, Services
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_todays_orders_keyboard

router = Router()

PAGE_SIZE = 1  # 1 sahifada 1 ta buyurtma (siz so'ragan pagination uchun eng toza variant)


async def _service_name(session, service_id_raw: str) -> str:
    if not service_id_raw:
        return "Noma'lum"
    try:
        service = await session.get(Services, int(service_id_raw))
        if service:
            return service.name
    except Exception:
        pass
    return str(service_id_raw)


def _status_for_time(order_time, today_: date) -> tuple[str, str]:
    now = datetime.now()
    order_dt = datetime.combine(today_, order_time)
    diff = order_dt - now
    minutes_left = int(diff.total_seconds() / 60)

    if diff.total_seconds() < 0:
        return "⏰ O'tgan", ""
    if diff.total_seconds() < 1800:
        return "🔴 Yaqinlashmoqda", f"\n⚠️ <b>{minutes_left} daqiqadan keyin</b>"
    if diff.total_seconds() < 3600:
        return "🟡 Yaqin", f"\n⏰ {minutes_left} daqiqadan keyin"
    return "🟢 Kutilmoqda", ""


async def _get_today_orders(barber_id_str: str):
    today_ = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(
                and_(Order.barber_id == barber_id_str, Order.date == today_)
            ).order_by(Order.time)
        )
        return result.scalars().all()


async def _render_page_to_message(msg: types.Message, barber_id_str: str, page: int):
    today_ = date.today()
    orders = await _get_today_orders(barber_id_str)

    if not orders:
        return await msg.answer(
            "📭 <b>Bugungi buyurtmalar yo'q</b>\n\n"
            "Hozircha bugun uchun navbatlar mavjud emas.",
            parse_mode="HTML",
        )

    total_pages = (len(orders) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))

    start = (page - 1) * PAGE_SIZE
    order = orders[start]  # PAGE_SIZE=1

    async with async_session() as session:
        service_name = await _service_name(session, order.service_id)

    status, time_status = _status_for_time(order.time, today_)

    text = (
        f"📋 <b>Bugungi buyurtmalar</b>\n"
        f"📦 <b>Jami:</b> {len(orders)}\n"
        f"📄 <b>Sahifa:</b> {page}/{total_pages}\n"
        f"--------------------\n"
        f"<b>Navbat</b> {status}\n\n"
        f"👤 <b>Mijoz:</b> {order.fullname}\n"
        f"📞 <b>Telefon:</b> <code>{order.phonenumber}</code>\n"
        f"✂️ <b>Xizmat:</b> {service_name}\n"
        f"⏰ <b>Vaqt:</b> {order.time.strftime('%H:%M')}"
        f"{time_status}\n"
        f"--------------------"
    )

    keyboard = get_todays_orders_keyboard(order_id=order.id, page=page, total_pages=total_pages)

    await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)


async def _edit_page_in_message(msg: types.Message, barber_id_str: str, page: int):
    today_ = date.today()
    orders = await _get_today_orders(barber_id_str)

    if not orders:
        try:
            await msg.edit_text(
                "📭 <b>Bugungi buyurtmalar yo'q</b>\n\n"
                "Hozircha bugun uchun navbatlar mavjud emas.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    total_pages = (len(orders) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))

    start = (page - 1) * PAGE_SIZE
    order = orders[start]

    async with async_session() as session:
        service_name = await _service_name(session, order.service_id)

    status, time_status = _status_for_time(order.time, today_)

    text = (
        f"📋 <b>Bugungi buyurtmalar</b>\n"
        f"📦 <b>Jami:</b> {len(orders)}\n"
        f"📄 <b>Sahifa:</b> {page}/{total_pages}\n"
        f"--------------------\n"
        f"<b>Navbat</b> {status}\n\n"
        f"👤 <b>Mijoz:</b> {order.fullname}\n"
        f"📞 <b>Telefon:</b> <code>{order.phonenumber}</code>\n"
        f"✂️ <b>Xizmat:</b> {service_name}\n"
        f"⏰ <b>Vaqt:</b> {order.time.strftime('%H:%M')}"
        f"{time_status}\n"
        f"--------------------"
    )

    keyboard = get_todays_orders_keyboard(order_id=order.id, page=page, total_pages=total_pages)

    await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


# ✅ FSM holatidan qat'i nazar ishlasin + matn farqi bo'lsa ham ushlasin
@router.message(StateFilter("*"), F.text.startswith("📅 Bugungi buyurtmalar"))
async def show_todays_orders(message: types.Message):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    barber_key = str(barber.id)
    await _render_page_to_message(message, barber_key, page=1)


@router.callback_query(F.data.startswith("todays_orders_page_"))
async def paginate_todays_orders(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    try:
        page = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer("❌ Noto'g'ri sahifa!", show_alert=True)
        return

    barber_key = str(barber.id)
    await _edit_page_in_message(callback.message, barber_key, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("todays_notify_"))
async def notify_client(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer("❌ Noto'g'ri buyurtma!", show_alert=True)
        return

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)
            return

        service_name = await _service_name(session, order.service_id)

    # Mijozga avtomatik xabar
    try:
        await callback.bot.send_message(
            chat_id=order.user_id,
            text=(
                f"🔔 <b>Eslatma!</b>\n\n"
                f"Hurmatli {order.fullname}!\n\n"
                f"Sizning navbatingiz:\n"
                f"📅 <b>Sana:</b> {order.date.strftime('%d.%m.%Y')}\n"
                f"⏰ <b>Vaqt:</b> {order.time.strftime('%H:%M')}\n"
                f"✂️ <b>Xizmat:</b> {service_name}\n\n"
                f"Iltimos, o'z vaqtida keling!"
            ),
            parse_mode="HTML"
        )
        await callback.answer("✅ Xabar yuborildi!", show_alert=True)
    except Exception:
        await callback.answer("❌ Xabar yuborishda xatolik yuz berdi!", show_alert=True)
