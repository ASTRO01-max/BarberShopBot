#handlers/booking.py
import logging
from datetime import datetime

from aiogram import types, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.fsm.context import FSMContext

from keyboards import booking_keyboards
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import phone_request_keyboard, get_dynamic_main_keyboard
from sql.db_order_utils import save_order
from sql.db_users_utils import get_user
from sql.db_barbers import get_barbers

from utils.states import UserState
from utils.validators import parse_user_date

logger = logging.getLogger(__name__)
router = Router()


# --- 1-qadam: Boshlash ---
async def start_booking(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await get_user(user_id)

    if user:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption="💈 Xizmat turini tanlang:",
                reply_markup=await booking_keyboards.service_keyboard()
            )
        else:
            await callback.message.edit_text(
                "💈 Xizmat turini tanlang:",
                reply_markup=await booking_keyboards.service_keyboard()
            )

        await state.set_state(UserState.waiting_for_service)

    else:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption="Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):"
            )
        else:
            await callback.message.edit_text(
                "Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):"
            )

        await state.set_state(UserState.waiting_for_fullname)

    await callback.answer("Navbat olish boshlandi ✅")


# --- Barber orqali boshlash ---
async def start_booking_from_barber(callback: CallbackQuery, state: FSMContext):
    barber_id = callback.data.split("_")[2]
    user_id = callback.from_user.id

    await state.update_data(barber_id=barber_id)

    text = "💈 Xizmat turini tanlang:"
    keyboard = await booking_keyboards.service_keyboard()

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=text,
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard
        )

    await state.set_state(UserState.waiting_for_service)
    await callback.answer("🧑‍🎤 Barber tanlandi, navbat boshlandi ✅")


# --- 2-qadam: Ism ---
async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip()

    if len(fullname.split()) < 2:
        await message.answer(
            "❗ Iltimos, ism va familiyani to‘liq kiriting (masalan: Aliyev Valijon)."
        )
        return

    await state.update_data(fullname=fullname)

    await message.answer(
        "📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:",
        reply_markup=phone_request_keyboard
    )

    await state.set_state(UserState.waiting_for_phonenumber)


# --- 3-qadam: Telefon ---
async def process_phonenumber(message: Message, state: FSMContext):
    phonenumber = None

    if message.contact and message.contact.phone_number:
        phonenumber = message.contact.phone_number
    elif message.text:
        phonenumber = message.text.strip()

    if not phonenumber or not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer(
            "❌ Iltimos, telefon raqamini to‘g‘ri kiriting (masalan: +998901234567)."
        )
        return

    data = await state.get_data()
    fullname = data.get("fullname") or message.from_user.full_name or "Ism kiritilmagan"

    await state.update_data(
        fullname=fullname,
        phonenumber=phonenumber
    )

    await message.answer(
        "📱 Raqamingiz qabul qilindi ✅",
        reply_markup=await get_dynamic_main_keyboard(message.from_user.id)
    )

    await message.answer(
        "💈 Endi xizmat turini tanlang:",
        reply_markup=await booking_keyboards.service_keyboard()
    )

    await state.set_state(UserState.waiting_for_service)


# --- 4-qadam: Xizmat ---
async def book_step1(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split("_")[1]
    data = await state.get_data()

    await state.update_data(service_id=service_id)

    if "barber_id" in data:
        barber_id = data["barber_id"]

        if callback.message.photo:
            await callback.message.edit_caption(
                caption="📅 Sana tanlang:",
                reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
            )
        else:
            await callback.message.edit_text(
                "📅 Sana tanlang:",
                reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
            )

        await state.set_state(UserState.waiting_for_date)
        await callback.answer("🧑‍🎤 Barber avtomatik tanlandi ✅")
        return

    if callback.message.photo:
        await callback.message.edit_caption(
            caption="💈 Barberni tanlang:",
            reply_markup=await booking_keyboards.barber_keyboard(service_id)
        )
    else:
        await callback.message.edit_text(
            "💈 Barberni tanlang:",
            reply_markup=await booking_keyboards.barber_keyboard(service_id)
        )

    await state.set_state(UserState.waiting_for_barber)


# --- 5-qadam: Barber ---
async def book_step2(callback: CallbackQuery, state: FSMContext):
    _, service_id, barber_id = callback.data.split("_")[:3]

    await state.update_data(
        service_id=service_id,
        barber_id=barber_id
    )

    if callback.message.photo:
        await callback.message.edit_caption(
            caption="📅 Sana tanlang:",
            reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
        )
    else:
        await callback.message.edit_text(
            "📅 Sana tanlang:",
            reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
        )

    await state.set_state(UserState.waiting_for_date)
    await callback.answer("💈 Barber tanlandi ✅")


# --- 6-qadam: Sana (callback) ---
async def book_step3(callback: CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date = callback.data.split("_")
    await state.update_data(date=date)

    keyboard = await booking_keyboards.time_keyboard(service_id, barber_id, date)

    if keyboard is None:
        back_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Orqaga",
                        callback_data=f"back_date_{service_id}_{barber_id}"
                    )
                ]
            ]
        )

        if callback.message.photo:
            await callback.message.edit_caption(
                caption="❌ Kechirasiz, bu kunga barcha vaqtlar band.",
                reply_markup=back_markup
            )
        else:
            await callback.message.edit_text(
                "❌ Kechirasiz, bu kunga barcha vaqtlar band.",
                reply_markup=back_markup
            )
    else:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption="⏰ Vaqt tanlang:",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                "⏰ Vaqt tanlang:",
                reply_markup=keyboard
            )

    await state.set_state(UserState.waiting_for_time)
    await callback.answer("📅 Sana qabul qilindi ✅")


# --- Sana (matn) ---
@router.message(UserState.waiting_for_date)
async def book_step3_message(message: Message, state: FSMContext):
    date = parse_user_date(message.text.strip())

    if not date:
        await message.answer(
            "❌ Kechirasiz, biz faqat joriy oy ichidagi sanalarni qabul qilamiz."
        )
        return

    await state.update_data(date=date)

    data = await state.get_data()
    keyboard = await booking_keyboards.time_keyboard(
        data["service_id"],
        data["barber_id"],
        date
    )

    if keyboard is None:
        await message.answer("❌ Bu kunda bo‘sh vaqt yo‘q.")
        return

    await message.answer("⏰ Vaqtni tanlang:", reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_time)


# --- Orqaga ---
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")

    if callback.message.photo:
        await callback.message.edit_caption(
            caption="📅 Sana tanlang:",
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
        )
    else:
        await callback.message.edit_text(
            "📅 Sana tanlang:",
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
        )

    await state.set_state(UserState.waiting_for_date)
    await callback.answer("🔙 Orqaga qaytildi")


# --- Tasdiqlash ---
@router.callback_query(F.data.startswith("confirm_"))
async def confirm(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    _, service_id, barber_id, date_str, time_str = data.split("_", 4)
    user_id = callback.from_user.id

    # ===============================
    # 1️⃣ UI: bosilgan vaqt tugmasini olib tashlash
    # ===============================
    markup = callback.message.reply_markup
    if markup and markup.inline_keyboard:
        new_keyboard = [
            [btn for btn in row if btn.callback_data != data]
            for row in markup.inline_keyboard
            if any(btn.callback_data != data for btn in row)
        ]
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard)
        )

    # ===============================
    # 2️⃣ DB: vaqt band emasligini tekshirish
    # ===============================
    from sql.db_order_utils import get_booked_times

    booked_times = await get_booked_times(barber_id, date_str)
    if time_str in booked_times:
        await callback.answer(
            "⛔ Ushbu vaqt hozirgina band bo‘ldi.\nBoshqa vaqt tanlang.",
            show_alert=True
        )
        return

    # ===============================
    # 3️⃣ Foydalanuvchi ma’lumotlari
    # ===============================
    user_data = await state.get_data()
    fullname = user_data.get("fullname")
    phone = user_data.get("phonenumber")

    if not fullname or not phone:
        user = await get_user(user_id)
        if user:
            fullname = fullname or user.fullname
            phone = phone or user.phone

    fullname = fullname or "Noma'lum"
    phone = phone or "Noma'lum"

    # ===============================
    # 4️⃣ Buyurtmani DB ga saqlash
    # ===============================
    order = {
        "user_id": user_id,
        "fullname": fullname,
        "phonenumber": phone,
        "service_id": service_id,
        "barber_id": barber_id,
        "date": date_str,
        "time": time_str,
    }

    await save_order(order)

    # ===============================
    # 5️⃣ Natijani foydalanuvchiga ko‘rsatish
    # ===============================
    text = (
        "✅ <b>Buyurtmangiz muvaffaqiyatli saqlandi!</b>\n\n"
        f"👤 <b>Ism:</b> {fullname}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"💈 <b>Xizmat:</b> {service_id}\n"
        f"👨‍💼 <b>Usta:</b> {barber_id}\n"
        f"📅 <b>Sana:</b> {date_str}\n"
        f"🕔 <b>Vaqt:</b> {time_str}"
    )

    # 🔑 MUHIM JOY
    if callback.message.photo:
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML"
        )

    await state.clear()
    await callback.answer("✅ Navbat olindi")

    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )





