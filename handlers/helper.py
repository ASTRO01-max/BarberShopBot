from aiogram import F, types, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import json
import os
from pathlib import Path
from datetime import datetime

ORDER_FILE = Path("database/orders.json")
router = Router()

def load_orders() -> list:
    """Barcha buyurtmalarni yuklaydi."""
    if not ORDER_FILE.exists():
        return []
    try:
        with ORDER_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_order(order: dict):
    """Yangi buyurtmani saqlaydi."""
    orders = load_orders()
    orders.append({
        "user_id": order.get("user_id"),
        "date": order.get("date"),
        "time": order.get("time"),
        "service_id": order.get("service_id"),
        "service": order.get("service"),
        "barber_id": order.get("barber_id"),
        "barber": order.get("barber"),
    })

    ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ORDER_FILE.open("w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=4)
    ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ORDER_FILE.open("w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=4)


def get_booked_times(service_id: str, barber_id: str, date: str) -> list:
    """
    Berilgan xizmat, barber va sanaga tegishli band qilingan vaqtlar ro'yxatini qaytaradi.
    """
    orders = load_orders()
    return [
        order['time']
        for order in orders
        if order.get('service_id') == service_id and
           order.get('barber_id') == barber_id and
           order.get('date') == date
    ]

def delete_last_order_by_user(user_id):
    if not os.path.exists(ORDER_FILE):
        return None

    with open(ORDER_FILE, "r", encoding="utf-8") as file:
        try:
            orders = json.load(file)
        except json.JSONDecodeError:
            return None

    user_orders = [order for order in orders if order.get("user_id") == user_id]


    if not user_orders:
        return None

    last_order = user_orders[-1]
    orders.remove(last_order)

    with open(ORDER_FILE, "w", encoding="utf-8") as file:
        json.dump(orders, file, indent=4, ensure_ascii=False)

    return last_order

@router.message(F.text == "🗂Buyurtmalar tarixi")
async def show_user_orders(message: Message):
    """Foydalanuvchining bugungi buyurtmalarini tekshiradi."""
    user_id = str(message.from_user.id)
    orders = load_orders()

    # Foydalanuvchiga tegishli buyurtmalar
    user_orders = [o for o in orders if str(o.get("user_id")) == user_id]

    if not user_orders:
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")
    todays_orders = [o for o in user_orders if o.get("date") == today]

    if not todays_orders:
        # Agar bugungi buyurtma bo‘lmasa
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📂 Oldingi buyurtmalarni ko'rish", callback_data="show_all_orders")]
            ]
        )
        await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
        return

    # Bugungi buyurtmalarni chiqarish
    response_lines = ["🗂 *Bugungi buyurtmalaringiz:*\n"]
    for idx, order in enumerate(todays_orders, start=1):
        sana = order.get("date", "Nomaʼlum")
        vaqt = order.get("time", "Nomaʼlum")
        barber = order.get("barber") or order.get("barber_id", "Nomaʼlum")
        xizmat = order.get("service") or order.get("service_id", "Nomaʼlum")

        response_lines.append(
            f"{idx}. 📅 {sana}, ⏰ {vaqt}\n   💈 Barber: {barber}\n   ✂️ Xizmat: {xizmat}\n"
        )

    await message.answer("\n".join(response_lines), parse_mode="Markdown")


@router.callback_query(F.data == "show_all_orders")
async def show_all_orders(callback: CallbackQuery):
    """Foydalanuvchining barcha buyurtmalarini ko‘rsatadi."""
    user_id = str(callback.from_user.id)
    orders = load_orders()

    user_orders = [o for o in orders if str(o.get("user_id")) == user_id]

    if not user_orders:
        await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    response_lines = ["🗂 *Sizning barcha buyurtmalaringiz:*\n"]
    for idx, order in enumerate(user_orders, start=1):
        sana = order.get("date", "Nomaʼlum")
        vaqt = order.get("time", "Nomaʼlum")
        barber = order.get("barber") or order.get("barber_id", "Nomaʼlum")
        xizmat = order.get("service") or order.get("service_id", "Nomaʼlum")

        response_lines.append(
            f"{idx}. 📅 {sana}, ⏰ {vaqt}\n   💈 Barber: {barber}\n   ✂️ Xizmat: {xizmat}\n"
        )

    await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown")
    await callback.answer()
