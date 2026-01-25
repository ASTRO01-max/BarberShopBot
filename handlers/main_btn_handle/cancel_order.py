#handlers/main_btn_handle/cancel_order.py
from datetime import date

from aiogram import F, Router, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, and_

from sql.db import async_session
from sql.models import Order
from keyboards.main_buttons import get_dynamic_main_keyboard
from keyboards.main_menu import get_main_menu

from .common import _format_dt, CANCEL_ORDERS_PER_PAGE

router = Router()

def _prepare_cancel_order_cards(orders):
    cards = []
    for o in orders:
        cards.append(
            {
                "id": o.id,
                "user_id": o.user_id,
                "fullname": o.fullname,
                "phonenumber": o.phonenumber,
                "service_id": o.service_id,
                "barber_id_name": o.barber_id_name,
                "date": _format_dt(o.date, "%Y-%m-%d"),
                "time": _format_dt(o.time, "%H:%M"),
                "booked_date": _format_dt(o.booked_date, "%Y-%m-%d"),
                "booked_time": _format_dt(o.booked_time, "%H:%M"),
            }
        )
    return cards


def get_cancel_orders_page(order_cards, page: int):
    start = page * CANCEL_ORDERS_PER_PAGE
    end = start + CANCEL_ORDERS_PER_PAGE
    sliced = order_cards[start:end]
    if not sliced:
        return "🛒 Buyurtmalar topilmadi.", InlineKeyboardMarkup(inline_keyboard=[])

    o = sliced[0]
    total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

    text = (
        "❌ *Bekor qilinadigan buyurtma:*\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        f"🆔 ID: {o['id']}\n\n"
        f"👤 Mijoz: {o['fullname']}\n"
        f"📞 Tel: {o['phonenumber']}\n"
        f"🧾 Xizmat ID: {o['service_id']}\n"
        f"💈 Barber: {o['barber_id_name']}\n"
        f"📅 Sana: {o['date']}\n"
        f"⏰ Vaqt: {o['time']}\n"
        f"🗓️ Buyurtma sanasi: {o['booked_date']}\n"
        f"🕒 Buyurtma vaqti: {o['booked_time']}\n"
    )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"cancel_prev:{page-1}"))
    if end < len(order_cards):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"cancel_next:{page+1}"))

    nav_row = buttons if buttons else []
    action_row = [
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order:{o['id']}")
    ]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, action_row] if nav_row else [action_row])
    return text, inline_kb

@router.message(F.text == "❌Buyurtmani bekor qilish")
async def show_todays_orders_for_cancel(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    today = date.today()

    # 🔹 Foydalanuvchining bugun joylagan barcha buyurtmalarini olish (navbat sanasidan qat’i nazar)
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(
                and_(Order.user_id == user_id, Order.booked_date == today)
            )
        )
        orders = result.scalars().all()

    # 🔹 Agar bugungi buyurtma topilmasa
    if not orders:
        keyboard = await get_dynamic_main_keyboard(user_id)
        await message.answer(
            "❗ Sizda bugun joylagan bekor qilinadigan buyurtma topilmadi.",
            reply_markup=keyboard
        )
        await message.answer(
            "Quyidagi menyudan birini tanlang:",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return
    # Bugun joylagan barcha buyurtmalarni chiqarish
    order_cards = _prepare_cancel_order_cards(orders)
    page = 0
    text, markup = get_cancel_orders_page(order_cards, page)
    await message.answer(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(cancel_order_cards=order_cards, cancel_current_page=page)


# Tugma bosilganda — buyurtmani bekor qilish
@router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order_callback(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return await callback.answer("❌ Xatolik: noto‘g‘ri ID.", show_alert=True)

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("❗ Bu buyurtma allaqachon bekor qilingan.", show_alert=True)
            return

        await session.delete(order)
        await session.commit()

    await callback.message.edit_text(
        f"✅ Buyurtma bekor qilindi!\n\n"
        f"📅 Sana: {order.date}\n"
        f"⏰ Vaqt: {order.time}"
    )
    await callback.answer("Buyurtma muvaffaqiyatli o‘chirildi ✅")

    keyboard = await get_dynamic_main_keyboard(callback.from_user.id)
    await callback.message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )



@router.callback_query(F.data.startswith(("cancel_next", "cancel_prev")))
async def paginate_cancel_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_cards = data.get("cancel_order_cards", [])
    if not order_cards:
        await callback.answer("?? Buyurtmalar topilmadi", show_alert=True)
        return

    page = int(callback.data.split(":")[1])
    text, markup = get_cancel_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(cancel_current_page=page)
    await callback.answer()
