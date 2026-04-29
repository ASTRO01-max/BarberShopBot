from datetime import date, timedelta

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, func, select

from sql.db import async_session
from sql.models import Order, Services

from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_back_statistics_keyboard

router = Router()

ORDERS_PAGE_PREFIX = "barberpanel_all_orders_page_"
ORDERS_JUMP5_CB = "barberpanel_orders_jump5"
ORDERS_JUMP10_CB = "barberpanel_orders_jump10"
ORDERS_PER_PAGE = 1


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


def _clamp_page(page: int, total_pages: int) -> int:
    if total_pages < 1:
        return 1
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


async def _safe_edit_message_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


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


def _build_pagination_rows(page: int, total_pages: int):
    rows = []
    if total_pages <= 1:
        return rows

    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"{ORDERS_PAGE_PREFIX}{page - 1}",
            )
        )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text="Keyingi ➡️",
                callback_data=f"{ORDERS_PAGE_PREFIX}{page + 1}",
            )
        )
    if nav_row:
        rows.append(nav_row)

    jump_row = []
    if page > 1:
        jump_row.extend(
            [
                InlineKeyboardButton(
                    text="⬅️ 10",
                    callback_data=f"{ORDERS_JUMP10_CB}:{_clamp_page(page - 10, total_pages)}",
                ),
                InlineKeyboardButton(
                    text="⬅️ 5",
                    callback_data=f"{ORDERS_JUMP5_CB}:{_clamp_page(page - 5, total_pages)}",
                ),
            ]
        )
    if page < total_pages:
        jump_row.extend(
            [
                InlineKeyboardButton(
                    text="5 ➡️",
                    callback_data=f"{ORDERS_JUMP5_CB}:{_clamp_page(page + 5, total_pages)}",
                ),
                InlineKeyboardButton(
                    text="10 ➡️",
                    callback_data=f"{ORDERS_JUMP10_CB}:{_clamp_page(page + 10, total_pages)}",
                ),
            ]
        )
    if jump_row:
        rows.append(jump_row)

    return rows


def _build_orders_text(
    orders,
    service_map,
    barber_name: str,
    page: int,
    total_pages: int,
    page_size: int,
):
    start = (page - 1) * page_size
    end = start + page_size
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
                f"📊 <b>Holat:</b> {status}",
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


def _build_statistics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Barcha buyurtmalar 📂",
                    callback_data=f"{ORDERS_PAGE_PREFIX}1",
                )
            ]
        ]
    )


def _build_orders_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    inline_keyboard = _build_pagination_rows(page, total_pages)
    inline_keyboard.extend(get_back_statistics_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def _parse_orders_page(data: str) -> int | None:
    if not data:
        return None

    try:
        if data.startswith(ORDERS_PAGE_PREFIX):
            return int(data.removeprefix(ORDERS_PAGE_PREFIX))
        if data.startswith(f"{ORDERS_JUMP5_CB}:") or data.startswith(f"{ORDERS_JUMP10_CB}:"):
            return int(data.split(":", 1)[1])
    except ValueError:
        return None

    return None


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

    return (
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
        f"📉 Oxirgi 30 kun: <b>{month_orders or 0}</b>\n"
        f"--------------------"
    )


async def _show_barber_orders(callback: types.CallbackQuery, page: int):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    barber_key = str(barber.id)
    barber_name = " ".join(
        part for part in [barber.barber_first_name, barber.barber_last_name] if part
    ).strip() or str(barber.id)

    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.barber_id == barber_key).order_by(Order.date, Order.time)
        )
        orders = result.scalars().all()

        if not orders:
            await _safe_edit_message_text(
                callback.message,
                "📭 <b>Buyurtmalar topilmadi</b>\n\nHozircha sizga tegishli buyurtmalar mavjud emas.",
                reply_markup=get_back_statistics_keyboard(),
            )
            await callback.answer()
            return

        service_map = {}
        for order in orders:
            if order.service_id not in service_map:
                service_map[order.service_id] = await _get_service_info(session, order.service_id)

    page_size = ORDERS_PER_PAGE
    total_pages = max((len(orders) + page_size - 1) // page_size, 1)
    page = _clamp_page(page, total_pages)

    text = _build_orders_text(orders, service_map, barber_name, page, total_pages, page_size)
    keyboard = _build_orders_keyboard(page, total_pages)

    await _safe_edit_message_text(callback.message, text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text == "📊 O'z statistikam")
async def show_barber_statistics(message: types.Message):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await message.answer("❌ Siz barber sifatida topilmadingiz.")
        return

    text = await _render_barber_statistics_text(barber)
    await message.answer(text, parse_mode="HTML", reply_markup=_build_statistics_keyboard())


@router.callback_query(F.data == "back_statistics")
async def back_to_statistics(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Siz barber sifatida topilmadingiz.", show_alert=True)
        return

    text = await _render_barber_statistics_text(barber)
    await _safe_edit_message_text(
        callback.message,
        text,
        reply_markup=_build_statistics_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith(
        (
            ORDERS_PAGE_PREFIX,
            f"{ORDERS_JUMP5_CB}:",
            f"{ORDERS_JUMP10_CB}:",
        )
    )
)
async def paginate_all_orders(callback: types.CallbackQuery):
    page = _parse_orders_page(callback.data)
    if page is None:
        await callback.answer("❌ Noto'g'ri sahifa.", show_alert=True)
        return

    await _show_barber_orders(callback, page)
