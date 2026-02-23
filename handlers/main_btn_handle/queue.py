# handlers/main_btn_handle/queue.py
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

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

QUEUE_CURRENT_PAGE_STATE_KEY = "queue_current_page"
QUEUE_ALL_CURRENT_PAGE_STATE_KEY = "queue_all_current_page"
QUEUE_ALL_TOTAL_ORDERS_STATE_KEY = "queue_all_total_orders"

QUEUE_ALL_ORDERS_PER_PAGE = 1


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


def _clamp_queue_all_page(page: int, total_pages: int) -> int:
    if total_pages < 1:
        return 1
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


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
                "id": order.id,
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
        "🗂 *Navbat tafsiloti:*\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        f"🆔 ID: {current['id']}\n\n"
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
                callback_data=f"queue_pick:{current['id']}:{page}",
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


def _build_queue_all_orders_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    prev_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages

    nav_buttons = [
        InlineKeyboardButton(
            text="⬅️ Oldingi",
            callback_data=f"{QUEUE_ALL_PREV_PAGE_CB}:{prev_page}",
        ),
        InlineKeyboardButton(
            text=f"📄 {page}/{total_pages}",
            callback_data=f"{QUEUE_ALL_PAGE_CB}:{page}",
        ),
        InlineKeyboardButton(
            text="➡️  Keyingi",
            callback_data=f"{QUEUE_ALL_NEXT_PAGE_CB}:{next_page}",
        ),
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons,
            [
                InlineKeyboardButton(
                    text="🔙 Navbatlar bo'limiga qaytish",
                    callback_data=QUEUE_CALLBACK_BACK_TO_QUEUE,
                )
            ],
        ]
    )


async def _get_queue_all_orders_page(page: int):
    try:
        async with async_session() as session:
            total_orders = await session.scalar(select(func.count(Order.id)))
            total_orders = int(total_orders or 0)
            total_pages = (total_orders + QUEUE_ALL_ORDERS_PER_PAGE - 1) // QUEUE_ALL_ORDERS_PER_PAGE
            total_pages = max(total_pages, 1)
            page = _clamp_queue_all_page(page, total_pages)
            offset = (page - 1) * QUEUE_ALL_ORDERS_PER_PAGE

            result = await session.execute(
                select(Order)
                .order_by(Order.date.desc(), Order.time.desc())
                .offset(offset)
                .limit(QUEUE_ALL_ORDERS_PER_PAGE)
            )
            orders = result.scalars().all()
    except Exception:
        return "❗ Navbatlar olishda xatolik yuz berdi.", _build_queue_all_orders_keyboard(1, 1), 0

    if not orders:
        return "📂 Navbatlar topilmadi.", _build_queue_all_orders_keyboard(page, total_pages), total_orders

    order_cards = await _prepare_order_cards(orders)
    response = f"📋 <b>Navbatlar ro'yxati (sahifa {page})</b>\n\n"

    for idx, (order, card) in enumerate(zip(orders, order_cards), start=offset + 1):
        response += (
            f"📌 <b>Navbat {idx}</b>\n"
            f"👤 <b>Mijoz:</b> {order.fullname}\n"
            f"📞 <b>Tel:</b> {order.phonenumber}\n"
            f"💈 <b>Barber:</b> {card['barber']}\n"
            f"✂️ <b>Xizmat:</b> {card['service']}\n"
            f"🗓 <b>Sana:</b> {card['date']}\n"
            f"⏰ <b>Vaqt:</b> {card['time']}\n"
            f"🗓 <b>Navbat olingan sana:</b> {_format_dt(order.booked_date, '%Y-%m-%d')}\n"
            f"⏰ <b>Navbat olingan vaqt:</b> {_format_dt(order.booked_time, '%H:%M')}\n\n"
        )

    return response, _build_queue_all_orders_keyboard(page, total_pages), total_orders


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
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)

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
    page = 1
    response, markup, total_orders = await _get_queue_all_orders_page(page)
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
        }
    )
    await callback.answer()


@router.callback_query(F.data.startswith((f"{QUEUE_ALL_NEXT_PAGE_CB}:", f"{QUEUE_ALL_PREV_PAGE_CB}:")))
async def paginate_queue_all_orders(callback: CallbackQuery, state: FSMContext):
    try:
        page = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri sahifa.", show_alert=True)
        return

    response, markup, total_orders = await _get_queue_all_orders_page(page)
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        **{
            QUEUE_ALL_CURRENT_PAGE_STATE_KEY: page,
            QUEUE_ALL_TOTAL_ORDERS_STATE_KEY: total_orders,
        }
    )
    await callback.answer("⏳ Yangilanmoqda...", show_alert=False)


@router.callback_query(F.data.startswith(f"{QUEUE_ALL_PAGE_CB}:"))
async def queue_all_page_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == QUEUE_CALLBACK_BACK_TO_QUEUE)
async def back_to_queue_from_all_orders(callback: CallbackQuery, state: FSMContext):
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
