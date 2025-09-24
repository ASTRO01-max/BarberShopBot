from aiogram import types
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database.static_data import services, barbers
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import booking_keyboards
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import phone_request_keyboard, get_dynamic_main_keyboard
from database.order_utils import save_order
from utils.states import UserState
from utils.validators import *
from database.users_utils import save_user, get_user


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

    await message.answer("Raqamingiz qabul qilindi ✅", reply_markup=get_dynamic_main_keyboard(message.from_user.id))
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
