from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMINS
import json

router = Router()
ORDERS_PER_PAGE = 5
ORDERS_FILE = "database/orders.json"

def get_orders_page(orders, page: int):
    start = page * ORDERS_PER_PAGE
    end = start + ORDERS_PER_PAGE
    sliced_orders = orders[start:end]

    response = "📋 Buyurtmalar ro'yxati:\n\n"
    for idx, order in enumerate(sliced_orders, start=start + 1):
        response += (
            f"📌 Buyurtma {idx}\n"
            f"👤 Mijoz: {order.get('fullname')}\n"
            f"💈 Barber: {order.get('barber_id')}\n"
            f"✂️ Xizmat: {order.get('service_id')}\n"
            f"🗓 Sana: {order.get('date')}\n"
            f"⏰ Vaqt: {order.get('time')}\n\n"
        )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi ro'yhat", callback_data=f"prev_page:{page-1}"))
    if end < len(orders):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi ro'yhat", callback_data=f"next_page:{page+1}"))

    return response, (InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None)

@router.message(F.text == "📁 Buyurtmalar ro'yxati")
async def show_all_orders(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)
    except:
        orders = []

    if not orders:
        return await message.answer("📂 Buyurtmalar topilmadi.")

    page = 0
    response, markup = get_orders_page(orders, page)
    sent_msg = await message.answer(response, reply_markup=markup)
    await state.update_data(orders=orders, current_page=page, current_msg=sent_msg.message_id)

@router.callback_query(F.data.startswith(("next_page", "prev_page")))
async def paginate_orders(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    orders = data.get("orders", [])
    page = int(callback.data.split(":")[1])

    response, markup = get_orders_page(orders, page)
    try:
        await callback.bot.delete_message(callback.message.chat.id, data["current_msg"])
    except:
        pass
    sent_msg = await callback.message.answer(response, reply_markup=markup)
    await state.update_data(current_msg=sent_msg.message_id, current_page=page)
    await callback.answer()
