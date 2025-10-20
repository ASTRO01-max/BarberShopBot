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
    offset = page * ORDERS_PER_PAGE

    async with async_session() as session:
        # Har safar faqat kerakli 5 ta yozuvni olamiz
        result = await session.execute(
            select(Order)
            .order_by(Order.date.desc(), Order.time.desc())
            .offset(offset)
            .limit(ORDERS_PER_PAGE)
        )
        orders = result.scalars().all()

        # Umumiy buyurtmalar sonini olish
        total_orders = await session.scalar(select(func.count(Order.id)))

    if not orders:
        return "📂 Buyurtmalar topilmadi.", None, total_orders

    response = f"📋 <b>Buyurtmalar ro'yxati (sahifa {page + 1})</b>\n\n"
    for idx, order in enumerate(orders, start=offset + 1):
        response += (
            f"📌 <b>Buyurtma {idx}</b>\n"
            f"👤 <b>Mijoz:</b> {order.fullname}\n"
            f"📞 <b>Tel:</b> {order.phonenumber}\n"
            f"💈 <b>Barber ID:</b> {order.barber_id}\n"
            f"✂️ <b>Xizmat ID:</b> {order.service_id}\n"
            f"🗓 <b>Sana:</b> {order.date}\n"
            f"⏰ <b>Vaqt:</b> {order.time}\n\n"
        )

    # Tugmalarni tayyorlash
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"prev_page:{page-1}"))
    if offset + ORDERS_PER_PAGE < total_orders:
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"next_page:{page+1}"))

    markup = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
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