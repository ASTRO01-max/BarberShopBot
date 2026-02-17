# handlers/main_btn_handle/orders_history.py
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .common import _fetch_user_orders, _prepare_order_cards, get_user_orders_page

router = Router()

TODAY_ORDERS_PER_PAGE = 1


def get_today_orders_page(order_cards, page: int):
    start = page * TODAY_ORDERS_PER_PAGE
    end = start + TODAY_ORDERS_PER_PAGE
    sliced = order_cards[start:end]

    if not sliced:
        return (
            "🛒 Bugungi buyurtmalar topilmadi.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
                ]
            ),
        )

    o = sliced[0]
    total_pages = (len(order_cards) - 1) // TODAY_ORDERS_PER_PAGE + 1

    text = (
        "🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        f"📅 Sana: {o['date']}\n"
        f"⏰ Vaqt: {o['time']}\n"
        f"💈 Barber: {o['barber']}\n"
        f"✂️ Xizmat: {o['service']}\n"
    )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"today_prev:{page-1}"))
    if end < len(order_cards):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"today_next:{page+1}"))

    rows = []
    if buttons:
        rows.append(buttons)
    rows.append([InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")])

    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_todays_order_cards(user_id: int):
    todays_orders = await _fetch_user_orders(user_id, only_today=True)
    if not todays_orders:
        return []
    return await _prepare_order_cards(todays_orders)


# Asosiy "🗂 Buyurtmalar tarixi" bosilganda - bugungi buyurtmalarni 1 tadan pagination bilan ko'rsatadi
@router.message(F.text.in_(["🗂 Buyurtmalar tarixi", "🗂Buyurtmalar tarixi"]))
async def show_user_orders(message: Message, state: FSMContext):
    user_id = message.from_user.id
    order_cards = await _load_todays_order_cards(user_id)

    if not order_cards:
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

    page = 0
    text, markup = get_today_orders_page(order_cards, page)
    await message.answer(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(today_order_cards=order_cards, today_current_page=page)


@router.callback_query(F.data.startswith(("today_next", "today_prev")))
async def paginate_today_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_cards = data.get("today_order_cards", [])

    if not order_cards:
        order_cards = await _load_todays_order_cards(callback.from_user.id)
        if not order_cards:
            await callback.message.edit_text(
                "❌ Bugun joylashtirilgan buyurtma topilmadi.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
                    ]
                ),
            )
            await callback.answer()
            return

    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto‘g‘ri sahifa.", show_alert=True)
        return

    total_pages = (len(order_cards) - 1) // TODAY_ORDERS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))

    text, markup = get_today_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(today_order_cards=order_cards, today_current_page=page)
    await callback.answer()


# Barcha buyurtmalar (pagination bilan)
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


# Pagination tugmalari uchun
@router.callback_query(F.data.startswith(("user_next", "user_prev")))
async def paginate_user_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_cards = data.get("order_cards", [])
    if not order_cards:
        await callback.answer("⚠️ Buyurtmalar topilmadi", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto‘g‘ri sahifa.", show_alert=True)
        return

    text, markup = get_user_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(current_page=page)
    await callback.answer()


# "Bugungi buyurtmalarga qaytish" tugmasi uchun
@router.callback_query(F.data == "back_to_today")
async def back_to_today(callback: CallbackQuery, state: FSMContext):
    order_cards = await _load_todays_order_cards(callback.from_user.id)

    if not order_cards:
        await callback.message.edit_text(
            "❌ Bugun joylashtirilgan buyurtma topilmadi.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
                ]
            ),
        )
        await callback.answer()
        return

    page = 0
    text, markup = get_today_orders_page(order_cards, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(today_order_cards=order_cards, today_current_page=page)
    await callback.answer()
