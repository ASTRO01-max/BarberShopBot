# admins/order_list.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order, Services, Barbers
from sqlalchemy import func

router = Router()
ORDERS_PER_PAGE = 5
CHECK_ORDERS_PER_PAGE = 1


EDIT_ORDERS_TEXT = "📝 Navbatlarni tahrirlash"
CHECK_ORDERS_TEXT = "🔍 Navbatlarni tekshirish"
EDIT_ORDERS_CB = "orders:edit"
CHECK_ORDERS_CB = "orders:check"
CHECK_PAGE_CB = "orders_page"
CHECK_JUMP5_CB = "orders_jump5"
CHECK_JUMP10_CB = "orders_jump10"
CHECK_GOTO_CB = "orders_goto"
CHECK_SEARCH_MODE_CB = "orders_search_mode"
CHECK_BACK_CB = "orders_back_to_pagination"

MODE_VIEW = "view"
MODE_EDIT = "edit"

EDIT_PAGE_CB = "orders_edit_page"
EDIT_JUMP5_CB = "orders_edit_jump5"
EDIT_JUMP10_CB = "orders_edit_jump10"
EDIT_GOTO_CB = "orders_edit_goto"
EDIT_SEARCH_MODE_CB = "orders_edit_search_mode"
EDIT_BACK_CB = "orders_edit_back_to_pagination"
EDIT_DELETE_CB = "orders_delete"


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _mode_callbacks(mode: str):
    if mode == MODE_EDIT:
        return {
            "page": EDIT_PAGE_CB,
            "jump5": EDIT_JUMP5_CB,
            "jump10": EDIT_JUMP10_CB,
            "goto": EDIT_GOTO_CB,
            "search_mode": EDIT_SEARCH_MODE_CB,
            "back": EDIT_BACK_CB,
        }
    return {
        "page": CHECK_PAGE_CB,
        "jump5": CHECK_JUMP5_CB,
        "jump10": CHECK_JUMP10_CB,
        "goto": CHECK_GOTO_CB,
        "search_mode": CHECK_SEARCH_MODE_CB,
        "back": CHECK_BACK_CB,
    }


def _resolve_mode_from_callback(data: str, default_mode: str = MODE_VIEW) -> str:
    if data.startswith(
        (
            f"{EDIT_PAGE_CB}:",
            f"{EDIT_JUMP5_CB}:",
            f"{EDIT_JUMP10_CB}:",
            f"{EDIT_GOTO_CB}:",
            f"{EDIT_DELETE_CB}:",
        )
    ) or data in (EDIT_SEARCH_MODE_CB, EDIT_BACK_CB):
        return MODE_EDIT
    if data.startswith(
        (
            f"{CHECK_PAGE_CB}:",
            f"{CHECK_JUMP5_CB}:",
            f"{CHECK_JUMP10_CB}:",
            f"{CHECK_GOTO_CB}:",
        )
    ) or data in (CHECK_SEARCH_MODE_CB, CHECK_BACK_CB):
        return MODE_VIEW
    return default_mode


def _build_check_orders_keyboard(
    page: int,
    total_pages: int,
    search_mode: bool = False,
    mode: str = MODE_VIEW,
    order_id: int | None = None,
):
    callbacks = _mode_callbacks(mode)

    rows = []


    if total_pages <= 1:
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{callbacks['page']}:{page - 1}")
        )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="➡️  Keyingi", callback_data=f"{callbacks['page']}:{page + 1}")
        )
    if nav_row:
        rows.append(nav_row)

    if not search_mode:
        jump_row = []
        if total_pages > 5 and page > 5:
            jump_row.append(
                InlineKeyboardButton(text="⬅️ 5", callback_data=f"{callbacks['jump5']}:{page - 5}")
            )
        if total_pages > 5 and page + 5 <= total_pages:
            jump_row.append(
                InlineKeyboardButton(text="5 ➡️", callback_data=f"{callbacks['jump5']}:{page + 5}")
            )
        if total_pages > 10 and page > 10:
            jump_row.append(
                InlineKeyboardButton(text="⬅️ 10", callback_data=f"{callbacks['jump10']}:{page - 10}")
            )
        if total_pages > 10 and page + 10 <= total_pages:
            jump_row.append(
                InlineKeyboardButton(text="10 ➡️", callback_data=f"{callbacks['jump10']}:{page + 10}")
            )
        if jump_row:
            rows.append(jump_row)

        rows.append([InlineKeyboardButton(text="🔍", callback_data=callbacks["search_mode"])])

    if mode == MODE_EDIT and order_id is not None:
        rows.append(
            [InlineKeyboardButton(text="❌ O'chirish", callback_data=f"{EDIT_DELETE_CB}:{order_id}")]
        )
        
    if search_mode:
        pages = _page_window(page, total_pages, window=20)
        page_rows = []
        row = []
        for p in pages:
            row.append(InlineKeyboardButton(text=str(p), callback_data=f"{callbacks['goto']}:{p}"))
            if len(row) == 10:
                page_rows.append(row)
                row = []
        if row:
            page_rows.append(row)
        rows.extend(page_rows)
        rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=callbacks["back"])])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def get_check_orders_page(page: int, search_mode: bool = False, mode: str = MODE_VIEW):
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
        response += f"📌 <b>Holat:</b> {row['status']}\n"

    order_id = _to_int(row.get("id")) if mode == MODE_EDIT else None
    markup = _build_check_orders_keyboard(
        page,
        total_pages,
        search_mode=search_mode,
        mode=mode,
        order_id=order_id,
    )
    return response, markup, total_orders, total_pages, page


async def get_orders_page(page: int):
    offset = max(0, page) * ORDERS_PER_PAGE

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .order_by(Order.date.desc(), Order.time.desc())
                .offset(offset)
                .limit(ORDERS_PER_PAGE)
            )
            orders = result.scalars().all()

            total_orders = await session.scalar(select(func.count(Order.id)))
            total_orders = int(total_orders or 0)
    except Exception as e:
        # Log yoki print — developmentda ko'rish
        print("get_orders_page DB error:", repr(e))
        return "❗ Navbatlar olishda xatolik yuz berdi.", None, 0

    if not orders:
        return "📂 Navbatlar topilmadi.", None, total_orders

    order_rows = await _prepare_order_rows(orders)
    response = f"📋 <b>Navbatlar ro'yxati (sahifa {page + 1})</b>\n\n"
    for idx, row in enumerate(order_rows, start=offset + 1):
        response += (
            f"📌 <b>Navbat {idx}</b>\n"
            f"👤 <b>Mijoz:</b> {row['fullname']}\n"
            f"📞 <b>Tel:</b> {row['phonenumber']}\n"
            f"💈 <b>Barber:</b> {row['barber']}\n"
            f"✂️ <b>Xizmat:</b> {row['service']}\n"
            f"🗓 <b>Sana:</b> {row['date']}\n"
            f"⏰ <b>Vaqt:</b> {row['time']}\n"
            f"🗓 <b>Navbat olingan sana:</b> {row['booked_date']}\n"
            f"🗓 <b>Navbat olingan vaqt:</b> {row['booked_time']}\n\n"
        )

    # Tugmalarni tayyorlash - har birini alohida qatorda qo'yiladi
    rows = []
    nav_buttons = []

    # Oldingi sahifa mavjud bo'lsa -> qo'shamiz
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"prev_page:{page-1}")
        )

    # Keyingi sahifa mavjud bo'lsa -> qo'shamiz
    if offset + ORDERS_PER_PAGE < total_orders:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️  Keyingi", callback_data=f"next_page:{page+1}")
        )

    # Agar kamida bitta tugma bo'lsa, barchasini bitta qatorda joylaymiz
    if nav_buttons:
        rows = [nav_buttons]

    rows.extend(
        [
            [InlineKeyboardButton(text=EDIT_ORDERS_TEXT, callback_data=EDIT_ORDERS_CB)],
            [InlineKeyboardButton(text=CHECK_ORDERS_TEXT, callback_data=CHECK_ORDERS_CB)],
        ]
    )

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    return response, markup, total_orders


# 🗂 Buyurtmalar ro'yxatini chiqarish
@router.message(F.text == "📁 Buyurtmalar ro'yxati")
async def show_all_orders(message: types.Message, state: FSMContext):
    page = 0
    response, markup, total = await get_orders_page(page)

    msg = await message.answer(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(current_page=page, current_msg=msg.message_id, total_orders=total)


# 🔁 Sahifalar orasida silliq harakat
@router.callback_query(F.data.startswith(("next_page", "prev_page")))
async def paginate_orders(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = int(callback.data.split(":")[1])

    response, markup, total = await get_orders_page(page)

    # ❗ Xabarni yangidan yubormasdan silliq o‘zgartiramiz
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")

    await state.update_data(current_page=page, total_orders=total)
    await callback.answer("⏳ Yangilanmoqda...", show_alert=False)


@router.callback_query(F.data == EDIT_ORDERS_CB)
async def orders_edit_callback(callback: types.CallbackQuery, state: FSMContext):
    page = 1
    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=False, mode=MODE_EDIT
    )
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        orders_mode=MODE_EDIT,
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=False,
    )
    await callback.answer()


@router.callback_query(F.data == CHECK_ORDERS_CB)
async def orders_check_callback(callback: types.CallbackQuery, state: FSMContext):
    page = 1
    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=False, mode=MODE_VIEW
    )
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        orders_mode=MODE_VIEW,
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
            f"{EDIT_PAGE_CB}:",
            f"{EDIT_JUMP5_CB}:",
            f"{EDIT_JUMP10_CB}:",
            f"{EDIT_GOTO_CB}:",
            EDIT_SEARCH_MODE_CB,
            EDIT_BACK_CB,
        )
    )
)
async def paginate_check_orders(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data or ""
    state_data = await state.get_data()
    mode = _resolve_mode_from_callback(data, default_mode=state_data.get("orders_mode", MODE_VIEW))
    search_mode = bool(state_data.get("orders_search_mode", False))
    page = state_data.get("orders_current_page", state_data.get("check_current_page", 1))

    if data in (CHECK_SEARCH_MODE_CB, EDIT_SEARCH_MODE_CB):
        search_mode = True
    elif data in (CHECK_BACK_CB, EDIT_BACK_CB):
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
        page, search_mode=search_mode, mode=mode
    )
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    update_payload = {
        "orders_mode": mode,
        "orders_current_page": current_page,
        "orders_total_orders": total_orders,
        "orders_total_pages": total_pages,
        "orders_search_mode": search_mode,
    }
    if mode == MODE_VIEW:
        update_payload.update(
            check_current_page=current_page,
            check_total_orders=total_orders,
            check_total_pages=total_pages,
            check_search_mode=search_mode,
        )
    await state.update_data(**update_payload)
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
    page = state_data.get("orders_current_page", 1)
    search_mode = bool(state_data.get("orders_search_mode", False))
    if not isinstance(page, int):
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1

    response, markup, total_orders, total_pages, current_page = await get_check_orders_page(
        page, search_mode=search_mode, mode=MODE_EDIT
    )
    await callback.message.edit_text(response, reply_markup=markup, parse_mode="HTML")
    await state.update_data(
        orders_mode=MODE_EDIT,
        orders_current_page=current_page,
        orders_total_orders=total_orders,
        orders_total_pages=total_pages,
        orders_search_mode=search_mode,
    )
    if deleted:
        await callback.answer("Navbat o'chirildi ✅", show_alert=False)
        return
    await callback.answer("Buyurtma topilmadi.", show_alert=True)
