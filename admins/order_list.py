#admins/order_list.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order
from sqlalchemy import func

router = Router()
ORDERS_PER_PAGE = 5


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
        # Log yoki print — developmentda ko'rish uchun
        print("get_orders_page DB error:", repr(e))
        return "❗ Navbatlar olishda xatolik yuz berdi.", None, 0

    if not orders:
        return "📂 Navbatlar topilmadi.", None, total_orders

    response = f"📋 <b>Navbatlar ro'yxati (sahifa {page + 1})</b>\n\n"
    for idx, order in enumerate(orders, start=offset + 1):
        # xavfsiz atribut olish (None bo'lsa bo'sh)
        fullname = getattr(order, "fullname", "") or ""
        phonenumber = getattr(order, "phonenumber", "") or ""
        barber_id = getattr(order, "barber_id", "") or ""
        service_id = getattr(order, "service_id", "") or ""
        order_date = getattr(order, "date", "") or ""
        order_time = getattr(order, "time", "") or ""
        order_booked_date = getattr(order, "booked_date", "") or ""
        order_booked_time = getattr(order, "booked_time", "") or ""

        response += (
            f"📌 <b>Navbat {idx}</b>\n"
            f"👤 <b>Mijoz:</b> {fullname}\n"
            f"📞 <b>Tel:</b> {phonenumber}\n"
            f"💈 <b>Barber ID:</b> {barber_id}\n"
            f"✂️ <b>Xizmat ID:</b> {service_id}\n"
            f"🗓 <b>Sana:</b> {order_date}\n"
            f"⏰ <b>Vaqt:</b> {order_time}\n"
            f"🗓 <b>Navbat olingan sana:</b> {order_booked_date}\n"
            f"🗓 <b>Navbat olingan vaqt:</b> {order_booked_time}\n\n"
        )

    # Tugmalarni tayyorlash — har birini alohida qatorda qo'yamiz
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