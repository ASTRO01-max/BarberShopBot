# admins/order_list.py
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order, Services, Barbers
from sqlalchemy import func

router = Router()
CHECK_ORDERS_PER_PAGE = 1

CHECK_ORDERS_CB = "orders:check"
CHECK_PAGE_CB = "orders_page"
CHECK_JUMP5_CB = "orders_jump5"
CHECK_JUMP10_CB = "orders_jump10"
CHECK_GOTO_CB = "orders_goto"
CHECK_SEARCH_MODE_CB = "orders_search_mode"
CHECK_BACK_CB = "orders_back_to_pagination"
BACK_TO_LIST_CB = "orders_back_to_list"
EDIT_DELETE_CB = "orders_delete"


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _safe_edit_message_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _prepare_order_rows(orders):
    if not orders:
        return []

    service_ids = {_to_int(o.service_id) for o in orders}
    service_ids.discard(None)
    barber_ids = {_to_int(o.barber_id) for o in orders}
    barber_ids.discard(None)

    services_by_id = {}
    barbers_by_id = {}
    async with async_session() as session:
        if service_ids:
            result = await session.execute(select(Services).where(Services.id.in_(service_ids)))
            services_by_id = {s.id: s for s in result.scalars().all()}
        if barber_ids:
            result = await session.execute(select(Barbers).where(Barbers.id.in_(barber_ids)))
            barbers_by_id = {b.id: b for b in result.scalars().all()}

    rows = []
    for order in orders:
        service_id = _to_int(order.service_id)
        service_name = (
            services_by_id[service_id].name
            if service_id is not None and service_id in services_by_id
            else str(order.service_id)
        )

        barber_name = (getattr(order, "barber_id_name", "") or "").strip()
        if not barber_name:
            barber_id = _to_int(order.barber_id)
            if barber_id is not None and barber_id in barbers_by_id:
                barber = barbers_by_id[barber_id]
                barber_name = " ".join(
                    part for part in [barber.barber_first_name, barber.barber_last_name] if part
                ).strip()
                barber_name = barber_name or str(order.barber_id)
            else:
                barber_name = str(order.barber_id)

        rows.append(
            {
                "id": getattr(order, "id", ""),
                "user_id": getattr(order, "user_id", ""),
                "fullname": getattr(order, "fullname", "") or "",
                "phonenumber": getattr(order, "phonenumber", "") or "",
                "service_id": getattr(order, "service_id", ""),
                "barber": barber_name,
                "barber_id": getattr(order, "barber_id", ""),
                "service": service_name,
                "date": order.date.strftime("%Y-%m-%d") if hasattr(order.date, "strftime") else str(order.date),
                "time": order.time.strftime("%H:%M") if hasattr(order.time, "strftime") else str(order.time),
                "booked_date": order.booked_date.strftime("%Y-%m-%d") if hasattr(order.booked_date, "strftime") else str(order.booked_date),
                "booked_time": order.booked_time.strftime("%H:%M") if hasattr(order.booked_time, "strftime") else str(order.booked_time),
                "status": getattr(order, "status", None),
            }
        )

    return rows


def _clamp_page(page: int, total_pages: int) -> int:
    if total_pages < 1:
        return 1
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


def _page_window(page: int, total_pages: int, window: int = 20):
    if total_pages <= 50:
        return list(range(1, total_pages + 1))
    start = max(1, page - (window // 2))
    end = min(total_pages, start + window - 1)
    if end - start + 1 < window:
        start = max(1, end - window + 1)
    return list(range(start, end + 1))


async def _clear_orders_pagination_state(state: FSMContext):
    keys_to_remove = {
        "orders_current_page",
        "orders_total_orders",
        "orders_total_pages",
        "orders_search_mode",
        "check_current_page",
        "check_total_orders",
        "check_total_pages",
        "check_search_mode",
    }
    data = await state.get_data()
    for key in keys_to_remove:
        data.pop(key, None)
    await state.set_data(data)


def _build_check_orders_keyboard(
    page: int,
    total_pages: int,
    search_mode: bool = False,
    order_id: int | None = None,
):
    delete_callback = f"{EDIT_DELETE_CB}:{order_id}" if order_id is not None else BACK_TO_LIST_CB
    search_callback = CHECK_BACK_CB if search_mode else CHECK_SEARCH_MODE_CB

    rows = [
        [
            InlineKeyboardButton(text="🔍 Qidirish", callback_data=search_callback),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=delete_callback),
        ]
    ]

    if total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{CHECK_PAGE_CB}:{page - 1}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"{CHECK_PAGE_CB}:{page + 1}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ 10", callback_data=f"{CHECK_JUMP10_CB}:{page - 10}"),
                InlineKeyboardButton(text="⬅️ 5", callback_data=f"{CHECK_JUMP5_CB}:{page - 5}"),
                InlineKeyboardButton(text="5 ➡️", callback_data=f"{CHECK_JUMP5_CB}:{page + 5}"),
                InlineKeyboardButton(text="➡️ 10", callback_data=f"{CHECK_JUMP10_CB}:{page + 10}"),
            ]
        )

        if search_mode:
            pages = _page_window(page, total_pages, window=20)
            page_rows = []
            row = []
            for p in pages:
                row.append(InlineKeyboardButton(text=str(p), callback_data=f"{CHECK_GOTO_CB}:{p}"))
                if len(row) == 10:
                    page_rows.append(row)
                    row = []
            if row:
                page_rows.append(row)
            rows.extend(page_rows)

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def get_check_orders_page(page: int, search_mode: bool = False):
    try:
        async with async_session() as session:
            total_orders = await session.scalar(select(func.count(Order.id)))
            total_orders = int(total_orders or 0)
            if total_orders == 0:
                return "Hozircha navbatlar mavjud emas.", None, 0, 0, 1

            total_pages = (total_orders + CHECK_ORDERS_PER_PAGE - 1) // CHECK_ORDERS_PER_PAGE
            page = _clamp_page(page, total_pages)
            offset = (page - 1) * CHECK_ORDERS_PER_PAGE

            result = await session.execute(
                select(Order)
                .order_by(Order.date.desc(), Order.time.desc())
                .offset(offset)
                .limit(CHECK_ORDERS_PER_PAGE)
            )
            orders = result.scalars().all()
    except Exception:
        return "❌ Navbatlar olishda xatolik yuz berdi.", None, 0, 0, 1

    if not orders:
        return "Hozircha navbatlar mavjud emas.", None, total_orders, total_pages, page

    order_rows = await _prepare_order_rows(orders)
    row = order_rows[0]

    response = (
        f"📋 <b>Navbat: {page} / {total_pages}</b>\n\n"
        f"🆔 <b>ID:</b> {row['id']}\n"
        f"👤 <b>Mijoz:</b> {row['fullname']}\n"
        f"☎️ <b>Tel:</b> {row['phonenumber']}\n"
        f"👤 <b>User ID:</b> {row['user_id']}\n"
        f"💇 <b>Barber:</b> {row['barber']}\n"
        f"🆔 <b>Barber ID:</b> {row['barber_id']}\n"
        f"✂️ <b>Xizmat:</b> {row['service']}\n"
        f"🆔 <b>Xizmat ID:</b> {row['service_id']}\n"
        f"📅 <b>Sana:</b> {row['date']}\n"
        f"⏰ <b>Vaqt:</b> {row['time']}\n"
        f"📅 <b>Navbat olingan sana:</b> {row['booked_date']}\n"
        f"⏰ <b>Navbat olingan vaqt:</b> {row['booked_time']}\n"
    )
    if row.get("status") is not None:
        response += f"📊 <b>Holat:</b> {row['status']}\n"

    order_id = _to_int(row.get("id"))
    markup = _build_check_orders_keyboard(
        page,
        total_pages,
        search_mode=search_mode,
        order_id=order_id,
    )
    return response, markup, total_orders, total_pages, page


@router.message(F.text == "📁 Buyurtmalar ro'yxati")
async def show_all_orders(message: types.Message, state: FSMContext):
    page = 1
    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=False
    )

    msg = await message.answer(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        current_page=current_page,
        current_msg=msg.message_id,
        total_orders=total_orders,
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=False,
        check_current_page=current_page,
        check_total_orders=total_orders,
        check_total_pages=total_pages,
        check_search_mode=False,
    )


@router.callback_query(F.data == CHECK_ORDERS_CB)
async def orders_check_callback(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    page = state_data.get("orders_current_page", state_data.get("check_current_page", 1))
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1

    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=False
    )
    await _safe_edit_message_text(callback.message, response, reply_markup=markup)
    await state.update_data(
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=False,
        check_current_page=current_page,
        check_total_orders=total_orders,
        check_total_pages=total_pages,
        check_search_mode=False,
    )
    await callback.answer()


@router.callback_query(F.data == BACK_TO_LIST_CB)
async def orders_back_to_list_callback(callback: types.CallbackQuery, state: FSMContext):
    page = 1
    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=False
    )
    await _safe_edit_message_text(callback.message, response, reply_markup=markup)
    await _clear_orders_pagination_state(state)
    await state.update_data(
        current_page=current_page,
        total_orders=total_orders,
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=False,
        check_current_page=current_page,
        check_total_orders=total_orders,
        check_total_pages=total_pages,
        check_search_mode=False,
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith(
        (
            f"{CHECK_PAGE_CB}:",
            f"{CHECK_JUMP5_CB}:",
            f"{CHECK_JUMP10_CB}:",
            f"{CHECK_GOTO_CB}:",
            CHECK_SEARCH_MODE_CB,
            CHECK_BACK_CB,
        )
    )
)
async def paginate_check_orders(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data or ""
    state_data = await state.get_data()
    search_mode = bool(state_data.get("orders_search_mode", False))
    page = state_data.get("orders_current_page", state_data.get("check_current_page", 1))

    if data == CHECK_SEARCH_MODE_CB:
        search_mode = True
    elif data == CHECK_BACK_CB:
        search_mode = False
    else:
        try:
            page = int(data.split(":")[1])
        except (IndexError, ValueError):
            page = 1

    if not isinstance(page, int):
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1

    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=search_mode
    )
    await _safe_edit_message_text(callback.message, response, reply_markup=markup)
    await state.update_data(
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=search_mode,
        check_current_page=current_page,
        check_total_orders=total_orders,
        check_total_pages=total_pages,
        check_search_mode=search_mode,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{EDIT_DELETE_CB}:"))
async def delete_order_from_edit_mode(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data or ""
    try:
        order_id = int(data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri buyurtma ID.", show_alert=True)
        return

    deleted = False
    try:
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order is not None:
                await session.delete(order)
                await session.commit()
                deleted = True
    except Exception:
        await callback.answer("❌ Navbatni o'chirishda xatolik yuz berdi.", show_alert=True)
        return

    state_data = await state.get_data()
    page = state_data.get("orders_current_page", state_data.get("check_current_page", 1))
    search_mode = bool(state_data.get("orders_search_mode", False))
    if not isinstance(page, int):
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1

    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=search_mode
    )
    await _safe_edit_message_text(callback.message, response, reply_markup=markup)
    await state.update_data(
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=search_mode,
        check_current_page=current_page,
        check_total_orders=total_orders,
        check_total_pages=total_pages,
        check_search_mode=search_mode,
    )
    if deleted:
        await callback.answer("Navbat o'chirildi ✅", show_alert=False)
        return
    await callback.answer("Buyurtma topilmadi.", show_alert=True)
