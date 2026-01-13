#admins/order_list.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order, Services, Barbers
from sqlalchemy import func

router = Router()
ORDERS_PER_PAGE = 5


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
                "fullname": getattr(order, "fullname", "") or "",
                "phonenumber": getattr(order, "phonenumber", "") or "",
                "barber": barber_name,
                "service": service_name,
                "date": order.date.strftime("%Y-%m-%d") if hasattr(order.date, "strftime") else str(order.date),
                "time": order.time.strftime("%H:%M") if hasattr(order.time, "strftime") else str(order.time),
                "booked_date": order.booked_date.strftime("%Y-%m-%d") if hasattr(order.booked_date, "strftime") else str(order.booked_date),
                "booked_time": order.booked_time.strftime("%H:%M") if hasattr(order.booked_time, "strftime") else str(order.booked_time),
            }
        )

    return rows


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

    # Tugmalarni tayyorlash — har birini alohida qatorda qo'yiladi
    rows = []
    nav_buttons = []

    # Oldingi sahifa mavjud bo‘lsa → qo‘shamiz
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"prev_page:{page-1}")
        )

    # Keyingi sahifa mavjud bo‘lsa → qo‘shamiz
    if offset + ORDERS_PER_PAGE < total_orders:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"next_page:{page+1}")
        )

    # Agar kamida bitta tugma bo‘lsa, barchasini bitta qatorda joylaymiz
    if nav_buttons:
        rows = [nav_buttons]

    markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
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


#ro'yhatdagi buyurtmalarni o'chirish funksiyalari 
