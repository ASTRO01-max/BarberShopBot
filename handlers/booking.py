from aiogram import F, types, Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database.static_data import services, barbers
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import booking_keyboards
from keyboards.main_menu import *
from keyboards.main_buttons import phone_request_keyboard, keyboard
from database.order_utils import get_booked_times, save_order, delete_last_order_by_user
from utils.states import UserState
import json
import os

async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Iltimos, to‘liq ismingizni kiriting (masalan, Aliyev Valijon):"
    )
    await state.set_state(UserState.waiting_for_fullname)
    await callback.answer()

async def process_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if len(fullname.split()) < 2:
        await message.answer("Iltimos, to‘liq ismingizni kiriting (ism va familiya).")
        return
    await state.update_data(fullname=fullname)

    await message.answer(
        "Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:",
        reply_markup=phone_request_keyboard
    )
    await state.set_state(UserState.waiting_for_phonenumber)

async def process_phonenumber(message: types.Message, state: FSMContext):
    # Tugma orqali yuborilgan telefon raqamni olish
    if message.contact:
        phonenumber = message.contact.phone_number
    else:
        phonenumber = message.text.strip()

    if not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer("Iltimos, telefon raqamini to‘g‘ri kiriting (masalan, +998901234567).")
        return

    await state.update_data(phonenumber=phonenumber)
    await message.answer("Raqamingiz qabul qilindi ✅", reply_markup=keyboard) 
    await message.answer(
        "💈 Xizmat turini tanlang:",
        reply_markup=booking_keyboards.service_keyboard()
    )
    await state.set_state(UserState.waiting_for_service)


async def book_step1(callback: types.CallbackQuery, state: FSMContext):
    service_id = callback.data.split("_")[1]
    await state.update_data(service_id=service_id)
    await callback.message.edit_text(
        "🧑‍🎤 Usta tanlang:",
        reply_markup=booking_keyboards.barber_keyboard(service_id)
    )
    await state.set_state(UserState.waiting_for_barber)
    await callback.answer()


# 2-bosqich: Sana tanlash
async def book_step2(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id = callback.data.split("_")
    await state.update_data(service_id=service_id, barber_id=barber_id)

    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()


# 3-bosqich: Vaqt tanlash
async def book_step3(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date = callback.data.split("_")
    await state.update_data(date=date)

    keyboard = booking_keyboards.time_keyboard(service_id, barber_id, date)

    if keyboard is None:
        back_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=f"back_date_{service_id}_{barber_id}"
                )]
            ]
        )
        await callback.message.edit_text(
            "❌ Kechirasiz, bu kunga barcha vaqtlar band.",
            reply_markup=back_markup
        )
    else:
        await callback.message.edit_text("⏰ Vaqt tanlang:", reply_markup=keyboard)

    await state.set_state(UserState.waiting_for_time)
    await callback.answer()


# Orqaga qaytish handleri
async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")

    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()



async def confirm(callback: types.CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date, time = callback.data.split("_")
    user_data = await state.get_data()
    user_id = callback.from_user.id
    service_name = services[service_id][0]
    barber_name = next((b['name'] for b in barbers if b['id'] == barber_id), "Noma'lum")

    order = {
        "user_id": user_id,
        "fullname": user_data["fullname"],
        "phonenumber": user_data["phonenumber"],
        "service_id": service_id,
        "barber_id": barber_id,
        "date": date,
        "time": time
    }
    save_order(order)

    await callback.message.edit_text(
        f"✅ Siz muvaffaqiyatli navbat oldingiz:\n"
        f"👤Ismingiz: {user_data['fullname']}\n"
        f"📱Telefon raqamingiz: {user_data['phonenumber']}\n"
        f"💈Xizmat: {service_name}\n"
        f"👨‍💼Usta: {barber_name}\n"
        f"🗓Sana: {date}\n"
        f"🕔Vaqt: {time}"
    )

    await callback.message.answer(
        f"🕔 Navbatingizni belgilang va o‘z vaqtida keling.\n"
        f"⏳ Navbat bo‘yicha xizmat vaqti belgilangan paytda boshlanadi.\n"
        f"❗15 daqiqa kechikkan taqdirda navbat avtomatik bekor qilinadi va boshqa mijozga o‘tadi."
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
