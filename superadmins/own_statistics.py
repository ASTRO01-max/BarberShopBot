# superadmins/own_statistics.py
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, and_
from datetime import date, timedelta

from sql.db import async_session
from sql.models import Order, Services
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_back_statistics_keyboard  # ✅ siz qo'shgan tugma

router = Router()

PAGE_SIZE = 5


def _format_date(value):
    return value.strftime("%d.%m.%Y") if value else "-"


def _format_time(value):
    return value.strftime("%H:%M") if value else "-"


def _status_label(order_date):
    today = date.today()
    if order_date < today:
        return "⏱️ O'tgan"
    if order_date > today:
        return "🕒 Kutilmoqda"
    return "✅ Bugun"


async def _get_service_info(session, service_id_raw: str):
    if not service_id_raw:
        return ("Noma'lum", None, None)
    try:
        service = await session.get(Services, int(service_id_raw))
        if service:
            return (service.name, service.price, service.duration)
    except Exception:
        pass
    return (str(service_id_raw), None, None)


def _build_pagination_row(page: int, total_pages: int):
    row = []
    if total_pages <= 1:
        return row
    if page > 1:
        row.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"barberpanel_all_orders_page_{page - 1}"
            )
        )
    if page < total_pages:
        row.append(
            InlineKeyboardButton(
                text="Keyingi ➡️",
                callback_data=f"barberpanel_all_orders_page_{page + 1}"
            )
        )
    return row


def _build_orders_text(orders, service_map, barber_name: str, page: int, total_pages: int):
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_orders = orders[start:end]

    lines = [
        "📂 <b>Barcha buyurtmalar</b>",
        f"👤 <b>Barber:</b> {barber_name}",
        f"📦 <b>Jami:</b> {len(orders)}",
        f"📄 <b>Sahifa:</b> {page}/{total_pages}",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for idx, order in enumerate(page_orders, start=start + 1):
        service_name, price, duration = service_map.get(
            order.service_id, ("Noma'lum", None, None)
        )
        booked_at = f"{_format_date(order.booked_date)} {_format_time(order.booked_time)}"
        service_at = f"{_format_date(order.date)} {_format_time(order.time)}"
        status = _status_label(order.date)

        lines.extend(
            [
                f"🧾 <b>Buyurtma #{idx}</b>",
                f"📅 <b>Buyurtma qilingan:</b> {booked_at}",
                f"🗓️ <b>Xizmat sanasi:</b> {service_at}",
                f"📌 <b>Holat:</b> {status}",
                f"👤 <b>Mijoz:</b> {order.fullname}",
                f"📞 <b>Telefon:</b> <code>{order.phonenumber}</code>",
                f"💈 <b>Xizmat:</b> {service_name}",
            ]
        )
        if price is not None:
            lines.append(f"💵 <b>Narx:</b> {price} so'm")
        if duration:
            lines.append(f"⏱️ <b>Davomiyligi:</b> {duration}")
        lines.extend(
            [
                f"🆔 <b>Buyurtma ID:</b> {order.id}",
                f"👥 <b>Telegram ID:</b> {order.user_id}",
                "━━━━━━━━━━━━━━━━━━",
            ]
        )

    return "\n".join(lines)


async def _render_barber_statistics_text(barber):
    barber_key = str(barber.id)
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    async with async_session() as session:
        total_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.barber_id == barber_key)
        )

        today_orders = await session.scalar(
            select(func.count(Order.id)).where(and_(Order.barber_id == barber_key, Order.date == today))
        )

        pending_orders = await session.scalar(
            select(func.count(Order.id)).where(and_(Order.barber_id == barber_key, Order.date >= today))
        )

        finished_orders = await session.scalar(
            select(func.count(Order.id)).where(and_(Order.barber_id == barber_key, Order.date < today))
        )

        week_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(Order.barber_id == barber_key, Order.date >= week_ago, Order.date <= today)
            )
        )

        month_orders = await session.scalar(
            select(func.count(Order.id)).where(
                and_(Order.barber_id == barber_key, Order.date >= month_ago, Order.date <= today)
            )
        )

        unique_clients = await session.scalar(
            select(func.count(func.distinct(Order.user_id))).where(Order.barber_id == barber_key)
        )

    text = (
        f"📊 <b>Shaxsiy statistika</b>\n"
        f"👤 <b>Barber:</b> {barber.barber_first_name}\n\n"
        f"--------------------\n"
        f"<b>📈 Umumiy ko'rsatkichlar</b>\n"
        f"📦 Jami buyurtmalar: <b>{total_orders or 0}</b>\n"
        f"✅ Yakunlangan: <b>{finished_orders or 0}</b>\n"
        f"⏳ Kutilayotgan: <b>{pending_orders or 0}</b>\n"
        f"👥 Unikal mijozlar: <b>{unique_clients or 0}</b>\n\n"
        f"<b>📅 Vaqt bo'yicha</b>\n"
        f"📅 Bugun: <b>{today_orders or 0}</b>\n"
        f"📆 Oxirgi 7 kun: <b>{week_orders or 0}</b>\n"
        f"📊 Oxirgi 30 kun: <b>{month_orders or 0}</b>\n"
        f"--------------------"
    )
    return text


@router.message(F.text == "📊 O'z statistikam")
async def show_barber_statistics(message: types.Message):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    text = await _render_barber_statistics_text(barber)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Barcha buyurtmalar 📂", callback_data="barberpanel_all_orders_page_1")]
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "back_statistics")
async def back_to_statistics(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    text = await _render_barber_statistics_text(barber)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Barcha buyurtmalar 📂", callback_data="barberpanel_all_orders_page_1")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("barberpanel_all_orders_page_"))
async def paginate_all_orders(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split("_")[-1])
    except Exception:
        return await callback.answer("❌ Noto'g'ri sahifa!", show_alert=True)

    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    barber_key = str(barber.id)
    barber_name = barber.barber_first_name

    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.barber_id == barber_key).order_by(Order.date, Order.time)
        )
        orders = result.scalars().all()

        if not orders:
            await callback.message.edit_text(
                "📭 <b>Buyurtmalar topilmadi</b>\n\n"
                "Hozircha sizga tegishli buyurtmalar mavjud emas.",
                parse_mode="HTML",
                reply_markup=get_back_statistics_keyboard(),  # ✅ baribir qaytish bo'lsin
            )
            await callback.answer()
            return

        service_map = {}
        for order in orders:
            if order.service_id not in service_map:
                service_map[order.service_id] = await _get_service_info(session, order.service_id)

    total_pages = (len(orders) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))

    text = _build_orders_text(orders, service_map, barber_name, page, total_pages)

    # ✅ pagination + "Statistikaga qaytish" ni bitta keyboardga jamlaymiz
    inline_keyboard = []
    pagination_row = _build_pagination_row(page, total_pages)
    if pagination_row:
        inline_keyboard.append(pagination_row)

    # siz superadmin_buttons.py da yaratgan keyboardni aynan shu yerga qo'shamiz
    # get_back_statistics_keyboard() -> InlineKeyboardMarkup, uning ichki inline_keyboard'ini olamiz:
    inline_keyboard.extend(get_back_statistics_keyboard().inline_keyboard)

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()
