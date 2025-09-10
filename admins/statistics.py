from aiogram import Router, types, F
from config import ADMINS
from datetime import datetime
import json

router = Router()

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

    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = [o for o in orders if o.get("date") == today]
    today_users = set(o.get("user_id") for o in today_orders)

    await message.answer(
        f"📦 Jami buyurtmalar soni: {total_orders}\n"
        f"👥 Foydalanuvchilar soni: {len(users)}\n"
        f"📅 Bugungi buyurtmalar soni: {len(today_orders)}\n"
        f"🙋‍♂️ Bugungi foydalanuvchilar soni: {len(today_users)}"
    )
