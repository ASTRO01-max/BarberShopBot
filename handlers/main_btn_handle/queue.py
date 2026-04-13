# handlers/main_btn_handle/queue.py
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import case, func, select

from sql.db import async_session
from sql.models import Order

from .common import CANCEL_ORDERS_PER_PAGE, _format_dt, _prepare_order_cards

router = Router()

QUEUE_EMPTY_TEXT = "🛒 Navbatlar mavjud emas."
QUEUE_CALLBACK_ALL_ORDERS = "queue_show_all_orders"
QUEUE_CALLBACK_BACK_TO_QUEUE = "queue_back_to_queue"

QUEUE_ALL_NEXT_PAGE_CB = "queue_all_next_page"
QUEUE_ALL_PREV_PAGE_CB = "queue_all_prev_page"
QUEUE_ALL_PAGE_CB = "queue_all_page"
QUEUE_ALL_OPEN_ORDER_CB = "queue_all_open_order"
QUEUE_ALL_BACK_TO_LIST_CB = "queue_all_back_to_list"
QUEUE_ALL_SEARCH_MENU_CB = "queue_all_search_menu"

QUEUE_SEARCH_PHONE_CB = "queue_search_phone"
QUEUE_SEARCH_DATE_CB = "queue_search_date"
QUEUE_SEARCH_WEEKDAY_CB = "queue_search_weekday"
QUEUE_SEARCH_MENU_BACK_CB = "queue_search_menu_back"
QUEUE_SEARCH_BACK_TO_MENU_CB = "queue_search_back_to_menu"
QUEUE_SEARCH_NEXT_PAGE_CB = "queue_search_next_page"
QUEUE_SEARCH_PREV_PAGE_CB = "queue_search_prev_page"
QUEUE_SEARCH_PAGE_CB = "queue_search_page"
QUEUE_SEARCH_OPEN_ORDER_CB = "queue_search_open_order"
QUEUE_SEARCH_DETAIL_BACK_CB = "queue_search_detail_back"

QUEUE_CURRENT_PAGE_STATE_KEY = "queue_current_page"
QUEUE_ALL_CURRENT_PAGE_STATE_KEY = "queue_all_current_page"
QUEUE_ALL_TOTAL_ORDERS_STATE_KEY = "queue_all_total_orders"
QUEUE_ALL_VIEW_STATE_KEY = "queue_all_view"
QUEUE_SEARCH_TYPE_STATE_KEY = "queue_search_type"
QUEUE_SEARCH_VALUE_STATE_KEY = "queue_search_value"
QUEUE_SEARCH_PAGE_STATE_KEY = "queue_search_page"
QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY = "queue_search_total_orders"

QUEUE_ALL_ORDERS_PER_PAGE = 1

QUEUE_VIEW_ALL_LIST = "queue_view_all_list"
QUEUE_VIEW_ALL_DETAIL = "queue_view_all_detail"
QUEUE_VIEW_SEARCH_MENU = "queue_view_search_menu"
QUEUE_VIEW_SEARCH_RESULTS = "queue_view_search_results"
QUEUE_VIEW_SEARCH_DETAIL = "queue_view_search_detail"

SEARCH_TYPE_PHONE = "phone"
SEARCH_TYPE_DATE = "date"
SEARCH_TYPE_WEEKDAY = "weekday"

QUEUE_STATUS_TODAY = "🟢 Bugungi"
QUEUE_STATUS_UPCOMING = "🔵 Kelayotgan"
QUEUE_STATUS_COMPLETED = "⚫ Yakunlangan"

QUEUE_WEEKDAY_TO_DOW = {
    "yakshanba": 0,
    "dushanba": 1,
    "seshanba": 2,
    "chorshanba": 3,
    "payshanba": 4,
    "juma": 5,
    "shanba": 6,
}
QUEUE_DOW_TO_WEEKDAY = {value: key.capitalize() for key, value in QUEUE_WEEKDAY_TO_DOW.items()}


class QueueSearchState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_date = State()
    waiting_for_weekday = State()


def _parse_page(value: str):
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return max(page, 0)


def _parse_order_and_page(data: str, prefix: str):
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != prefix:
        return None, None

    try:
        order_id = int(parts[1])
        page = int(parts[2])
    except (TypeError, ValueError):
        return None, None

    return order_id, max(page, 0)


def _parse_one_based_page(value: str):
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return max(page, 1)


def _parse_one_based_order_and_page(data: str, prefix: str):
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != prefix:
        return None, None

    try:
        order_id = int(parts[1])
        page = int(parts[2])
    except (TypeError, ValueError):
        return None, None

    return order_id, max(page, 1)


def _parse_prefixed_one_based_page(data: str, prefix: str):
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != prefix:
        return None
    return _parse_one_based_page(parts[1])


def _clamp_queue_all_page(page: int, total_pages: int) -> int:
    if total_pages < 1:
        return 1
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


def _normalize_weekday_token(value: str) -> str:
    return " ".join((value or "").strip().lower().split()).replace("’", "'")


def _parse_search_date(value: str):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _search_type_label(search_type: str) -> str:
    labels = {
        SEARCH_TYPE_PHONE: "Telefon",
        SEARCH_TYPE_DATE: "Sana",
        SEARCH_TYPE_WEEKDAY: "Kun",
    }
    return labels.get(search_type, "Qidiruv")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _queue_status_label(order_date, today=None) -> str:
    today = today or datetime.now().date()
    if order_date == today:
        return QUEUE_STATUS_TODAY
    if order_date > today:
        return QUEUE_STATUS_UPCOMING
    return QUEUE_STATUS_COMPLETED


def _decorate_queue_cards_with_status(orders, order_cards):
    today = datetime.now().date()
    cards = []
    for order, card in zip(orders, order_cards):
        prepared = dict(card)
        prepared["status"] = _queue_status_label(order.date, today=today)
        cards.append(prepared)
    return cards


def _format_queue_button_text(card) -> str:
    status = card.get("status", "").strip()
    status_part = f" | {status}" if status else ""
    label = f"📅 {card['date']} | ⏰ {card['time']} | 💈 {card['barber']}{status_part}"
    return label if len(label) <= 64 else f"{label[:61]}..."


def _queue_order_detail_text(order, card) -> str:
    status = card.get("status") or _queue_status_label(order.date)
    return (
        "📌 <b>Navbat tafsiloti:</b>\n\n"
        # f"🆔 <b>ID:</b> {order.id}\n"
        f"👤 <b>Mijoz:</b> {order.fullname}\n"
        f"📞 <b>Tel:</b> {order.phonenumber}\n"
        f"💈 <b>Barber:</b> {card['barber']}\n"
        f"✂️ <b>Xizmat:</b> {card['service']}\n"
        f"🗓 <b>Sana:</b> {card['date']}\n"
        f"⏰ <b>Vaqt:</b> {card['time']}\n"
        f"🗓 <b>Navbat olingan sana:</b> {_format_dt(order.booked_date, '%Y-%m-%d')}\n"
        f"⏰ <b>Navbat olingan vaqt:</b> {_format_dt(order.booked_time, '%H:%M')}\n"
        f"🚦 <b>Status:</b> {status}"
    )


def _queue_all_list_text(page: int, total_pages: int, total_orders: int) -> str:
    return (
        "📋 <b>Navbatlar ro'yxati</b>\n\n"
        f"{QUEUE_STATUS_TODAY} | {QUEUE_STATUS_UPCOMING} | {QUEUE_STATUS_COMPLETED}\n\n"
        f"📄 <b>Sahifa:</b> {page}/{total_pages}\n"
        f"📦 <b>Jami navbatlar:</b> {total_orders}"
    )


def _queue_search_results_text(
    page: int,
    total_pages: int,
    total_orders: int,
    search_type: str,
    search_value: str,
) -> str:
    return (
        "🔎 <b>Qidiruv natijalari</b>\n\n"
        f"🧭 <b>Tur:</b> {_search_type_label(search_type)}\n"
        f"🔍 <b>So'rov:</b> {search_value}\n"
        f"📄 <b>Sahifa:</b> {page}/{total_pages}\n"
        f"📦 <b>Jami:</b> {total_orders}\n"
    )


def _queue_search_menu_text() -> str:
    return (
        "🔎 <b>Qidiruv bo'limi</b>\n\n"
        "Qidirish turini tanlang:"
    )


def _queue_search_prompt_text(search_type: str) -> str:
    prompts = {
        SEARCH_TYPE_PHONE: "Telefon raqamini kiriting:\n\nMasalan: +998998071134",
        SEARCH_TYPE_DATE: "Sanani kiriting:\n\nMasalan: 2025-03-10",
        SEARCH_TYPE_WEEKDAY: "Kunni kiriting:\n\nMasalan: Dushanba",
    }
    return prompts.get(search_type, "Qidiruv qiymatini kiriting:")


def _queue_search_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Qidiruv bo'limiga qaytish",
                    callback_data=QUEUE_SEARCH_BACK_TO_MENU_CB,
                )
            ]
        ]
    )


def _queue_search_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1️⃣ Telefon bo‘yicha", callback_data=QUEUE_SEARCH_PHONE_CB)],
            [InlineKeyboardButton(text="2️⃣ Sana bo‘yicha", callback_data=QUEUE_SEARCH_DATE_CB)],
            [InlineKeyboardButton(text="3️⃣ Kun bo‘yicha", callback_data=QUEUE_SEARCH_WEEKDAY_CB)],
            [InlineKeyboardButton(text="🔙 Ortga", callback_data=QUEUE_SEARCH_MENU_BACK_CB)],
        ]
    )


def _queue_pagination_row(
    page: int,
    total_pages: int,
    prev_cb: str,
    page_cb: str,
    next_cb: str,
):
    prev_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages
    return [
        InlineKeyboardButton(
            text="⬅️ Oldingi",
            callback_data=f"{prev_cb}:{prev_page}",
        ),
        InlineKeyboardButton(
            text=f"📄 {page}/{total_pages}",
            callback_data=f"{page_cb}:{page}",
        ),
        InlineKeyboardButton(
            text="➡️ Keyingi",
            callback_data=f"{next_cb}:{next_page}",
        ),
    ]


async def _safe_edit_queue_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    parse_mode: str | None = None,
):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def _fetch_past_order_by_id(user_id: int, order_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(
                Order.id == order_id,
                Order.user_id == user_id,
            )
        )
        return result.scalars().first()


async def _fetch_paginated_past_orders(user_id: int, page: int, extra_filters=None):
    today = datetime.now().date()
    filters = [Order.user_id == user_id]
    if extra_filters:
        filters.extend(extra_filters)

    status_rank = case(
        (Order.date == today, 0),
        (Order.date > today, 1),
        else_=2,
    )

    async with async_session() as session:
        total_orders = await session.scalar(select(func.count(Order.id)).where(*filters))
        total_orders = int(total_orders or 0)
        total_pages = (total_orders + QUEUE_ALL_ORDERS_PER_PAGE - 1) // QUEUE_ALL_ORDERS_PER_PAGE
        total_pages = max(total_pages, 1)
        page = _clamp_queue_all_page(page, total_pages)
        offset = (page - 1) * QUEUE_ALL_ORDERS_PER_PAGE

        result = await session.execute(
            select(Order)
            .where(*filters)
            .order_by(status_rank.asc(), Order.date.asc(), Order.time.asc(), Order.id.asc())
            .offset(offset)
            .limit(QUEUE_ALL_ORDERS_PER_PAGE)
        )
        orders = result.scalars().all()

    return orders, total_orders, total_pages, page


def _build_search_filters(search_type: str, raw_value: str):
    value = (raw_value or "").strip()
    if not value:
        return None, None, "❗ Qidiruv qiymati bo'sh."

    if search_type == SEARCH_TYPE_PHONE:
        escaped = _escape_like(value)
        return [Order.phonenumber.ilike(f"%{escaped}%", escape="\\")], value, None

    if search_type == SEARCH_TYPE_DATE:
        parsed = _parse_search_date(value)
        if parsed is None:
            return None, None, "❗ Sana formatini to'g'ri kiriting: YYYY-MM-DD"
        return [Order.date == parsed], parsed.strftime("%Y-%m-%d"), None

    if search_type == SEARCH_TYPE_WEEKDAY:
        normalized = _normalize_weekday_token(value)
        dow = QUEUE_WEEKDAY_TO_DOW.get(normalized)
        if dow is None:
            return None, None, "❗ Kunni to'g'ri kiriting (masalan: Dushanba)."
        return [func.extract("dow", Order.date) == dow], QUEUE_DOW_TO_WEEKDAY[dow], None

    return None, None, "❗ Noma'lum qidiruv turi."


def _matches_search(order, search_type: str, search_value: str) -> bool:
    if search_type == SEARCH_TYPE_PHONE:
        return (search_value or "").strip() in str(order.phonenumber or "")

    if search_type == SEARCH_TYPE_DATE:
        parsed = _parse_search_date(search_value)
        return parsed is not None and order.date == parsed

    if search_type == SEARCH_TYPE_WEEKDAY:
        normalized = _normalize_weekday_token(search_value)
        dow = QUEUE_WEEKDAY_TO_DOW.get(normalized)
        if dow is None or not hasattr(order.date, "weekday"):
            return False
        order_dow = (order.date.weekday() + 1) % 7
        return order_dow == dow

    return False


def _queue_empty_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Barcha navbatlarni ko'rish",
                    callback_data=QUEUE_CALLBACK_ALL_ORDERS,
                )
            ]
        ]
    )


def _prepare_queue_order_cards(orders):
    cards = []
    for order in orders:
        cards.append(
            {
                # "id": order.id,
                "fullname": order.fullname,
                "phonenumber": order.phonenumber,
                "service_id": order.service_id,
                "barber_id_name": order.barber_id_name,
                "date": _format_dt(order.date, "%Y-%m-%d"),
                "time": _format_dt(order.time, "%H:%M"),
                "booked_date": _format_dt(order.booked_date, "%Y-%m-%d"),
                "booked_time": _format_dt(order.booked_time, "%H:%M"),
            }
        )
    return cards


async def _fetch_queue_orders(user_id: int):
    today = datetime.now().date()
    async with async_session() as session:
        result = await session.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.date >= today)
            .order_by(Order.date.asc(), Order.time.asc(), Order.id.asc())
        )
        return result.scalars().all()


def _queue_page_text(order_cards, page: int, today_count: int, future_count: int) -> str:
    start = page * CANCEL_ORDERS_PER_PAGE
    end = start + CANCEL_ORDERS_PER_PAGE
    sliced = order_cards[start:end]
    if not sliced:
        return QUEUE_EMPTY_TEXT

    current = sliced[0]
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

    return (
        "🗂 *Navbatlar bo'limi*\n"
        f"📅 Bugungi navbatlar: {today_count}\n"
        f"⏳ Kelgusi navbatlar: {future_count}\n\n"
        # "🗂 *Navbat tafsiloti:*\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        # f"🆔 ID: {current['id']}\n\n"
        f"👤 Mijoz: {current['fullname']}\n"
        f"📞 Tel: {current['phonenumber']}\n"
        f"🧾 Xizmat ID: {current['service_id']}\n"
        f"💈 Barber: {current['barber_id_name']}\n"
        f"📅 Sana: {current['date']}\n"
        f"⏰ Vaqt: {current['time']}\n"
        f"🗓️ Buyurtma sanasi: {current['booked_date']}\n"
        f"🕒 Buyurtma vaqti: {current['booked_time']}\n"
    )


def _queue_page_markup(order_cards, page: int) -> InlineKeyboardMarkup:
    start = page * CANCEL_ORDERS_PER_PAGE
    end = start + CANCEL_ORDERS_PER_PAGE
    sliced = order_cards[start:end]
    if not sliced:
        return _queue_empty_markup()

    current = sliced[0]
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

    rows = []
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"queue_prev:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="➡️ Keyingi",
                callback_data=f"queue_next:{page + 1}",
            )
        )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Navbatni o'chirish",
                callback_data=f"queue_pick:{page}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="📁 Barcha navbatlarni ko'rish",
                callback_data=QUEUE_CALLBACK_ALL_ORDERS,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_queue_all_orders_keyboard(
    page: int,
    total_pages: int,
    orders=None,
    order_cards=None,
) -> InlineKeyboardMarkup:
    rows = []

    rows.append(
        _queue_pagination_row(
            page=page,
            total_pages=total_pages,
            prev_cb=QUEUE_ALL_PREV_PAGE_CB,
            page_cb=QUEUE_ALL_PAGE_CB,
            next_cb=QUEUE_ALL_NEXT_PAGE_CB,
        )
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Qidirish tugmasi",
                callback_data=QUEUE_ALL_SEARCH_MENU_CB,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Navbatlar bo'limiga qaytish",
                callback_data=QUEUE_CALLBACK_BACK_TO_QUEUE,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_queue_search_results_keyboard(
    page: int,
    total_pages: int,
    orders=None,
    order_cards=None,
) -> InlineKeyboardMarkup:
    rows = []

    rows.append(
        _queue_pagination_row(
            page=page,
            total_pages=total_pages,
            prev_cb=QUEUE_SEARCH_PREV_PAGE_CB,
            page_cb=QUEUE_SEARCH_PAGE_CB,
            next_cb=QUEUE_SEARCH_NEXT_PAGE_CB,
        )
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Qidiruv bo'limiga qaytish",
                callback_data=QUEUE_SEARCH_BACK_TO_MENU_CB,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_queue_detail_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Ortga",
                    callback_data=callback_data,
                )
            ]
        ]
    )


async def _get_queue_all_orders_page(user_id: int, page: int):
    try:
        orders, total_orders, total_pages, page = await _fetch_paginated_past_orders(
            user_id=user_id,
            page=page,
        )
    except Exception:
        return "❗ Navbatlar olishda xatolik yuz berdi.", _build_queue_all_orders_keyboard(1, 1), 0, 1

    if not orders:
        return "📂 Navbatlar topilmadi.", _build_queue_all_orders_keyboard(page, total_pages), total_orders, page

    order_cards = await _prepare_order_cards(orders)
    order_cards = _decorate_queue_cards_with_status(orders, order_cards)
    current_order = orders[0]
    current_card = order_cards[0]
    response = (
        _queue_all_list_text(
            page=page,
            total_pages=total_pages,
            total_orders=total_orders,
        )
        + "\n\n"
        + _queue_order_detail_text(current_order, current_card)
    )
    markup = _build_queue_all_orders_keyboard(page, total_pages, orders, order_cards)
    return response, markup, total_orders, page


async def _get_queue_search_results_page(
    user_id: int,
    page: int,
    search_type: str,
    search_value: str,
):
    filters, normalized_value, error = _build_search_filters(search_type, search_value)
    if error:
        return error, _build_queue_search_results_keyboard(1, 1), 0, 1

    try:
        orders, total_orders, total_pages, page = await _fetch_paginated_past_orders(
            user_id=user_id,
            page=page,
            extra_filters=filters,
        )
    except Exception:
        return "❗ Navbatlar olishda xatolik yuz berdi.", _build_queue_search_results_keyboard(1, 1), 0, 1

    if not orders:
        text = (
            "📂 Qidiruv bo'yicha navbatlar topilmadi.\n\n"
            f"🧭 Tur: {_search_type_label(search_type)}\n"
            f"🔍 So'rov: {normalized_value}"
        )
        return text, _build_queue_search_results_keyboard(page, total_pages), total_orders, page

    order_cards = await _prepare_order_cards(orders)
    order_cards = _decorate_queue_cards_with_status(orders, order_cards)
    current_order = orders[0]
    current_card = order_cards[0]
    text = (
        _queue_search_results_text(
            page=page,
            total_pages=total_pages,
            total_orders=total_orders,
            search_type=search_type,
            search_value=normalized_value,
        )
        + "\n\n"
        + _queue_order_detail_text(current_order, current_card)
    )
    markup = _build_queue_search_results_keyboard(page, total_pages, orders, order_cards)
    return text, markup, total_orders, page


def _fallback_order_card(order):
    barber_name = (getattr(order, "barber_id_name", "") or "").strip() or str(order.barber_id)
    return {
        "barber": barber_name,
        "service": str(order.service_id),
        "date": _format_dt(order.date, "%Y-%m-%d"),
        "time": _format_dt(order.time, "%H:%M"),
        "status": _queue_status_label(order.date),
    }


async def _render_queue_search_results_callback(
    callback: CallbackQuery,
    state: FSMContext,
    page: int,
):
    data = await state.get_data()
    search_type = data.get(QUEUE_SEARCH_TYPE_STATE_KEY)
    search_value = data.get(QUEUE_SEARCH_VALUE_STATE_KEY)
    if not search_type or not search_value:
        await callback.answer("Qidiruvni qayta boshlang.", show_alert=True)
        return False

    response, markup, total_orders, page = await _get_queue_search_results_page(
        callback.from_user.id,
        page=page,
        search_type=search_type,
        search_value=search_value,
    )
    await _safe_edit_queue_message(
        callback.message,
        text=response,
        reply_markup=markup,
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_SEARCH_PAGE_STATE_KEY: page,
            QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_RESULTS,
        }
    )
    return True


async def _build_queue_page_text_and_markup(user_id: int, page: int):
    orders = await _fetch_queue_orders(user_id)
    if not orders:
        return QUEUE_EMPTY_TEXT, _queue_empty_markup(), 0, []

    order_cards = _prepare_queue_order_cards(orders)
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))

    today = datetime.now().date()
    today_count = sum(1 for order in orders if order.date == today)
    future_count = sum(1 for order in orders if order.date > today)

    text = _queue_page_text(order_cards, page, today_count, future_count)
    markup = _queue_page_markup(order_cards, page)
    return text, markup, page, order_cards


async def _render_queue_page(callback: CallbackQuery, state: FSMContext, page: int):
    text, markup, page, order_cards = await _build_queue_page_text_and_markup(
        callback.from_user.id,
        page=page,
    )

    if order_cards:
        await _safe_edit_queue_message(
            callback.message,
            text=text,
            reply_markup=markup,
            parse_mode="Markdown",
        )
    else:
        await _safe_edit_queue_message(
            callback.message,
            text=text,
            reply_markup=markup,
        )

    await state.update_data(**{QUEUE_CURRENT_PAGE_STATE_KEY: page})


@router.message(F.text.in_(["рџ—‚Navbatlar", "рџ—‚ Navbatlar", "🗂Navbatlar", "🗂 Navbatlar", "Navbatlar"]))
async def show_queue_orders(message: Message, state: FSMContext):
    text, markup, page, order_cards = await _build_queue_page_text_and_markup(
        message.from_user.id,
        page=0,
    )

    if order_cards:
        await message.answer(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)

    await state.update_data(**{QUEUE_CURRENT_PAGE_STATE_KEY: page})


@router.callback_query(F.data == QUEUE_CALLBACK_ALL_ORDERS)
async def show_queue_all_orders(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    page = 1
    response, markup, total_orders, page = await _get_queue_all_orders_page(
        callback.from_user.id,
        page,
    )
    await _safe_edit_queue_message(
        callback.message,
        text=response,
        reply_markup=markup,
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_ALL_LIST,
            QUEUE_SEARCH_PAGE_STATE_KEY: 1,
            QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY: 0,
        }
    )
    await callback.answer()


@router.callback_query(F.data.startswith((f"{QUEUE_ALL_NEXT_PAGE_CB}:", f"{QUEUE_ALL_PREV_PAGE_CB}:")))
async def paginate_queue_all_orders(callback: CallbackQuery, state: FSMContext):
    page = _parse_prefixed_one_based_page(
        callback.data or "",
        (callback.data or "").split(":")[0] if ":" in (callback.data or "") else "",
    )
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    response, markup, total_orders, page = await _get_queue_all_orders_page(
        callback.from_user.id,
        page,
    )
    await _safe_edit_queue_message(
        callback.message,
        text=response,
        reply_markup=markup,
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_ALL_LIST,
        }
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_ALL_PAGE_CB}:"))
async def queue_all_page_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_ALL_OPEN_ORDER_CB}:"))
async def show_queue_all_order_detail(callback: CallbackQuery, state: FSMContext):
    order_id, page = _parse_one_based_order_and_page(callback.data, QUEUE_ALL_OPEN_ORDER_CB)
    if order_id is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    order = await _fetch_past_order_by_id(callback.from_user.id, order_id)
    if not order:
        await callback.answer("Navbat topilmadi.", show_alert=True)
        return

    order_cards = await _prepare_order_cards([order])
    card = order_cards[0] if order_cards else _fallback_order_card(order)

    await _safe_edit_queue_message(
        callback.message,
        text=_queue_order_detail_text(order, card),
        reply_markup=_build_queue_detail_back_keyboard(f"{QUEUE_ALL_BACK_TO_LIST_CB}:{page}"),
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_ALL_DETAIL,
        }
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_ALL_BACK_TO_LIST_CB}:"))
async def back_to_all_orders_list(callback: CallbackQuery, state: FSMContext):
    page = _parse_prefixed_one_based_page(callback.data, QUEUE_ALL_BACK_TO_LIST_CB)
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    response, markup, total_orders, page = await _get_queue_all_orders_page(
        callback.from_user.id,
        page=page,
    )
    await _safe_edit_queue_message(
        callback.message,
        text=response,
        reply_markup=markup,
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_ALL_LIST,
        }
    )
    await callback.answer()


@router.callback_query(F.data == QUEUE_ALL_SEARCH_MENU_CB)
async def show_queue_search_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_search_menu_text(),
        reply_markup=_queue_search_menu_keyboard(),
        parse_mode="HTML",
    )
    await state.update_data(**{QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_MENU})
    await callback.answer()


@router.callback_query(F.data == QUEUE_SEARCH_MENU_BACK_CB)
async def back_to_all_orders_from_search_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    current_page = data.get(QUEUE_ALL_CURRENT_PAGE_STATE_KEY, 1)
    page = current_page if isinstance(current_page, int) and current_page > 0 else 1

    response, markup, total_orders, page = await _get_queue_all_orders_page(
        callback.from_user.id,
        page=page,
    )
    await _safe_edit_queue_message(
        callback.message,
        text=response,
        reply_markup=markup,
        parse_mode="HTML",
    )
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_ALL_LIST,
        }
    )
    await callback.answer()


@router.callback_query(F.data == QUEUE_SEARCH_BACK_TO_MENU_CB)
async def back_to_queue_search_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_search_menu_text(),
        reply_markup=_queue_search_menu_keyboard(),
        parse_mode="HTML",
    )
    await state.update_data(**{QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_MENU})
    await callback.answer()


@router.callback_query(F.data == QUEUE_SEARCH_PHONE_CB)
async def start_queue_phone_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_PHONE})
    await state.set_state(QueueSearchState.waiting_for_phone)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_search_prompt_text(SEARCH_TYPE_PHONE),
        reply_markup=_queue_search_prompt_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == QUEUE_SEARCH_DATE_CB)
async def start_queue_date_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_DATE})
    await state.set_state(QueueSearchState.waiting_for_date)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_search_prompt_text(SEARCH_TYPE_DATE),
        reply_markup=_queue_search_prompt_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == QUEUE_SEARCH_WEEKDAY_CB)
async def start_queue_weekday_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_WEEKDAY})
    await state.set_state(QueueSearchState.waiting_for_weekday)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_search_prompt_text(SEARCH_TYPE_WEEKDAY),
        reply_markup=_queue_search_prompt_keyboard(),
    )
    await callback.answer()


@router.message(QueueSearchState.waiting_for_phone)
async def queue_search_phone_value(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Telefon raqamini kiriting.")
        return

    await state.update_data(
        **{
            QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_PHONE,
            QUEUE_SEARCH_VALUE_STATE_KEY: query,
        }
    )
    response, markup, total_orders, page = await _get_queue_search_results_page(
        message.from_user.id,
        page=1,
        search_type=SEARCH_TYPE_PHONE,
        search_value=query,
    )
    await state.set_state(None)
    await message.answer(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        **{
            QUEUE_SEARCH_PAGE_STATE_KEY: page,
            QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_RESULTS,
        }
    )


@router.message(QueueSearchState.waiting_for_date)
async def queue_search_date_value(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if _parse_search_date(query) is None:
        await message.answer("Sana formatini to'g'ri kiriting: YYYY-MM-DD")
        return

    await state.update_data(
        **{
            QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_DATE,
            QUEUE_SEARCH_VALUE_STATE_KEY: query,
        }
    )
    response, markup, total_orders, page = await _get_queue_search_results_page(
        message.from_user.id,
        page=1,
        search_type=SEARCH_TYPE_DATE,
        search_value=query,
    )
    await state.set_state(None)
    await message.answer(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        **{
            QUEUE_SEARCH_PAGE_STATE_KEY: page,
            QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_RESULTS,
        }
    )


@router.message(QueueSearchState.waiting_for_weekday)
async def queue_search_weekday_value(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if _normalize_weekday_token(query) not in QUEUE_WEEKDAY_TO_DOW:
        await message.answer("Kunni to'g'ri kiriting (masalan: Dushanba).")
        return

    await state.update_data(
        **{
            QUEUE_SEARCH_TYPE_STATE_KEY: SEARCH_TYPE_WEEKDAY,
            QUEUE_SEARCH_VALUE_STATE_KEY: query,
        }
    )
    response, markup, total_orders, page = await _get_queue_search_results_page(
        message.from_user.id,
        page=1,
        search_type=SEARCH_TYPE_WEEKDAY,
        search_value=query,
    )
    await state.set_state(None)
    await message.answer(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        **{
            QUEUE_SEARCH_PAGE_STATE_KEY: page,
            QUEUE_SEARCH_TOTAL_ORDERS_STATE_KEY: total_orders,
            QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_RESULTS,
        }
    )


@router.callback_query(
    F.data.startswith((f"{QUEUE_SEARCH_NEXT_PAGE_CB}:", f"{QUEUE_SEARCH_PREV_PAGE_CB}:"))
)
async def paginate_queue_search_results(callback: CallbackQuery, state: FSMContext):
    page = _parse_prefixed_one_based_page(
        callback.data or "",
        (callback.data or "").split(":")[0] if ":" in (callback.data or "") else "",
    )
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    rendered = await _render_queue_search_results_callback(callback, state, page=page)
    if rendered:
        await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_SEARCH_PAGE_CB}:"))
async def queue_search_page_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_SEARCH_OPEN_ORDER_CB}:"))
async def show_queue_search_order_detail(callback: CallbackQuery, state: FSMContext):
    order_id, page = _parse_one_based_order_and_page(callback.data, QUEUE_SEARCH_OPEN_ORDER_CB)
    if order_id is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    order = await _fetch_past_order_by_id(callback.from_user.id, order_id)
    if not order:
        await callback.answer("Navbat topilmadi.", show_alert=True)
        return

    data = await state.get_data()
    search_type = data.get(QUEUE_SEARCH_TYPE_STATE_KEY)
    search_value = data.get(QUEUE_SEARCH_VALUE_STATE_KEY)
    if not search_type or not search_value or not _matches_search(order, search_type, search_value):
        await callback.answer("Qidiruv natijasi yangilangan.", show_alert=True)
        return

    order_cards = await _prepare_order_cards([order])
    card = order_cards[0] if order_cards else _fallback_order_card(order)
    await _safe_edit_queue_message(
        callback.message,
        text=_queue_order_detail_text(order, card),
        reply_markup=_build_queue_detail_back_keyboard(f"{QUEUE_SEARCH_DETAIL_BACK_CB}:{page}"),
        parse_mode="HTML",
    )
    await state.update_data(**{QUEUE_ALL_VIEW_STATE_KEY: QUEUE_VIEW_SEARCH_DETAIL})
    await callback.answer()


@router.callback_query(F.data.startswith(f"{QUEUE_SEARCH_DETAIL_BACK_CB}:"))
async def back_to_queue_search_results(callback: CallbackQuery, state: FSMContext):
    page = _parse_prefixed_one_based_page(callback.data, QUEUE_SEARCH_DETAIL_BACK_CB)
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    rendered = await _render_queue_search_results_callback(callback, state, page=page)
    if rendered:
        await callback.answer()


@router.callback_query(F.data == QUEUE_CALLBACK_BACK_TO_QUEUE)
async def back_to_queue_from_all_orders(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    page = data.get(QUEUE_CURRENT_PAGE_STATE_KEY, 0)
    await _render_queue_page(callback, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith(("queue_next:", "queue_prev:")))
async def paginate_queue_orders(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    page = _parse_page(parts[1])
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    await _render_queue_page(callback, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith("queue_pick:"))
async def pick_queue_order_for_delete(callback: CallbackQuery):
    order_id, page = _parse_order_and_page(callback.data, "queue_pick")
    if order_id is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    today = datetime.now().date()
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("Bu navbat allaqachon o'chirilgan.", show_alert=True)
            return

        if order.user_id != callback.from_user.id:
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return

        if order.date < today:
            await callback.answer("Bu navbat faol emas.", show_alert=True)
            return

        await callback.message.edit_text(
            "❓ Quyidagi navbatni o'chirmoqchimisiz?\n\n"
            f"📅 Sana: {_format_dt(order.date, '%Y-%m-%d')}\n"
            f"⏰ Vaqt: {_format_dt(order.time, '%H:%M')}\n"
            f"🧾 Xizmat: {order.service_id}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ O'chirishni tasdiqlash",
                            callback_data=f"queue_confirm:{order.id}:{page}",
                        )
                    ],
                    [InlineKeyboardButton(text="🔙 Ortga", callback_data=f"queue_page:{page}")],
                ]
            ),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("queue_page:"))
async def back_to_queue_page(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 2:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    page = _parse_page(parts[1])
    if page is None:
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    await _render_queue_page(callback, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith("queue_confirm:"))
async def delete_queue_order(callback: CallbackQuery, state: FSMContext):
    order_id, page = _parse_order_and_page(callback.data, "queue_confirm")
    if order_id is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    today = datetime.now().date()
    deleted = False

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("Bu navbat allaqachon o'chirilgan.", show_alert=True)
        elif order.user_id != callback.from_user.id:
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return
        elif order.date < today:
            await callback.answer("Bu navbat faol emas.", show_alert=True)
        else:
            await session.delete(order)
            await session.commit()
            deleted = True

    if deleted:
        await callback.answer("✅ Navbat muvaffaqiyatli o'chirildi.")

    await _render_queue_page(callback, state, page)
