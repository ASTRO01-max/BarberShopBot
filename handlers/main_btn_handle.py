#handlers/main_btn_handle.py
import re
from aiogram import F, types, Router
from datetime import date
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, and_
from sql.db import async_session
from sql.models import Order, Services, Barbers
from utils.states import UserState, UserForm
from sql.db_users_utils import save_user, delete_user
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from utils.validators import validate_fullname, validate_phone

router = Router()
USER_ORDERS_PER_PAGE = 5
CANCEL_ORDERS_PER_PAGE = 1


# def _to_int(value):
#     try:
#         return int(value)
#     except (TypeError, ValueError):
#         return None


# async def _prepare_order_cards(orders):
#     if not orders:
#         return []

#     service_ids = {_to_int(o.service_id) for o in orders}
#     service_ids.discard(None)
#     barber_ids = {_to_int(o.barber_id) for o in orders}
#     barber_ids.discard(None)

#     services_by_id = {}
#     barbers_by_id = {}
#     async with async_session() as session:
#         if service_ids:
#             result = await session.execute(select(Services).where(Services.id.in_(service_ids)))
#             services_by_id = {s.id: s for s in result.scalars().all()}
#         if barber_ids:
#             result = await session.execute(select(Barbers).where(Barbers.id.in_(barber_ids)))
#             barbers_by_id = {b.id: b for b in result.scalars().all()}

#     order_cards = []
#     for o in orders:
#         service_id = _to_int(o.service_id)
#         service_name = (
#             services_by_id[service_id].name
#             if service_id is not None and service_id in services_by_id
#             else str(o.service_id)
#         )

#         barber_name = (getattr(o, "barber_id_name", "") or "").strip()
#         if not barber_name:
#             barber_id = _to_int(o.barber_id)
#             if barber_id is not None and barber_id in barbers_by_id:
#                 barber = barbers_by_id[barber_id]
#                 barber_name = " ".join(
#                     part for part in [barber.barber_first_name, barber.barber_last_name] if part
#                 ).strip()
#                 barber_name = barber_name or str(o.barber_id)
#             else:
#                 barber_name = str(o.barber_id)

#         date_text = o.date.strftime("%Y-%m-%d") if hasattr(o.date, "strftime") else str(o.date)
#         time_text = o.time.strftime("%H:%M") if hasattr(o.time, "strftime") else str(o.time)

#         order_cards.append(
#             {
#                 "date": date_text,
#                 "time": time_text,
#                 "barber": barber_name,
#                 "service": service_name,
#             }
#         )

#     return order_cards


# async def _fetch_user_orders(user_id: int, only_today: bool = False):
#     async with async_session() as session:
#         query = select(Order).where(Order.user_id == user_id)
#         if only_today:
#             query = query.where(Order.booked_date == date.today())
#         query = query.order_by(Order.booked_date.desc(), Order.booked_time.desc(), Order.id.desc())
#         result = await session.execute(query)
#         return result.scalars().all()


# def get_user_orders_page(order_cards, page: int):
#     """
#     Foydalanuvchi buyurtmalarini sahifalab chiqarish
#     """
#     start = page * USER_ORDERS_PER_PAGE
#     end = start + USER_ORDERS_PER_PAGE
#     sliced = order_cards[start:end]

#     text = "📋 *Sizning barcha buyurtmalaringiz:*\n\n"
#     for idx, o in enumerate(sliced, start=start + 1):
#         text += (
#             f"📌 *Buyurtma {idx}*\n"
#             f"📅 Sana: {o['date']}\n"
#             f"⏰ Vaqt: {o['time']}\n"
#             f"💈 Barber: {o['barber']}\n"
#             f"✂️ Xizmat: {o['service']}\n\n"
#         )

    # Tugmalar (pagination + qaytish)
#     buttons = []
#     if page > 0:
#         buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"user_prev:{page-1}"))
#     if end < len(order_cards):
#         buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"user_next:{page+1}"))

#     nav_row = buttons if buttons else []
#     back_row = [InlineKeyboardButton(text="📂 Bugungi buyurtmalarga qaytish", callback_data="back_to_today")]

#     inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, back_row] if nav_row else [back_row])
#     return text, inline_kb


# def _format_dt(value, fmt):
#     return value.strftime(fmt) if hasattr(value, "strftime") else str(value)


# def _prepare_cancel_order_cards(orders):
#     cards = []
#     for o in orders:
#         cards.append(
#             {
#                 "id": o.id,
#                 "user_id": o.user_id,
#                 "fullname": o.fullname,
#                 "phonenumber": o.phonenumber,
#                 "service_id": o.service_id,
#                 "barber_id_name": o.barber_id_name,
#                 "date": _format_dt(o.date, "%Y-%m-%d"),
#                 "time": _format_dt(o.time, "%H:%M"),
#                 "booked_date": _format_dt(o.booked_date, "%Y-%m-%d"),
#                 "booked_time": _format_dt(o.booked_time, "%H:%M"),
#             }
#         )
#     return cards


# def get_cancel_orders_page(order_cards, page: int):
#     start = page * CANCEL_ORDERS_PER_PAGE
#     end = start + CANCEL_ORDERS_PER_PAGE
#     sliced = order_cards[start:end]
#     if not sliced:
#         return "🛒 Buyurtmalar topilmadi.", InlineKeyboardMarkup(inline_keyboard=[])

#     o = sliced[0]
#     total_pages = (len(order_cards) - 1) // CANCEL_ORDERS_PER_PAGE + 1

#     text = (
#         "❌ *Bekor qilinadigan buyurtma:*\n"
#         f"📄 Sahifa: {page + 1}/{total_pages}\n"
#         f"🆔 ID: {o['id']}\n\n"
#         f"👤 Mijoz: {o['fullname']}\n"
#         f"📞 Tel: {o['phonenumber']}\n"
#         f"🧾 Xizmat ID: {o['service_id']}\n"
#         f"💈 Barber: {o['barber_id_name']}\n"
#         f"📅 Sana: {o['date']}\n"
#         f"⏰ Vaqt: {o['time']}\n"
#         f"🗓️ Buyurtma sanasi: {o['booked_date']}\n"
#         f"🕒 Buyurtma vaqti: {o['booked_time']}\n"
#     )

#     buttons = []
#     if page > 0:
#         buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"cancel_prev:{page-1}"))
#     if end < len(order_cards):
#         buttons.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"cancel_next:{page+1}"))

#     nav_row = buttons if buttons else []
#     action_row = [
#         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order:{o['id']}")
#     ]

#     inline_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row, action_row] if nav_row else [action_row])
#     return text, inline_kb


# 🟢 1️⃣ Asosiy "🗂Buyurtmalar tarixi" bosilganda — bugun joylashtirilgan buyurtmalarni ko‘rsatadi
# @router.message(F.text == "🗂Buyurtmalar tarixi")
# async def show_user_orders(message: Message):
#     user_id = message.from_user.id
#     todays_orders = await _fetch_user_orders(user_id, only_today=True)
#     if not todays_orders:
#         all_orders = await _fetch_user_orders(user_id, only_today=False)
#         if not all_orders:
#             await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
#             return

#         markup = InlineKeyboardMarkup(
#             inline_keyboard=[
#                 [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
#             ]
#         )
#         await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
#         return

#     order_cards = await _prepare_order_cards(todays_orders)

    # 🔸 Agar bugun joylashtirilgan buyurtmalar mavjud bo‘lsa
#     response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
#     for idx, o in enumerate(order_cards, start=1):
#         response_lines.append(
#             f"{idx}. 📅 {o['date']}, ⏰ {o['time']}\n"
#             f"   💈 Barber: {o['barber']}\n"
#             f"   ✂️ Xizmat: {o['service']}\n"
#         )

#     markup = InlineKeyboardMarkup(
#         inline_keyboard=[
#             [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
#         ]
#     )

#     await message.answer("\n".join(response_lines), parse_mode="Markdown", reply_markup=markup)


# 🟢 2️⃣ Barcha buyurtmalar (pagination bilan)
# @router.callback_query(F.data == "show_all_orders")
# async def show_all_orders(callback: CallbackQuery, state: FSMContext):
#     user_id = callback.from_user.id
#     user_orders = await _fetch_user_orders(user_id)
#     if not user_orders:
#         await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
#         await callback.answer()
#         return

#     order_cards = await _prepare_order_cards(user_orders)
#     page = 0
#     text, markup = get_user_orders_page(order_cards, page)
#     await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
#     await state.update_data(order_cards=order_cards, current_page=page)
#     await callback.answer()


# 🟢 3️⃣ Pagination tugmalari uchun
# @router.callback_query(F.data.startswith(("user_next", "user_prev")))
# async def paginate_user_orders(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     order_cards = data.get("order_cards", [])
#     if not order_cards:
#         await callback.answer("⚠️ Buyurtmalar topilmadi", show_alert=True)
#         return

#     page = int(callback.data.split(":")[1])
#     text, markup = get_user_orders_page(order_cards, page)
#     await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
#     await state.update_data(current_page=page)
#     await callback.answer()


# 🟢 4️⃣ "Bugungi buyurtmalarga qaytish" tugmasi uchun
# @router.callback_query(F.data == "back_to_today")
# async def back_to_today(callback: CallbackQuery):
#     user_id = callback.from_user.id
#     todays_orders = await _fetch_user_orders(user_id, only_today=True)

#     markup = InlineKeyboardMarkup(
#         inline_keyboard=[
#             [InlineKeyboardButton(text="📁 Barcha buyurtmalarni ko‘rish", callback_data="show_all_orders")]
#         ]
#     )

#     if not todays_orders:
#         await callback.message.edit_text("❌ Bugun joylashtirilgan buyurtma topilmadi.", reply_markup=markup)
#         await callback.answer()
#         return

#     order_cards = await _prepare_order_cards(todays_orders)

#     response_lines = ["🗂 *Bugun joylashtirilgan buyurtmalaringiz:*\n"]
#     for idx, o in enumerate(order_cards, start=1):
#         response_lines.append(
#             f"{idx}. 📅 {o['date']}, ⏰ {o['time']}\n"
#             f"   💈 Barber: {o['barber']}\n"
#             f"   ✂️ Xizmat: {o['service']}\n"
#         )

#     await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown", reply_markup=markup)
#     await callback.answer()


# @router.message(F.text == "❌Buyurtmani bekor qilish")
# async def show_todays_orders_for_cancel(message: types.Message, state: FSMContext):
#     user_id = message.from_user.id
#     today = date.today()

    # 🔹 Foydalanuvchining bugun joylagan barcha buyurtmalarini olish (navbat sanasidan qat’i nazar)
#     async with async_session() as session:
#         result = await session.execute(
#             select(Order).where(
#                 and_(Order.user_id == user_id, Order.booked_date == today)
#             )
#         )
#         orders = result.scalars().all()

    # 🔹 Agar bugungi buyurtma topilmasa
#     if not orders:
#         keyboard = await get_dynamic_main_keyboard(user_id)
#         await message.answer(
#             "❗ Sizda bugun joylagan bekor qilinadigan buyurtma topilmadi.",
#             reply_markup=keyboard
#         )
#         await message.answer(
#             "Quyidagi menyudan birini tanlang:",
#             parse_mode="HTML",
#             reply_markup=get_main_menu()
#         )
#         return
    # Bugun joylagan barcha buyurtmalarni chiqarish
#     order_cards = _prepare_cancel_order_cards(orders)
#     page = 0
#     text, markup = get_cancel_orders_page(order_cards, page)
#     await message.answer(text, parse_mode="Markdown", reply_markup=markup)
#     await state.update_data(cancel_order_cards=order_cards, cancel_current_page=page)


# Tugma bosilganda — buyurtmani bekor qilish
# @router.callback_query(F.data.startswith("cancel_order:"))
# async def cancel_order_callback(callback: CallbackQuery):
#     try:
#         order_id = int(callback.data.split(":")[1])
#     except (IndexError, ValueError):
#         return await callback.answer("❌ Xatolik: noto‘g‘ri ID.", show_alert=True)

#     async with async_session() as session:
#         order = await session.get(Order, order_id)
#         if not order:
#             await callback.answer("❗ Bu buyurtma allaqachon bekor qilingan.", show_alert=True)
#             return

#         await session.delete(order)
#         await session.commit()

#     await callback.message.edit_text(
#         f"✅ Buyurtma bekor qilindi!\n\n"
#         f"📅 Sana: {order.date}\n"
#         f"⏰ Vaqt: {order.time}"
#     )
#     await callback.answer("Buyurtma muvaffaqiyatli o‘chirildi ✅")

#     keyboard = await get_dynamic_main_keyboard(callback.from_user.id)
#     await callback.message.answer(
#         "Quyidagi menyudan birini tanlang:",
#         parse_mode="HTML",
#         reply_markup=get_main_menu()
#     )



# @router.callback_query(F.data.startswith(("cancel_next", "cancel_prev")))
# async def paginate_cancel_orders(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     order_cards = data.get("cancel_order_cards", [])
#     if not order_cards:
#         await callback.answer("?? Buyurtmalar topilmadi", show_alert=True)
#         return

#     page = int(callback.data.split(":")[1])
#     text, markup = get_cancel_orders_page(order_cards, page)
#     await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
#     await state.update_data(cancel_current_page=page)
#     await callback.answer()


# @router.message(F.text == "📥Foydalanuvchini saqlash")
# async def ask_fullname(message: types.Message, state: FSMContext):
#     await state.set_state(UserForm.fullname)
#     await message.answer("👤 To‘liq ismingizni kiriting:")


# @router.message(UserForm.fullname)
# async def process_fullname(message: types.Message, state: FSMContext):
#     fullname = message.text.strip()
#     if not validate_fullname(fullname):
#         await message.answer("❌ Ism noto‘g‘ri formatda.")
#         return
#     await state.update_data(fullname=fullname)
#     await state.set_state(UserForm.phone)
#     await message.answer("📞 Telefon raqamingizni kiriting (+998 bilan)")
#     await message.answer(
#         "Telefon raqamingizni button orqali yuborishingiz mumkin",
#         reply_markup=phone_request_keyboard
#     )

# @router.message(UserForm.phone)
# async def process_phone(message: types.Message, state: FSMContext):
#     phone_raw = None
#     if message.contact and getattr(message.contact, "phone_number", None):
#         phone_raw = message.contact.phone_number
#     elif message.text:
#         phone_raw = message.text.strip()
#     else:
#         await message.answer("📱 Iltimos telefon raqamingizni yuboring — matn sifatida (+998901234567) yoki 'Kontakt yuborish' tugmasi orqali.")
#         return

#     digits = re.sub(r"\D", "", phone_raw) 
#     normalized = None

#     if phone_raw.startswith("+") and len(digits) >= 9:
#         normalized = "+" + digits
#     elif digits.startswith("998") and len(digits) >= 12:
#         normalized = "+" + digits
#     elif digits.startswith("0") and len(digits) == 9:
#         normalized = "+998" + digits[1:]
#     else:
#         normalized = "+" + digits
#     if not validate_phone(normalized):
#         await message.answer("❌ Telefon raqami noto‘g‘ri. Iltimos +998901234567 formatida yuboring yoki Kontakt yuboring.")
#         return

#     user_data = await state.get_data()
#     fullname = user_data.get("fullname") or message.from_user.full_name

#     payload = {
#         "id": message.from_user.id,    
#         "tg_id": message.from_user.id, 
#         "fullname": fullname,
#         "phone": normalized
#     }

#     saved = await save_user(payload)  
#     if not saved:
#         await message.answer("❌ Ma'lumotlarni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
#         return

#     await state.clear()
#     keyboard = await get_dynamic_main_keyboard(message.from_user.id)

#     await message.answer(
#         f"✅ Ma’lumotlar saqlandi!\n\n👤 Ism: {saved.fullname or fullname}\n📞 Tel: {saved.phone}",
#         reply_markup=keyboard
#     )
#     await message.answer(
#         "Quyidagi menyudan birini tanlang:",
#         parse_mode="HTML",
#         reply_markup=get_main_menu()
#     )

# @router.message(F.text == "📥Foydalanuvchi ma'lumotlarini o'zgartirish")
# async def ask_new_fullname(message: Message, state: FSMContext):
#     await message.answer("✏️ Yangi to‘liq ismingizni kiriting:")
#     await state.set_state(UserState.waiting_for_new_fullname)


# @router.message(UserState.waiting_for_new_fullname)
# async def process_new_fullname(message: Message, state: FSMContext):
#     await state.update_data(new_fullname=message.text.strip())
#     await message.answer("📱 Endi yangi telefon raqamingizni kiriting (+998 bilan):")
#     await state.set_state(UserState.waiting_for_new_phone)
#     await message.answer(
#         "Telefon raqamingizni button orqali yuborishingiz mumkin",
#         reply_markup=phone_request_keyboard
#     )
    # await message.answer(
    #     "Quyidagi menyudan birini tanlang:",
    #     parse_mode="HTML",
    #     reply_markup=get_main_menu()
    # )

# @router.message(UserState.waiting_for_new_phone, F.content_type.in_({"text", "contact"}))
# async def process_new_phone(message: types.Message, state: FSMContext):

#     phone = None
#     if message.contact and getattr(message.contact, "phone_number", None):
#         phone = message.contact.phone_number
#     elif message.text:
#         phone = message.text.strip()
#     else:
#         await message.answer(
#             "📱 Iltimos, telefon raqamingizni yuboring — matn sifatida (+998901234567) "
#             "yoki 'Kontakt yuborish' tugmasi orqali."
#         )
#         return

#     if not phone.startswith("+998") or len(phone) != 13:
#         await message.answer("❌ Iltimos, telefon raqamini to‘g‘ri kiriting (masalan: +998901234567).")
#         return

#     user_data = await state.get_data()
#     fullname = user_data.get("new_fullname")

#     from sql.db_users_utils import update_user
#     success = await update_user(
#         user_id=message.from_user.id,
#         new_fullname=fullname,
#         new_phone=phone
#     )

#     if success:
#         keyboard = await get_dynamic_main_keyboard(message.from_user.id)
#         await message.answer(
#             f"✅ Ma'lumotlaringiz yangilandi!\n\n👤 Ism: {fullname}\n📱 Telefon: {phone}",
#             reply_markup=keyboard
#         )
#     else:
#         await message.answer("❌ Ma'lumotni yangilashda xatolik yuz berdi.")

#     await state.clear()
#     await message.answer(
#         "Quyidagi menyudan birini tanlang:",
#         parse_mode="HTML",
#         reply_markup=get_main_menu()
#     )

# @router.message(F.text == "❌ Foydalanuvchi ma'lumotlarini o‘chirish")
# async def delete_user_data(message: types.Message):
#     user_id = message.from_user.id
#     deleted = await delete_user(user_id)
#     keyboard = await get_dynamic_main_keyboard(user_id)

#     if deleted:
#         await message.answer("🗑 Foydalanuvchi ma'lumotlari muvaffaqiyatli o‘chirildi!", reply_markup=keyboard)
#     else:
#         await message.answer("⚠️ Foydalanuvchi topilmadi yoki o‘chirishda xatolik yuz berdi.")

#     await message.answer("Quyidagi menyudan birini tanlang:", reply_markup=get_main_menu())

