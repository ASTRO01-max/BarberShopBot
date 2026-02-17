#handlers/main_btn_handle/cancel_order.py
from datetime import date, datetime

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from keyboards.main_menu import get_main_menu
from sql.db import async_session
from sql.models import Order

from .common import CANCEL_ORDERS_PER_PAGE, _format_dt

router = Router()

CANCEL_SCOPE_TODAY = "today"
CANCEL_SCOPE_FUTURE = "future"
CANCEL_SCOPE_ALL = "all"

_SCOPE_TO_CODE = {
    CANCEL_SCOPE_TODAY: "t",
    CANCEL_SCOPE_FUTURE: "f",
    CANCEL_SCOPE_ALL: "a",
}
_CODE_TO_SCOPE = {value: key for key, value in _SCOPE_TO_CODE.items()}


def _prepare_cancel_order_cards(orders):
    cards = []
    for o in orders:
        cards.append(
            {
                "id": o.id,
                "user_id": o.user_id,
                "fullname": o.fullname,
                "phonenumber": o.phonenumber,
                "service_id": o.service_id,
                "barber_id_name": o.barber_id_name,
                "date": _format_dt(o.date, "%Y-%m-%d"),
                "time": _format_dt(o.time, "%H:%M"),
                "booked_date": _format_dt(o.booked_date, "%Y-%m-%d"),
                "booked_time": _format_dt(o.booked_time, "%H:%M"),
            }
        )
    return cards


def get_cancel_orders_page(order_cards, page: int):
    start = page * CANCEL_ORDERS_PER_PAGE
    end = start + CANCEL_ORDERS_PER_PAGE
    sliced = order_cards[start:end]
    if not sliced:
        return "🛒 Buyurtmalar topilmadi.", InlineKeyboardMarkup(inline_keyboard=[])

    o = sliced[0]
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

    text = (
        "❌ *Bekor qilinadigan buyurtma:*\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        f"🆔 ID: {o['id']}\n\n"
        f"👤 Mijoz: {o['fullname']}\n"
        f"📞 Tel: {o['phonenumber']}\n"
        f"🧾 Xizmat ID: {o['service_id']}\n"
        f"💈 Barber: {o['barber_id_name']}\n"
        f"📅 Sana: {o['date']}\n"
        f"⏰ Vaqt: {o['time']}\n"
        f"🗓️ Buyurtma sanasi: {o['booked_date']}\n"
        f"🕒 Buyurtma vaqti: {o['booked_time']}\n"
    )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"cancel_prev:{page-1}"))
    if end < len(order_cards):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"cancel_next:{page+1}"))

    nav_row = buttons if buttons else []
    action_row = [
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order:{o['id']}")
    ]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, action_row] if nav_row else [action_row])
    return text, inline_kb


def get_scoped_cancel_orders_page(order_cards, page: int, scope_code: str):
    start = page * CANCEL_ORDERS_PER_PAGE
    end = start + CANCEL_ORDERS_PER_PAGE
    sliced = order_cards[start:end]
    if not sliced:
        return "🛒 Buyurtmalar topilmadi.", InlineKeyboardMarkup(inline_keyboard=[])

    o = sliced[0]
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

    text = (
        "❌ *Bekor qilinadigan buyurtma:*\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        f"🆔 ID: {o['id']}\n\n"
        f"👤 Mijoz: {o['fullname']}\n"
        f"📞 Tel: {o['phonenumber']}\n"
        f"🧾 Xizmat ID: {o['service_id']}\n"
        f"💈 Barber: {o['barber_id_name']}\n"
        f"📅 Sana: {o['date']}\n"
        f"⏰ Vaqt: {o['time']}\n"
        f"🗓️ Buyurtma sanasi: {o['booked_date']}\n"
        f"🕒 Buyurtma vaqti: {o['booked_time']}\n"
    )

    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"cancel_scope_prev:{scope_code}:{page-1}",
            )
        )
    if end < len(order_cards):
        buttons.append(
            InlineKeyboardButton(
                text="➡️ Keyingi",
                callback_data=f"cancel_scope_next:{scope_code}:{page+1}",
            )
        )

    nav_row = buttons if buttons else []
    action_row = [
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"cancel_pick:{scope_code}:{o['id']}:{page}",
        )
    ]
    back_row = [InlineKeyboardButton(text="📋 Bo‘limlar menyusi", callback_data="cancel_back_menu")]

    inline_rows = [nav_row, action_row, back_row] if nav_row else [action_row, back_row]
    inline_kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    return text, inline_kb


def get_order_cancel_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bugungi navbatni o‘chirish", callback_data="cancel_today_orders")],
            [InlineKeyboardButton(text="❌ Kelgusi navbatni o‘chirish", callback_data="cancel_future_orders")],
            [InlineKeyboardButton(text="❌ Barcha navbatlarni ko‘rib o‘chirish", callback_data="cancel_all_orders")],
        ]
    )


def inline_button() -> InlineKeyboardMarkup:
    # Backward compatibility: old calls still work.
    return get_order_cancel_menu_keyboard()


def _current_local_date() -> date:
    # Project bo'ylab datetime.now()/date.today() ishlatiladi.
    return datetime.now().date()


def _scope_title(scope: str) -> str:
    if scope == CANCEL_SCOPE_TODAY:
        return "❌ Bugungi navbatlar"
    if scope == CANCEL_SCOPE_FUTURE:
        return "❌ Kelgusi navbatlar"
    return "❌ Bugungi va kelgusi navbatlar"


def _empty_scope_message(scope: str) -> str:
    if scope == CANCEL_SCOPE_TODAY:
        return "Bugungi navbat topilmadi"
    if scope == CANCEL_SCOPE_FUTURE:
        return "Kutilayotgan navbat topilmadi"
    return "Bekor qilish uchun navbat topilmadi"


def _order_matches_scope(order: Order, scope: str, today: date) -> bool:
    if scope == CANCEL_SCOPE_TODAY:
        return order.date == today
    if scope == CANCEL_SCOPE_FUTURE:
        return order.date > today
    if scope == CANCEL_SCOPE_ALL:
        return order.date >= today
    return False


async def _fetch_cancel_orders_by_scope(user_id: int, scope: str):
    today = _current_local_date()
    async with async_session() as session:
        query = select(Order).where(Order.user_id == user_id)

        if scope == CANCEL_SCOPE_TODAY:
            query = query.where(Order.date == today)
        elif scope == CANCEL_SCOPE_FUTURE:
            query = query.where(Order.date > today)
        elif scope == CANCEL_SCOPE_ALL:
            query = query.where(Order.date >= today)
        else:
            return []

        query = query.order_by(Order.date.asc(), Order.time.asc(), Order.id.asc())
        result = await session.execute(query)
        return result.scalars().all()


def _build_orders_list_keyboard(orders, scope: str) -> InlineKeyboardMarkup:
    scope_code = _SCOPE_TO_CODE[scope]
    rows = []

    for order in orders:
        time_text = _format_dt(order.time, "%H:%M")
        date_text = _format_dt(order.date, "%Y-%m-%d")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🕒 {time_text} | 🧾 {order.service_id} | 📅 {date_text}",
                    callback_data=f"cancel_pick:{scope_code}:{order.id}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="📋 Bo‘limlar menyusi", callback_data="cancel_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_scope_orders(callback: CallbackQuery, scope: str, page: int = 0):
    orders = await _fetch_cancel_orders_by_scope(callback.from_user.id, scope)
    if not orders:
        await callback.message.edit_text(
            _empty_scope_message(scope),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Bo‘limlar menyusi", callback_data="cancel_back_menu")]
                ]
            ),
        )
        return

    order_cards = _prepare_cancel_order_cards(orders)
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))

    scope_code = _SCOPE_TO_CODE[scope]
    body_text, markup = get_scoped_cancel_orders_page(order_cards, page, scope_code)
    await callback.message.edit_text(
        f"{_scope_title(scope)}\n\n{body_text}",
        parse_mode="Markdown",
        reply_markup=markup,
    )


def _parse_scoped_callback(data: str, prefix: str):
    parts = data.split(":")
    if len(parts) not in (3, 4) or parts[0] != prefix:
        return None, None, 0

    scope = _CODE_TO_SCOPE.get(parts[1])
    if scope is None:
        return None, None, 0

    try:
        order_id = int(parts[2])
    except (TypeError, ValueError):
        return None, None, 0

    page = 0
    if len(parts) == 4:
        try:
            page = int(parts[3])
        except (TypeError, ValueError):
            page = 0

    return scope, order_id, max(page, 0)


@router.message(F.text == "❌ Buyurtmani bekor qilish")
@router.message(F.text == "❌Buyurtmani bekor qilish")
async def show_todays_orders_for_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Buyurtmani bekor qilish bo‘limi.\nKerakli bo‘limni tanlang:",
        reply_markup=get_order_cancel_menu_keyboard(),
    )


@router.callback_query(F.data == "cancel_back_menu")
async def show_cancel_menu_from_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "❌ Buyurtmani bekor qilish bo‘limi.\nKerakli bo‘limni tanlang:",
        reply_markup=get_order_cancel_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_today_orders")
async def show_today_orders_for_cancel(callback: CallbackQuery):
    await _render_scope_orders(callback, CANCEL_SCOPE_TODAY)
    await callback.answer()


@router.callback_query(F.data == "cancel_future_orders")
async def show_future_orders_for_cancel(callback: CallbackQuery):
    await _render_scope_orders(callback, CANCEL_SCOPE_FUTURE)
    await callback.answer()


@router.callback_query(F.data == "cancel_all_orders")
async def show_all_active_orders_for_cancel(callback: CallbackQuery):
    await _render_scope_orders(callback, CANCEL_SCOPE_ALL)
    await callback.answer()


@router.callback_query(F.data.startswith(("cancel_scope_next:", "cancel_scope_prev:")))
async def paginate_scoped_cancel_orders(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return

    scope = _CODE_TO_SCOPE.get(parts[1])
    if scope is None:
        await callback.answer("Noto‘g‘ri bo‘lim.", show_alert=True)
        return

    try:
        page = int(parts[2])
    except (TypeError, ValueError):
        await callback.answer("Noto‘g‘ri sahifa.", show_alert=True)
        return

    await _render_scope_orders(callback, scope, page)
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_pick:"))
async def select_order_for_cancel(callback: CallbackQuery):
    scope, order_id, page = _parse_scoped_callback(callback.data, "cancel_pick")
    if scope is None:
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return

    today = _current_local_date()
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("Bu navbat allaqachon o‘chirilgan.", show_alert=True)
            await _render_scope_orders(callback, scope, page)
            return

        if order.user_id != callback.from_user.id:
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return

        if not _order_matches_scope(order, scope, today):
            await callback.answer("Bu navbat tanlangan bo‘limga kirmaydi.", show_alert=True)
            await _render_scope_orders(callback, scope, page)
            return

        scope_code = _SCOPE_TO_CODE[scope]
        await callback.message.edit_text(
            "Quyidagi navbatni bekor qilmoqchimisiz?\n\n"
            f"📅 Sana: {_format_dt(order.date, '%Y-%m-%d')}\n"
            f"⏰ Vaqt: {_format_dt(order.time, '%H:%M')}\n"
            f"🧾 Xizmat: {order.service_id}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Bekor qilish",
                            callback_data=f"cancel_confirm:{scope_code}:{order.id}:{page}",
                        )
                    ],
                    [InlineKeyboardButton(text="🔙 Ortga", callback_data=f"cancel_scope:{scope_code}:{page}")],
                ]
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_scope:"))
async def back_to_scope_orders(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) not in (2, 3):
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return

    scope = _CODE_TO_SCOPE.get(parts[1])
    if scope is None:
        await callback.answer("Noto‘g‘ri bo‘lim.", show_alert=True)
        return

    page = 0
    if len(parts) == 3:
        try:
            page = int(parts[2])
        except (TypeError, ValueError):
            page = 0

    await _render_scope_orders(callback, scope, max(page, 0))
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_confirm:"))
async def cancel_order_with_confirmation(callback: CallbackQuery):
    scope, order_id, page = _parse_scoped_callback(callback.data, "cancel_confirm")
    if scope is None:
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return

    today = _current_local_date()
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("Bu navbat allaqachon o‘chirilgan.", show_alert=True)
            await _render_scope_orders(callback, scope, page)
            return

        if order.user_id != callback.from_user.id:
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return

        if not _order_matches_scope(order, scope, today):
            await callback.answer("Bu navbat tanlangan bo‘limga kirmaydi.", show_alert=True)
            await _render_scope_orders(callback, scope, page)
            return

        await session.delete(order)
        await session.commit()

    await callback.answer("Buyurtma muvaffaqiyatli o‘chirildi ✅")
    await _render_scope_orders(callback, scope, page)


# Eski callbacklarni qo'llab-quvvatlash (backward compatibility)
@router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order_callback(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return await callback.answer("❗ Xatolik: noto‘g‘ri ID.", show_alert=True)

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("❗ Bu buyurtma allaqachon bekor qilingan.", show_alert=True)
            return

        if order.user_id != callback.from_user.id:
            await callback.answer("❗ Bu buyurtma sizga tegishli emas.", show_alert=True)
            return

        await session.delete(order)
        await session.commit()

    await callback.message.edit_text(
        f"✅ Buyurtma bekor qilindi!\n\n"
        f"📅 Sana: {order.date}\n"
        f"⏰ Vaqt: {order.time}"
    )
    await callback.answer("Buyurtma muvaffaqiyatli o‘chirildi ✅")

    await callback.message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )


@router.callback_query(F.data.startswith(("cancel_next", "cancel_prev")))
async def paginate_cancel_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_cards = data.get("cancel_order_cards", [])
    if not order_cards:
        await callback.answer("❗ Buyurtmalar topilmadi", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto‘g‘ri sahifa.", show_alert=True)
        return

    text, markup = get_cancel_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(cancel_current_page=page)
    await callback.answer()
