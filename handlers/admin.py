from aiogram import Router, types, F
from config import ADMINS  # admin ID lar
from aiogram.filters import Command
import json

router = Router()

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    markup = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📊 Statistika"), types.KeyboardButton(text="📁 Buyurtmalar ro'yxati")],
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
