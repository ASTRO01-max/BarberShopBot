from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order
from sqlalchemy import func

router = Router()
ORDERS_PER_PAGE = 5


# 📄 Sahifani shakllantirish funksiyasi
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
        return "❗ Buyurtmalarni olishda xatolik yuz berdi.", None, 0

    if not orders:
        return "📂 Buyurtmalar topilmadi.", None, total_orders

    response = f"📋 <b>Buyurtmalar ro'yxati (sahifa {page + 1})</b>\n\n"
    for idx, order in enumerate(orders, start=offset + 1):
        # xavfsiz atribut olish (None bo'lsa bo'sh)
        fullname = getattr(order, "fullname", "") or ""
        phonenumber = getattr(order, "phonenumber", "") or ""
        barber_id = getattr(order, "barber_id", "") or ""
        service_id = getattr(order, "service_id", "") or ""
        order_date = getattr(order, "date", "") or ""
        order_time = getattr(order, "time", "") or ""

        response += (
            f"📌 <b>Buyurtma {idx}</b>\n"
            f"👤 <b>Mijoz:</b> {fullname}\n"
            f"📞 <b>Tel:</b> {phonenumber}\n"
            f"💈 <b>Barber ID:</b> {barber_id}\n"
            f"✂️ <b>Xizmat ID:</b> {service_id}\n"
            f"🗓 <b>Sana:</b> {order_date}\n"
            f"⏰ <b>Vaqt:</b> {order_time}\n\n"
        )

    # Tugmalarni tayyorlash — har birini alohida qatorda qo'yamiz
    rows = []
    if page > 0:
        rows.append([InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"prev_page:{page-1}")])
    if offset + ORDERS_PER_PAGE < total_orders:
        rows.append([InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"next_page:{page+1}")])

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