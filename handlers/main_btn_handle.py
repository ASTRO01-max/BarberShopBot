#handlers/main_btn_handle.py
import re
from aiogram import F, types, Router
from datetime import date
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from sqlalchemy import select, and_
from sql.db import async_session
from sql.models import Order, Services
from utils.states import UserState, UserForm
from sql.db_order_utils import delete_last_order_by_user, load_orders
from sql.db_users_utils import save_user, update_user, delete_user, get_user
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from utils.validators import validate_fullname, validate_phone

router = Router()
USER_ORDERS_PER_PAGE = 5


def get_user_orders_page(user_orders, page: int):
    """
    Foydalanuvchi buyurtmalarini sahifalab chiqarish
    """
    start = page * USER_ORDERS_PER_PAGE
    end = start + USER_ORDERS_PER_PAGE
    sliced = user_orders[start:end]

    text = "📋 *Sizning barcha buyurtmalaringiz:*\n\n"
    for idx, o in enumerate(sliced, start=start + 1):
        text += (
            f"📌 *Buyurtma {idx}*\n"
            f"📅 Sana: {o.date}\n"
            f"⏰ Vaqt: {o.time}\n"
            f"💈 Barber: {o.barber_id}\n"
            f"✂️ Xizmat: {o.service_id}\n\n"
        )

    # Tugmalar (pagination + qaytish)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"user_prev:{page-1}"))
    if end < len(user_orders):
        buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"user_next:{page+1}"))

    nav_row = buttons if buttons else []
    back_row = [InlineKeyboardButton(text="📂 Bugungi buyurtmalarga qaytish", callback_data="back_to_today")]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, back_row] if nav_row else [back_row])
    return text, inline_kb


# 🟢 1️⃣ Asosiy "🗂Buyurtmalar tarixi" bosilganda — bugun joylashtirilgan buyurtmalarni ko‘rsatadi
@router.message(F.text == "🗂Buyurtmalar tarixi")
async def show_user_orders(message: Message):
    user_id = message.from_user.id
    orders = await load_orders()
    user_orders = [o for o in orders if o.user_id == user_id]

    if not user_orders:
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    today = datetime.now().date()
    # 🔹 Faqat bugun joylashtirilgan buyurtmalarni olish (booked_date bo‘yicha)
    todays_orders = [o for o in user_orders if getattr(o, "booked_date", None) == today]

    # 🔸 Agar bugun buyurtma qilinmagan bo‘lsa
    if not todays_orders:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
            ]
        )
        await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
        return

    # 🔸 Agar bugun joylashtirilgan buyurtmalar mavjud bo‘lsa
    response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
    for idx, o in enumerate(todays_orders, start=1):
        response_lines.append(
            f"{idx}. 📅 {o.date}, ⏰ {o.time}\n"
            f"   💈 Barber: {o.barber_id}\n"
            f"   ✂️ Xizmat: {o.service_id}\n"
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
    orders = await load_orders()
    user_orders = [o for o in orders if o.user_id == user_id]

    if not user_orders:
        await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
        await callback.answer()
        return

    page = 0
    text, markup = get_user_orders_page(user_orders, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(user_orders=user_orders, current_page=page)
    await callback.answer()


# 🟢 3️⃣ Pagination tugmalari uchun
@router.callback_query(F.data.startswith(("user_next", "user_prev")))
async def paginate_user_orders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_orders = data.get("user_orders", [])
    if not user_orders:
        await callback.answer("⚠️ Buyurtmalar topilmadi", show_alert=True)
        return

    page = int(callback.data.split(":")[1])
    text, markup = get_user_orders_page(user_orders, page)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(current_page=page)
    await callback.answer()


# 🟢 4️⃣ "Bugungi buyurtmalarga qaytish" tugmasi uchun
@router.callback_query(F.data == "back_to_today")
async def back_to_today(callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = await load_orders()
    user_orders = [o for o in orders if o.user_id == user_id]

    today = datetime.now().date()
    todays_orders = [o for o in user_orders if getattr(o, "booked_date", None) == today]

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
        ]
    )

    if not todays_orders:
        await callback.message.edit_text("❌ Bugun joylashtirilgan buyurtma topilmadi.", reply_markup=markup)
        await callback.answer()
        return

    response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
    for idx, o in enumerate(todays_orders, start=1):
        response_lines.append(
            f"{idx}. 📅 {o.date}, ⏰ {o.time}\n"
            f"   💈 Barber: {o.barber_id}\n"
            f"   ✂️ Xizmat: {o.service_id}\n"
        )

    await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown", reply_markup=markup)
    await callback.answer()


@router.message(F.text == "❌Buyurtmani bekor qilish")
async def show_todays_orders_for_cancel(message: types.Message):
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

    # 🔹 Bugun joylagan barcha buyurtmalarni chiqarish
    async with async_session() as session:
        for order in orders:
            # Xizmat nomini xavfsiz olish
            service_name = str(order.service_id)
            if isinstance(order.service_id, int):
                service = await session.get(Services, order.service_id)
                if service:
                    service_name = service.service_name

            markup = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="❌ Bekor qilish",
                        callback_data=f"cancel_order:{order.id}"
                    )
                ]]
            )

            await message.answer(
                f"📅 Sana: {order.date}\n"
                f"⏰ Vaqt: {order.time}\n"
                f"✂️ Xizmat: {service_name}",
                reply_markup=markup
            )


# 🟢 Tugma bosilganda — buyurtmani bekor qilish
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



@router.message(F.text == "📥Foydalanuvchini saqlash")
async def ask_fullname(message: types.Message, state: FSMContext):
    await state.set_state(UserForm.fullname)
    await message.answer("👤 To‘liq ismingizni kiriting:")


@router.message(UserForm.fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if not validate_fullname(fullname):
        await message.answer("❌ Ism noto‘g‘ri formatda.")
        return
    await state.update_data(fullname=fullname)
    await state.set_state(UserForm.phone)
    await message.answer("📞 Telefon raqamingizni kiriting (+998 bilan)")
    await message.answer(
        "Telefon raqamingizni button orqali yuborishingiz mumkin",
        reply_markup=phone_request_keyboard
    )

@router.message(UserForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone_raw = None
    if message.contact and getattr(message.contact, "phone_number", None):
        phone_raw = message.contact.phone_number
    elif message.text:
        phone_raw = message.text.strip()
    else:
        await message.answer("📱 Iltimos telefon raqamingizni yuboring — matn sifatida (+998901234567) yoki 'Kontakt yuborish' tugmasi orqali.")
        return

    digits = re.sub(r"\D", "", phone_raw) 
    normalized = None

    if phone_raw.startswith("+") and len(digits) >= 9:
        normalized = "+" + digits
    elif digits.startswith("998") and len(digits) >= 12:
        normalized = "+" + digits
    elif digits.startswith("0") and len(digits) == 9:
        normalized = "+998" + digits[1:]
    else:
        normalized = "+" + digits
    if not validate_phone(normalized):
        await message.answer("❌ Telefon raqami noto‘g‘ri. Iltimos +998901234567 formatida yuboring yoki Kontakt yuboring.")
        return

    user_data = await state.get_data()
    fullname = user_data.get("fullname") or message.from_user.full_name

    payload = {
        "id": message.from_user.id,    
        "tg_id": message.from_user.id, 
        "fullname": fullname,
        "phone": normalized
    }

    saved = await save_user(payload)  
    if not saved:
        await message.answer("❌ Ma'lumotlarni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
        return

    await state.clear()
    keyboard = await get_dynamic_main_keyboard(message.from_user.id)

    await message.answer(
        f"✅ Ma’lumotlar saqlandi!\n\n👤 Ism: {saved.fullname or fullname}\n📞 Tel: {saved.phone}",
        reply_markup=keyboard
    )
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "📥Foydalanuvchi ma'lumotlarini o'zgartirish")
async def ask_new_fullname(message: Message, state: FSMContext):
    await message.answer("✏️ Yangi to‘liq ismingizni kiriting:")
    await state.set_state(UserState.waiting_for_new_fullname)


@router.message(UserState.waiting_for_new_fullname)
async def process_new_fullname(message: Message, state: FSMContext):
    await state.update_data(new_fullname=message.text.strip())
    await message.answer("📱 Endi yangi telefon raqamingizni kiriting (+998 bilan):")
    await state.set_state(UserState.waiting_for_new_phone)
    await message.answer(
        "Telefon raqamingizni button orqali yuborishingiz mumkin",
        reply_markup=phone_request_keyboard
    )
    # await message.answer(
    #     "Quyidagi menyudan birini tanlang:",
    #     parse_mode="HTML",
    #     reply_markup=get_main_menu()
    # )

@router.message(UserState.waiting_for_new_phone, F.content_type.in_({"text", "contact"}))
async def process_new_phone(message: types.Message, state: FSMContext):

    phone = None
    if message.contact and getattr(message.contact, "phone_number", None):
        phone = message.contact.phone_number
    elif message.text:
        phone = message.text.strip()
    else:
        await message.answer(
            "📱 Iltimos, telefon raqamingizni yuboring — matn sifatida (+998901234567) "
            "yoki 'Kontakt yuborish' tugmasi orqali."
        )
        return

    if not phone.startswith("+998") or len(phone) != 13:
        await message.answer("❌ Iltimos, telefon raqamini to‘g‘ri kiriting (masalan: +998901234567).")
        return

    user_data = await state.get_data()
    fullname = user_data.get("new_fullname")

    from sql.db_users_utils import update_user
    success = await update_user(
        user_id=message.from_user.id,
        new_fullname=fullname,
        new_phone=phone
    )

    if success:
        keyboard = await get_dynamic_main_keyboard(message.from_user.id)
        await message.answer(
            f"✅ Ma'lumotlaringiz yangilandi!\n\n👤 Ism: {fullname}\n📱 Telefon: {phone}",
            reply_markup=keyboard
        )
    else:
        await message.answer("❌ Ma'lumotni yangilashda xatolik yuz berdi.")

    await state.clear()
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "❌ Foydalanuvchi ma'lumotlarini o‘chirish")
async def delete_user_data(message: types.Message):
    user_id = message.from_user.id
    deleted = await delete_user(user_id)
    keyboard = await get_dynamic_main_keyboard(user_id)

    if deleted:
        await message.answer("🗑 Foydalanuvchi ma'lumotlari muvaffaqiyatli o‘chirildi!", reply_markup=keyboard)
    else:
        await message.answer("⚠️ Foydalanuvchi topilmadi yoki o‘chirishda xatolik yuz berdi.")

    await message.answer("Quyidagi menyudan birini tanlang:", reply_markup=get_main_menu())

