from aiogram import Router, types, F
from config import ADMINS
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import static_data
from utils.states import AdminStates
from datetime import datetime
import json

from handlers.admins.admin_buttons import markup
from handlers.admins.admin_helpper import *

router = Router()
ORDERS_PER_PAGE = 5

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    await message.answer("🔐 Admin panelga xush kelibsiz!", reply_markup=markup)

@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    orders_file = "database/orders.json"
    try:
        with open(orders_file, "r", encoding="utf-8") as file:
            orders = json.load(file)
    except:
        orders = []

    # Jami buyurtmalar va foydalanuvchilar
    total_orders = len(orders)
    users = set(order.get("user_id") for order in orders)

    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")

    # Bugungi buyurtmalar va foydalanuvchilar
    today_orders = [o for o in orders if o.get("date") == today]
    today_users = set(o.get("user_id") for o in today_orders)

    await message.answer(
        f"📦 Jami buyurtmalar soni: {total_orders}\n"
        f"👥 Foydalanuvchilar soni: {len(users)}\n"
        f"📅 Bugungi buyurtmalar soni: {len(today_orders)}\n"
        f"🙋‍♂️ Bugungi foydalanuvchilar soni: {len(today_users)}"
    )

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
   

# @router.message(F.text == "📁 Buyurtmalar ro'yxati")
# async def show_all_orders(message: types.Message):
#     if message.from_user.id not in ADMINS:
#         return

#     orders_file = "database/orders.json"
#     try:
#         with open(orders_file, "r", encoding="utf-8") as file:
#             orders = json.load(file)
#     except:
#         orders = []

#     if not orders:
#         await message.answer("📂 Buyurtmalar topilmadi.")
#         return

#     response = "📋 Buyurtmalar ro'yxati:\n\n"
#     for idx, order in enumerate(orders, start=1):
#         response += (
#             f"📌 Buyurtma {idx}\n"
#             f"👤 Mijoz: {order.get('fullname')}\n"
#             f"💈 Barber: {order.get('barber_id')}\n"
#             f"✂️ Xizmat: {order.get('service_id')}\n"
#             f"🗓 Sana: {order.get('date')}\n"
#             f"⏰ Vaqt: {order.get('time')}\n\n"
#         )

#     await message.answer(response)

@router.message(F.text == "💈Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    await state.set_state(AdminStates.adding_service)
    await message.answer("📝 Yangi servis nomini kiriting:")

@router.message(AdminStates.adding_service)
async def save_service(message: types.Message, state: FSMContext):
    service_name = message.text.strip()
    for val in static_data.services.values():
        if val[0] == service_name:
            await message.answer("⚠️ Bu servis allaqachon mavjud.")
            await state.clear()
            return

    # ID yaratish (masalan, pastga aylantirib)
    service_id = service_name.lower().replace(" ", "_")
    static_data.services[service_id] = (service_name, 0, "0 daqiqa")  # Default qiymatlar
    await message.answer(f"✅ Servis qo‘shildi: {service_name}")
    await state.clear()

@router.message(F.text == "👨‍🎤Barber qo'shis")
async def add_barber_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    await state.set_state(AdminStates.adding_barber)
    await message.answer("🧔‍♂️ Yangi barber nomini kiriting:")

@router.message(AdminStates.adding_barber)
async def save_barber(message: types.Message, state: FSMContext):
    barber_name = message.text.strip()
    for barber in static_data.barbers:
        if barber["name"].lower() == barber_name.lower():
            await message.answer("⚠️ Bu barber allaqachon mavjud.")
            await state.clear()
            return

    barber_id = barber_name.lower().replace(" ", "_")
    new_barber = {
        "id": barber_id,
        "name": barber_name,
        "exp": "0 yil",
        "days": "Noma’lum"
    }
    static_data.barbers.append(new_barber)
    await message.answer(f"✅ Barber qo‘shildi: {barber_name}")
    await state.clear()
