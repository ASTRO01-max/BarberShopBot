#handlers/main_btn_handle/orders_history.py
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from .common import _fetch_user_orders, _prepare_order_cards, get_user_orders_page

router = Router()

# 🟢 1️⃣ Asosiy "🗂Buyurtmalar tarixi" bosilganda — bugun joylashtirilgan buyurtmalarni ko‘rsatadi
@router.message(F.text == "🗂Buyurtmalar tarixi")
async def show_user_orders(message: Message):
    user_id = message.from_user.id
    todays_orders = await _fetch_user_orders(user_id, only_today=True)
    if not todays_orders:
        all_orders = await _fetch_user_orders(user_id, only_today=False)
        if not all_orders:
            await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
            return

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
            ]
        )
        await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
        return

    order_cards = await _prepare_order_cards(todays_orders)

    # 🔸 Agar bugun joylashtirilgan buyurtmalar mavjud bo‘lsa
    response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
    for idx, o in enumerate(order_cards, start=1):
        response_lines.append(
            f"{idx}. 📅 {o['date']}, ⏰ {o['time']}\n"
            f"   💈 Barber: {o['barber']}\n"
            f"   ✂️ Xizmat: {o['service']}\n"
        )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
        ]
    )

    await message.answer("\n".join(response_lines), parse_mode="Markdown", reply_markup=markup)


# 🟢 2️⃣ Barcha buyurtmalar (pagination bilan)
@router.callback_query(F.data == "show_all_orders")
async def show_all_orders(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_orders = await _fetch_user_orders(user_id)
    if not user_orders:
        await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
        await callback.answer()
        return

    order_cards = await _prepare_order_cards(user_orders)
    page = 0
    text, markup = get_user_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(order_cards=order_cards, current_page=page)
    await callback.answer()


# 🟢 3️⃣ Pagination tugmalari uchun
@router.callback_query(F.data.startswith(("user_next", "user_prev")))
async def paginate_user_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_cards = data.get("order_cards", [])
    if not order_cards:
        await callback.answer("⚠️ Buyurtmalar topilmadi", show_alert=True)
        return

    page = int(callback.data.split(":")[1])
    text, markup = get_user_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(current_page=page)
    await callback.answer()


# 🟢 4️⃣ "Bugungi buyurtmalarga qaytish" tugmasi uchun
@router.callback_query(F.data == "back_to_today")
async def back_to_today(callback: CallbackQuery):
    user_id = callback.from_user.id
    todays_orders = await _fetch_user_orders(user_id, only_today=True)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
        ]
    )

    if not todays_orders:
        await callback.message.edit_text("❌ Bugun joylashtirilgan buyurtma topilmadi.", reply_markup=markup)
        await callback.answer()
        return

    order_cards = await _prepare_order_cards(todays_orders)

    response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
    for idx, o in enumerate(order_cards, start=1):
        response_lines.append(
            f"{idx}. 📅 {o['date']}, ⏰ {o['time']}\n"
            f"   💈 Barber: {o['barber']}\n"
            f"   ✂️ Xizmat: {o['service']}\n"
        )

    await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown", reply_markup=markup)
    await callback.answer()
