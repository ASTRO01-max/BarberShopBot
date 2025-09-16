from aiogram import F, types, Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database.static_data import services, barbers
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import booking_keyboards
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import phone_request_keyboard, keyboard
from database.order_utils import get_booked_times, save_order, delete_last_order_by_user
from utils.states import UserState, UserForm
from utils.validators import *
from database.users_utils import save_user, get_user
import json
import os

# async def start_booking(callback: types.CallbackQuery, state: FSMContext):
#     user_id = callback.from_user.id
#     user = get_user(user_id)

#     if user:
#         # ✅ User mavjud → to‘g‘ridan-to‘g‘ri xizmat tanlash
#         await book_step1()
#     else:
#         # ❌ User mavjud emas → ism so‘raymiz
#         await callback.message.edit_text(
#             "Iltimos, to‘liq ismingizni kiriting (masalan, Aliyev Valijon):"
#         )
#         await state.set_state(UserState.waiting_for_fullname)

#     await callback.answer()


# async def process_fullname(message: types.Message, state: FSMContext):
#     fullname = message.text.strip()
#     if len(fullname.split()) < 2:
#         await message.answer("Iltimos, ism va familiyani kiriting (masalan: Aliyev Valijon).")
#         return

#     await state.update_data(fullname=fullname)

#     await message.answer(
#         "Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:",
#         reply_markup=phone_request_keyboard
#     )
#     await state.set_state(UserState.waiting_for_phonenumber)


# async def process_phonenumber(message: types.Message, state: FSMContext):
#     # Tugma orqali yuborilgan telefon raqamni olish
#     phonenumber = message.contact.phone_number if message.contact else message.text.strip()

#     if not phonenumber.startswith("+998") or len(phonenumber) != 13:
#         await message.answer("Iltimos, telefon raqamini to‘g‘ri kiriting (masalan, +998901234567).")
#         return

#     # State ichidan fullname olish
#     user_data = await state.get_data()
#     fullname = user_data.get("fullname", "Ism kiritilmagan")

#     # Yangi userni faylga saqlash
#     save_user({
#         "id": message.from_user.id,   # Telegram user id
#         "fullname": fullname,
#         "phone": phonenumber
#     })

#     # State ichiga telefonni saqlash
#     await state.update_data(phonenumber=phonenumber)

#     await message.answer("Raqamingiz qabul qilindi ✅", reply_markup=keyboard) 
#     await message.answer(
#         "💈 Xizmat turini tanlang:",
#         reply_markup=booking_keyboards.service_keyboard()
#     )
#     await state.set_state(UserState.waiting_for_service)


# async def book_step1(callback: types.CallbackQuery, state: FSMContext):
#     service_id = callback.data.split("_")[1]
#     await state.update_data(service_id=service_id)
#     await callback.message.edit_text(
#         "🧑‍🎤 Usta tanlang:",
#         reply_markup=booking_keyboards.barber_keyboard(service_id)
#     )
#     await state.set_state(UserState.waiting_for_barber)
#     await callback.answer()

# # 2-bosqich: Sana tanlash
# async def book_step2(callback: types.CallbackQuery, state: FSMContext):
#     _, service_id, barber_id = callback.data.split("_")
#     await state.update_data(service_id=service_id, barber_id=barber_id)

#     await callback.message.edit_text(
#         "📅 Sana tanlang:",
#         reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
#     )
#     await state.set_state(UserState.waiting_for_date)
#     await callback.answer()


# # 3-bosqich: Vaqt tanlash
# async def book_step3(callback: types.CallbackQuery, state: FSMContext):
#     _, service_id, barber_id, date = callback.data.split("_")
#     await state.update_data(date=date)

#     keyboard = booking_keyboards.time_keyboard(service_id, barber_id, date)

#     if keyboard is None:
#         back_markup = InlineKeyboardMarkup(
#             inline_keyboard=[
#                 [InlineKeyboardButton(
#                     text="🔙 Orqaga",
#                     callback_data=f"back_date_{service_id}_{barber_id}"
#                 )]
#             ]
#         )
#         await callback.message.edit_text(
#             "❌ Kechirasiz, bu kunga barcha vaqtlar band.",
#             reply_markup=back_markup
#         )
#     else:
#         await callback.message.edit_text("⏰ Vaqt tanlang:", reply_markup=keyboard)

#     await state.set_state(UserState.waiting_for_time)
#     await callback.answer()


# # Orqaga qaytish handleri
# async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
#     _, _, service_id, barber_id = callback.data.split("_")

#     await callback.message.edit_text(
#         "📅 Sana tanlang:",
#         reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
#     )
#     await state.set_state(UserState.waiting_for_date)
#     await callback.answer()


# async def confirm(callback: types.CallbackQuery, state: FSMContext):
#     _, service_id, barber_id, date, time = callback.data.split("_")
#     user_id = callback.from_user.id
#     user = get_user(user_id)

#     user_data = await state.get_data()

#     # Agar user.json faylida mavjud bo‘lsa undan foydalanamiz
#     if user:
#         fullname = user["fullname"]
#         phone = user["phone"]
#     else:
#         fullname = user_data.get("fullname")
#         phone = user_data.get("phonenumber")

#     service_name = services[service_id][0]
#     barber_name = next((b['name'] for b in barbers if b['id'] == barber_id), "Noma'lum")

#     order = {
#         "user_id": user_id,
#         "fullname": fullname,
#         "phonenumber": phone,
#         "service_id": service_id,
#         "barber_id": barber_id,
#         "date": date,
#         "time": time
#     }
#     save_order(order)

#     await callback.message.edit_text(
#         f"✅ Siz muvaffaqiyatli navbat oldingiz:\n"
#         f"👤Ismingiz: {fullname}\n"
#         f"📱Telefon: {phone}\n"
#         f"💈Xizmat: {service_name}\n"
#         f"👨‍💼Usta: {barber_name}\n"
#         f"🗓Sana: {date}\n"
#         f"🕔Vaqt: {time}"
#     )

#     await state.clear()
#     await callback.answer()

#     await callback.message.answer(
#         "Quyidagi menyudan birini tanlang:",
#         reply_markup=get_main_menu()
#     )


# --- 1-qadam: Boshlash ---
async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = get_user(user_id)

    if user:
        # Agar foydalanuvchi mavjud bo‘lsa → xizmat tanlashdan boshlanadi
        await callback.message.edit_text(
            "💈 Xizmat turini tanlang:",
            reply_markup=booking_keyboards.service_keyboard()
        )
        await state.set_state(UserState.waiting_for_service)
    else:
        # Agar foydalanuvchi yo‘q bo‘lsa → ism so‘raymiz
        await callback.message.edit_text(
            "Iltimos, to‘liq ismingizni kiriting (masalan, Aliyev Valijon):"
        )
        await state.set_state(UserState.waiting_for_fullname)

    await callback.answer()

# --- 2-qadam: Foydalanuvchi ism kiritadi ---
async def process_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if len(fullname.split()) < 2:
        await message.answer("Iltimos, ism va familiyani kiriting (masalan: Aliyev Valijon).")
        return

    await state.update_data(fullname=fullname)

    await message.answer(
        "Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:",
        reply_markup=phone_request_keyboard
    )
    await state.set_state(UserState.waiting_for_phonenumber)

# --- 3-qadam: Telefon raqami ---
async def process_phonenumber(message: types.Message, state: FSMContext):
    phonenumber = message.contact.phone_number if message.contact else message.text.strip()

    if not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer("Iltimos, telefon raqamini to‘g‘ri kiriting (masalan, +998901234567).")
        return

    user_data = await state.get_data()
    fullname = user_data.get("fullname", "Ism kiritilmagan")

    # Foydalanuvchini saqlash
    save_user({
        "id": message.from_user.id,
        "fullname": fullname,
        "phone": phonenumber
    })

    await state.update_data(phonenumber=phonenumber)

    await message.answer("Raqamingiz qabul qilindi ✅", reply_markup=keyboard)
    await message.answer(
        "💈 Xizmat turini tanlang:",
        reply_markup=booking_keyboards.service_keyboard()
    )
    await state.set_state(UserState.waiting_for_service)

# --- 4-qadam: Xizmat tanlash ---
async def book_step1(callback: types.CallbackQuery, state: FSMContext):
    service_id = callback.data.split("_")[1]
    await state.update_data(service_id=service_id)
    await callback.message.edit_text(
        "🧑‍🎤 Usta tanlang:",
        reply_markup=booking_keyboards.barber_keyboard(service_id)
    )
    await state.set_state(UserState.waiting_for_barber)
    await callback.answer()

# --- 5-qadam: Usta tanlash ---
async def book_step2(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id = callback.data.split("_")
    await state.update_data(service_id=service_id, barber_id=barber_id)

    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()

# --- 6-qadam: Sana tanlash ---
async def book_step3(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date = callback.data.split("_")
    await state.update_data(date=date)

    keyboard = booking_keyboards.time_keyboard(service_id, barber_id, date)

    if keyboard is None:
        back_markup = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=f"back_date_{service_id}_{barber_id}"
                )
            ]]
        )
        await callback.message.edit_text(
            "❌ Kechirasiz, bu kunga barcha vaqtlar band.",
            reply_markup=back_markup
        )
    else:
        await callback.message.edit_text("⏰ Vaqt tanlang:", reply_markup=keyboard)

    await state.set_state(UserState.waiting_for_time)
    await callback.answer()

# --- Orqaga qaytish ---
async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")
    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()

# --- 7-qadam: Tasdiqlash ---
async def confirm(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date, time = callback.data.split("_")
    user_id = callback.from_user.id
    user = get_user(user_id)
    user_data = await state.get_data()

    fullname = user["fullname"] if user else user_data.get("fullname")
    phone = user["phone"] if user else user_data.get("phonenumber")

    service_name = services[service_id][0]
    barber_name = next((b['name'] for b in barbers if b['id'] == barber_id), "Noma'lum")

    order = {
        "user_id": user_id,
        "fullname": fullname,
        "phonenumber": phone,
        "service_id": service_id,
        "barber_id": barber_id,
        "date": date,
        "time": time
    }
    save_order(order)

    await callback.message.edit_text(
        f"✅ Siz muvaffaqiyatli navbat oldingiz:\n"
        f"👤Ismingiz: {fullname}\n"
        f"📱Telefon: {phone}\n"
        f"💈Xizmat: {service_name}\n"
        f"👨‍💼Usta: {barber_name}\n"
        f"🗓Sana: {date}\n"
        f"🕔Vaqt: {time}"
    )

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "Quyidagi menyudan birini tanlang:",
        reply_markup=get_main_menu()
    )

router = Router()  # bu kerak

@router.message(F.text == "❌Buyurtmani bekor qilish")
async def cancel_last_order(message: Message):
    user_id = message.from_user.id
    deleted_order = delete_last_order_by_user(user_id)

    if deleted_order:
        await message.answer(
            f"✅ Eng so‘nggi buyurtmangiz bekor qilindi:\n"
            f"📅 Sana: {deleted_order['date']}\n"
            f"⏰ Vaqt: {deleted_order['time']}\n"
            f"💇‍♂️ Barber ID: {deleted_order['barber_id']}\n"
            f"🛎 Xizmat ID: {deleted_order['service_id']}"
        )
    else:
        await message.answer("❗ Sizda bekor qilinadigan buyurtma topilmadi.")

@router.message(F.text == "🗂Buyurtmalar tarixi")
async def show_user_orders(message: Message):
    user_id = message.from_user.id
    orders_file = "database/orders.json" 

    # Fayl mavjud emas bo‘lsa
    if not os.path.exists(orders_file):
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    # Faylni o‘qish
    try:
        with open(orders_file, "r", encoding="utf-8") as file:
            orders = json.load(file)
    except json.JSONDecodeError:
        orders = []


    user_orders = [order for order in orders if str(order.get("user_id")) == str(user_id)]

    if not user_orders:
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return


    response = "🗂 *Sizning buyurtmalaringiz:*\n\n"
    for idx, order in enumerate(user_orders, start=1):
        sana = order.get("date", "Nomaʼlum")
        vaqt = order.get("time", "Nomaʼlum")
        barber = order.get("barber", "Nomaʼlum")
        xizmat = order.get("service", "Nomaʼlum")
        response += f"{idx}. 📅 Sana: {sana}, ⏰ Vaqt: {vaqt}, 💈 Barber: {barber}, ✂️ Xizmat: {xizmat}\n"

    await message.answer(response, parse_mode="Markdown")

@router.message(F.text == "📥Foydalanuvchini saqlash")
async def ask_fullname(message: types.Message, state: FSMContext):
    await state.set_state(UserForm.fullname)
    await message.answer("👤 Iltimos, to‘liq ismingizni kiriting (Masalan: Anvar Karimov)")

@router.message(UserForm.fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if not validate_fullname(fullname):
        await message.answer("❌ Ism noto‘g‘ri formatda. Qaytadan kiriting (Masalan: Ali Valiyev)")
        return
    await state.update_data(fullname=fullname)
    await state.set_state(UserForm.phone)
    await message.answer("📞 Endi telefon raqamingizni kiriting (+998901234567 formatida)")

@router.message(UserForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer("❌ Telefon raqami noto‘g‘ri. Iltimos, +998 bilan boshlang.")
        return

    user_data = await state.get_data()
    user_data["phone"] = phone
    user_data["id"] = message.from_user.id  # ✅ Telegram foydalanuvchi ID qo‘shildi

    save_user(user_data)
    await state.clear()

    await message.answer(
        f"✅ Ma’lumotlar saqlandi!\n\n👤 Ism: {user_data['fullname']}\n📞 Tel: {user_data['phone']}",
        reply_markup=get_main_menu()
    )
