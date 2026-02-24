# superadmins/order_notify_handlers.py
import logging
from datetime import datetime

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from sql.db import async_session
from sql.db_barber_inbox import inbox_mark_seen_by_order
from sql.models import BarberOrderInbox, Order

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 1
SCOPE_TODAY = "today"
SCOPE_FUTURE = "future"
NOTIFY_PAGE_CB = "barber_notify_page"
NOTIFY_SCOPE_CB = "barber_notify_scope"


def _fmt_date(value) -> str:
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def _fmt_time(value) -> str:
    return value.strftime("%H:%M") if hasattr(value, "strftime") else str(value)


def _scope_title(scope: str) -> str:
    if scope == SCOPE_FUTURE:
        return "⏳ Kelgusi navbatlar"
    return "📅 Bugungi navbatlar"


def _clamp_page(page: int, total_pages: int) -> int:
    if total_pages < 1:
        return 1
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


def _realtime_text(order: Order) -> str:
    if not getattr(order, "date", None) or not getattr(order, "time", None):
        return "⏱ <b>Real-time:</b> Noma'lum"

    now = datetime.now()
    order_dt = datetime.combine(order.date, order.time)
    diff_seconds = int((order_dt - now).total_seconds())

    if diff_seconds >= 0:
        minutes_left = diff_seconds // 60
        if order.date == now.date():
            return f"⏱ <b>Real-time:</b> {minutes_left} daqiqadan keyin"
        days_left = (order.date - now.date()).days
        return f"⏱ <b>Real-time:</b> {days_left} kundan keyin"

    minutes_passed = abs(diff_seconds) // 60
    return f"⏱ <b>Real-time:</b> {minutes_passed} daqiqa oldin o'tgan"


def _order_detail_text(
    order: Order,
    username: str,
    scope: str,
    page: int,
    total_pages: int,
    today_count: int,
    future_count: int,
) -> str:
    return (
        "📌 <b>Buyurtma batafsil</b>\n\n"
        f"📅 <b>Bugungi:</b> {today_count} | ⏳ <b>Kelgusi:</b> {future_count}\n"
        f"📂 <b>Bo'lim:</b> {_scope_title(scope)}\n"
        f"📄 <b>Sahifa:</b> {page}/{total_pages}\n\n"
        f"👤 <b>Username:</b> {username}\n"
        f"👤 <b>Fullname:</b> {order.fullname}\n"
        f"📱 <b>Phone:</b> {order.phonenumber}\n"
        f"💈 <b>Service:</b> {order.service_id}\n"
        f"🧑‍🎤 <b>Barber name:</b> {order.barber_id_name}\n"
        f"📅 <b>Navbat sanasi:</b> {_fmt_date(order.date)}\n"
        f"🕒 <b>Navbat vaqti:</b> {_fmt_time(order.time)}\n"
        f"{_realtime_text(order)}\n"
        f"🗓 <b>Yaratilgan sana:</b> {_fmt_date(order.booked_date)}\n"
        f"⏱ <b>Yaratilgan vaqt:</b> {_fmt_time(order.booked_time)}\n"
    )


async def _resolve_username(bot, user_id: int) -> str:
    username = "username yo'q"
    try:
        chat = await bot.get_chat(int(user_id))
        if getattr(chat, "username", None):
            username = f"@{chat.username}"
    except Exception:
        username = "username yo'q"
    return username


async def _fetch_notify_orders(barber_tg_id: int):
    today = datetime.now().date()
    async with async_session() as session:
        result = await session.execute(
            select(Order)
            .join(BarberOrderInbox, BarberOrderInbox.order_id == Order.id)
            .where(
                BarberOrderInbox.barber_tg_id == barber_tg_id,
                BarberOrderInbox.is_delivered.is_(True),
                Order.date >= today,
            )
            .order_by(Order.date.asc(), Order.time.asc(), Order.id.asc())
        )
        raw_orders = result.scalars().all()

    unique_orders = []
    seen_ids = set()
    for order in raw_orders:
        if order.id in seen_ids:
            continue
        seen_ids.add(order.id)
        unique_orders.append(order)

    today_orders = [order for order in unique_orders if order.date == today]
    future_orders = [order for order in unique_orders if order.date > today]
    return today_orders, future_orders


def _build_notify_keyboard(
    *,
    scope: str,
    page: int,
    total_pages: int,
    order_id: int | None,
    today_count: int,
    future_count: int,
) -> InlineKeyboardMarkup:
    today_total_pages = max(1, (today_count + PAGE_SIZE - 1) // PAGE_SIZE)
    prev_scope = scope
    prev_page = page - 1 if page > 1 else 1
    if scope == SCOPE_FUTURE and page == 1 and today_count > 0:
        prev_scope = SCOPE_TODAY
        prev_page = today_total_pages

    next_scope = scope
    next_page = page + 1 if page < total_pages else total_pages
    if scope == SCOPE_TODAY and page == total_pages and future_count > 0:
        next_scope = SCOPE_FUTURE
        next_page = 1

    rows = [
        [
            InlineKeyboardButton(
                text=f"📅 Bugungi ({today_count})",
                callback_data=f"{NOTIFY_SCOPE_CB}:{SCOPE_TODAY}:1",
            ),
            InlineKeyboardButton(
                text=f"⏳ Kelgusi ({future_count})",
                callback_data=f"{NOTIFY_SCOPE_CB}:{SCOPE_FUTURE}:1",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"{NOTIFY_PAGE_CB}:{prev_scope}:{prev_page}",
            ),
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data=f"{NOTIFY_PAGE_CB}:{scope}:{page}",
            ),
            InlineKeyboardButton(
                text="Keyingi ➡️",
                callback_data=f"{NOTIFY_PAGE_CB}:{next_scope}:{next_page}",
            ),
        ],
    ]

    if order_id is not None:
        rows.append(
            [InlineKeyboardButton(text="❌ Yopish", callback_data=f"barber_order_close:{order_id}")]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _parse_scope_page(data: str, prefix: str):
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != prefix:
        return None, 1

    scope = parts[1]
    if scope not in (SCOPE_TODAY, SCOPE_FUTURE):
        return None, 1

    try:
        page = int(parts[2])
    except (TypeError, ValueError):
        page = 1

    return scope, max(page, 1)


async def _upsert_callback_message(
    callback: types.CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
):
    if not callback.message:
        return

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


def _pick_scope_and_page(
    *,
    today_orders,
    future_orders,
    selected_order_id: int | None,
    requested_scope: str | None,
    requested_page: int,
):
    if requested_scope in (SCOPE_TODAY, SCOPE_FUTURE):
        scope = requested_scope
    else:
        scope = None
        if selected_order_id is not None:
            if any(order.id == selected_order_id for order in today_orders):
                scope = SCOPE_TODAY
            elif any(order.id == selected_order_id for order in future_orders):
                scope = SCOPE_FUTURE
        if scope is None:
            scope = SCOPE_TODAY if today_orders else SCOPE_FUTURE

    scoped_orders = today_orders if scope == SCOPE_TODAY else future_orders
    if not scoped_orders:
        if scope == SCOPE_TODAY and future_orders:
            scope = SCOPE_FUTURE
            scoped_orders = future_orders
        elif scope == SCOPE_FUTURE and today_orders:
            scope = SCOPE_TODAY
            scoped_orders = today_orders

    total_pages = max(1, (len(scoped_orders) + PAGE_SIZE - 1) // PAGE_SIZE)

    if selected_order_id is not None and requested_scope is None:
        idx = next(
            (index for index, order in enumerate(scoped_orders) if order.id == selected_order_id),
            None,
        )
        if idx is not None:
            requested_page = idx // PAGE_SIZE + 1

    page = _clamp_page(requested_page, total_pages)
    return scope, scoped_orders, page, total_pages


async def _render_notify_page(
    callback: types.CallbackQuery,
    *,
    barber_tg_id: int,
    selected_order_id: int | None = None,
    requested_scope: str | None = None,
    requested_page: int = 1,
):
    today_orders, future_orders = await _fetch_notify_orders(barber_tg_id)
    today_count = len(today_orders)
    future_count = len(future_orders)

    if not today_orders and not future_orders:
        empty_markup = _build_notify_keyboard(
            scope=SCOPE_TODAY,
            page=1,
            total_pages=1,
            order_id=selected_order_id,
            today_count=0,
            future_count=0,
        )
        text = "📭 <b>Bugungi va kelgusi navbat bildirishnomalari mavjud emas.</b>"
        await _upsert_callback_message(callback, text=text, reply_markup=empty_markup)
        return

    scope, scoped_orders, page, total_pages = _pick_scope_and_page(
        today_orders=today_orders,
        future_orders=future_orders,
        selected_order_id=selected_order_id,
        requested_scope=requested_scope,
        requested_page=requested_page,
    )

    if not scoped_orders:
        text = "📭 <b>Tanlangan bo'limda navbat topilmadi.</b>"
        markup = _build_notify_keyboard(
            scope=scope,
            page=1,
            total_pages=1,
            order_id=selected_order_id,
            today_count=today_count,
            future_count=future_count,
        )
        await _upsert_callback_message(callback, text=text, reply_markup=markup)
        return

    start = (page - 1) * PAGE_SIZE
    current_order = scoped_orders[start]
    username = await _resolve_username(callback.bot, int(current_order.user_id))

    await inbox_mark_seen_by_order(order_id=current_order.id, barber_tg_id=barber_tg_id)

    text = _order_detail_text(
        current_order,
        username,
        scope,
        page,
        total_pages,
        today_count,
        future_count,
    )
    markup = _build_notify_keyboard(
        scope=scope,
        page=page,
        total_pages=total_pages,
        order_id=current_order.id,
        today_count=today_count,
        future_count=future_count,
    )

    await _upsert_callback_message(callback, text=text, reply_markup=markup)


@router.callback_query(F.data.startswith("barber_order_detail:"))
async def barber_order_detail(callback: types.CallbackQuery):
    try:
        order_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri buyurtma.", show_alert=True)
        return

    await _render_notify_page(
        callback,
        barber_tg_id=callback.from_user.id,
        selected_order_id=order_id,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{NOTIFY_PAGE_CB}:"))
async def barber_notify_page(callback: types.CallbackQuery):
    scope, page = _parse_scope_page(callback.data or "", NOTIFY_PAGE_CB)
    if scope is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    await _render_notify_page(
        callback,
        barber_tg_id=callback.from_user.id,
        requested_scope=scope,
        requested_page=page,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{NOTIFY_SCOPE_CB}:"))
async def barber_notify_scope(callback: types.CallbackQuery):
    scope, page = _parse_scope_page(callback.data or "", NOTIFY_SCOPE_CB)
    if scope is None:
        await callback.answer("Noto'g'ri bo'lim.", show_alert=True)
        return

    await _render_notify_page(
        callback,
        barber_tg_id=callback.from_user.id,
        requested_scope=scope,
        requested_page=page,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("barber_order_close:"))
async def barber_order_close(callback: types.CallbackQuery):
    try:
        order_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri buyurtma.", show_alert=True)
        return

    barber_tg_id = callback.from_user.id
    await inbox_mark_seen_by_order(order_id=order_id, barber_tg_id=barber_tg_id)

    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_text("✅ Yopildi")
        except Exception:
            pass

    await callback.answer("Yopildi ✅")
