from aiogram import Router, types, F
from config import ADMINS
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import static_data
from utils.states import AdminStates, BroadcastState
from datetime import datetime
import json
import re

from handlers.admins.admin_buttons import markup
from handlers.admins.admin_helpper import *
from database.services_barbers_utils import *

router = Router()
ORDERS_PER_PAGE = 5
USERS_FILE = "database/orders.json"

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

    # Inline buttonlarni qo‘shish
    buttons = []

    if page > 0:  # oldingi sahifa mavjud
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi ro'yhat", callback_data=f"prev_page:{page-1}"))
    if end < len(orders):  # keyingi sahifa mavjud
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi ro'yhat", callback_data=f"next_page:{page+1}"))

    return response, InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None


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
    await state.update_data(orders=orders, current_page=page, current_msg=sent_msg.message_id)


@router.callback_query(F.data.startswith(("next_page", "prev_page")))
async def paginate_orders(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    orders = data.get("orders", [])
    page = int(callback.data.split(":")[1])

    response, markup = get_orders_page(orders, page)

    # eski xabarni o‘chirib tashlash (faqat oxirgisini!)
    try:
        await callback.bot.delete_message(callback.message.chat.id, data["current_msg"])
    except:
        pass

    # yangi xabar yuborish
    sent_msg = await callback.message.answer(response, reply_markup=markup)
    await state.update_data(current_msg=sent_msg.message_id, current_page=page)

    await callback.answer()
   

@router.message(F.text == "💈 Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    await state.set_state(AdminStates.adding_service)
    await message.answer("📝 Yangi servis nomini kiriting:")


@router.message(AdminStates.adding_service)
async def save_service_name(message: types.Message, state: FSMContext):
    service_name = message.text.strip()

    # mavjudligini tekshirish (fayldan yangisini olish)
    services = sb_utils.load_services()
    for val in services.values():
        if val[0].lower() == service_name.lower():
            await message.answer("⚠️ Bu servis allaqachon mavjud.")
            await state.clear()
            return

    # xavfsiz ID yaratish
    raw_id = service_name.lower().replace(" ", "_")
    service_id = re.sub(r"[^a-z0-9_]", "", raw_id)

    base_id = service_id
    i = 1
    while service_id in services:
        service_id = f"{base_id}_{i}"
        i += 1

    # vaqtinchalik saqlash
    await state.update_data(service_id=service_id, service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer("💵 Servis narxini kiriting (so'mda, faqat raqam):")


@router.message(AdminStates.adding_service_price)
async def save_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Narx faqat raqam bo‘lishi kerak. Qayta kiriting:")
        return

    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("⏰ Servis davomiyligini kiriting (masalan: 30 daqiqa):")


@router.message(AdminStates.adding_service_duration)
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    data = await state.get_data()

    service_id = data["service_id"]
    service_name = data["service_name"]
    price = data["price"]

    # fayldan yangisini olish va qo‘shish
    services = sb_utils.load_services()
    services[service_id] = (service_name, price, duration)
    sb_utils.save_services(services)

    await message.answer(
        f"✅ Servis qo‘shildi:\n\n"
        f"✂️ {service_name} – {price} so'm ({duration})"
    )
    await state.clear()

@router.message(AdminStates.adding_barber)
async def save_barber(message: types.Message, state: FSMContext):
    barber_name = message.text.strip()

    # mavjudligini case-insensitive tekshirish
    for barber in static_data.barbers:
        if barber["name"].lower() == barber_name.lower():
            await message.answer("⚠️ Bu barber allaqachon mavjud.")
            await state.clear()
            return

    # xavfsiz ID yaratish
    raw_id = barber_name.lower().replace(" ", "_")
    barber_id = re.sub(r"[^a-z0-9_]", "", raw_id)

    # agar ID allaqachon mavjud bo‘lsa, raqam qo‘shib chiqamiz
    base_id = barber_id
    i = 1
    existing_ids = {b["id"] for b in static_data.barbers}
    while barber_id in existing_ids:
        barber_id = f"{base_id}_{i}"
        i += 1

    # yangi barber qo‘shish
    new_barber = {
        "id": barber_id,
        "name": barber_name,
        "exp": "0 yil",
        "days": "Noma’lum"
    }
    static_data.barbers.append(new_barber)

    await message.answer(f"✅ Barber qo‘shildi: {barber_name}")
    await state.clear()

@router.message(F.text == "✉️ Mahsus xabar yuborish")
async def ask_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return await message.answer("❌ Siz admin emassiz!")

    await message.answer("📨 Yubormoqchi bo'lgan xabaringizni kiriting:")
    await state.set_state(BroadcastState.waiting_for_message)


@router.message(BroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext, bot):
    text = message.text

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = []

    sent_count = 0
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=f"📢 Admin xabari:\n\n{text}")
            sent_count += 1
        except:
            pass  # agar foydalanuvchi bloklagan bo‘lsa yoki xato chiqsa

    await message.answer(f"✅ Xabar {sent_count} ta foydalanuvchiga yuborildi.")
    await state.clear()