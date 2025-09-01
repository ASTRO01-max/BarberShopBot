from aiogram import Router, types, F
from config import ADMINS  # admin ID lar
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import static_data
import json

class AdminStates(StatesGroup):
    adding_service = State()
    adding_barber = State()

router = Router()

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    markup = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📊 Statistika"), types.KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
            [types.KeyboardButton(text="💈Servis qo'shish"), types.KeyboardButton(text="👨‍🎤Barber qo'shis")],
            [types.KeyboardButton(text="Mahsus xabar yuborish"), types.KeyboardButton(text="CRN tizimi")]
            [types.KeyboardButton(text="🔙 Ortga")]
        ],
        resize_keyboard=True
    )

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

    total_orders = len(orders)
    users = set(order.get("user_id") for order in orders)

    await message.answer(f"📦 Jami buyurtmalar: {total_orders}\n👥 Foydalanuvchilar soni: {len(users)}")

@router.message(F.text == "📁 Buyurtmalar ro'yxati")
async def show_all_orders(message: types.Message):
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

    response = "📋 Buyurtmalar ro'yxati:\n\n"
    for idx, order in enumerate(orders, start=1):
        response += f"{idx}. 👤 ID: {order.get('user_id')} - 💈 Barber: {order.get('barber')} - ✂️ Xizmat: {order.get('service')} - ⏰ {order.get('date')} {order.get('time')}\n"

    await message.answer(response)

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
