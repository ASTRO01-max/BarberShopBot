from aiogram import types
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database.static_data import services, barbers
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import booking_keyboards
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import phone_request_keyboard, get_dynamic_main_keyboard
from sql.db_order_utils import save_order
from utils.states import UserState
from utils.validators import *
from database.users_utils import save_user, get_user

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

    # ✅ JSON emas, endi PostgreSQL ga saqlanadi
    await save_order(order)

    await callback.message.edit_text(
        f"✅ Siz muvaffaqiyatli navbat oldingiz:\n"
        f"👤 Ismingiz: {fullname}\n"
        f"📱 Telefon: {phone}\n"
        f"💈 Xizmat: {service_name}\n"
        f"👨‍💼 Usta: {barber_name}\n"
        f"🗓 Sana: {date}\n"
        f"🕔 Vaqt: {time}"
    )

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "Quyidagi menyudan birini tanlang:",
        reply_markup=get_main_menu()
    )
