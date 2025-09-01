from aiogram import Router, types, F
from config import ADMINS
import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()

ORDERS_PER_PAGE = 5  # har safar nechta buyurtma ko‘rsatish


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

    # Inline button qo‘shish (agar keyingi sahifa mavjud bo‘lsa)
    buttons = []
    if end < len(orders):  # keyingi sahifa bor
        buttons.append([InlineKeyboardButton(text="➡️ Keyingi ro'yhat", callback_data=f"next_page:{page+1}")])

    return response, InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


@router.message(F.text == "📁 Buyurtmalar ro'yxati")
async def show_all_orders(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    orders_file = "database/orders.json"
    try:
        with open(orders_file, "r", encoding="utf-8") as file:
            orders = json.load(file)
    except:
        orders = []

    if not orders:
        await message.answer("📂 Buyurtmalar topilmadi.")
        return

    # birinchi sahifa
    page = 0
    response, markup = get_orders_page(orders, page)

    sent_msg = await message.answer(response, reply_markup=markup)
    await state.update_data(orders=orders, current_msg=sent_msg.message_id)


@router.callback_query(F.data.startswith("next_page"))
async def paginate_orders(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    orders = data.get("orders", [])
    page = int(callback.data.split(":")[1])

    response, markup = get_orders_page(orders, page)

    # eski xabarni o‘chirib tashlash
    try:
        await callback.bot.delete_message(callback.message.chat.id, data["current_msg"])
    except:
        pass

    # yangi xabar yuborish
    sent_msg = await callback.message.answer(response, reply_markup=markup)
    await state.update_data(current_msg=sent_msg.message_id)
    await callback.answer()
