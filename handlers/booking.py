import logging
from aiogram import types, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from keyboards import booking_keyboards
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import phone_request_keyboard, get_dynamic_main_keyboard
from sql.db_order_utils import save_order
from utils.states import UserState
from utils.validators import *
from sql.db_users_utils import get_user, save_user
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()

# --- 1-qadam: Boshlash ---
async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    """Agar foydalanuvchi bazada bo‘lsa → xizmat tanlash bosqichiga o‘tadi, aks holda ism so‘raladi."""
    user_id = callback.from_user.id
    user = await get_user(user_id)

    if user:
        # ✅ Bazada mavjud foydalanuvchi → xizmat tanlashga o‘tadi
        await callback.message.edit_text(
            "💈 Xizmat turini tanlang:",
            reply_markup=await booking_keyboards.service_keyboard()
        )
        await state.set_state(UserState.waiting_for_service)
    else:
        # 🆕 Yangi foydalanuvchi → ism so‘raladi
        await callback.message.edit_text(
            "Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):"
        )
        await state.set_state(UserState.waiting_for_fullname)

    await callback.answer()


# --- 2-qadam: Foydalanuvchi ism kiritadi ---
async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip()
    if len(fullname.split()) < 2:
        await message.answer("❗ Iltimos, ism va familiyani to‘liq kiriting (masalan: Aliyev Valijon).")
        return

    await state.update_data(fullname=fullname)

    await message.answer(
        "📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:",
        reply_markup=phone_request_keyboard
    )
    await state.set_state(UserState.waiting_for_phonenumber)


# --- 3-qadam: Telefon raqami ---
async def process_phonenumber(message: Message, state: FSMContext):
    """Telefon raqamini tekshirish, saqlash va keyingi bosqichga o‘tish."""
    phonenumber = None
    if message.contact and message.contact.phone_number:
        phonenumber = message.contact.phone_number
    elif message.text:
        phonenumber = message.text.strip()

    # ✅ Validatsiya
    if not phonenumber or not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer("❌ Iltimos, telefon raqamini to‘g‘ri kiriting (masalan: +998901234567).")
        return

    # ✅ Ma’lumotni state ichiga saqlaymiz
    user_data = await state.get_data()
    fullname = user_data.get("fullname", message.from_user.full_name or "Ism kiritilmagan")

    await state.update_data(fullname=fullname, phonenumber=phonenumber)

    # ✅ Keyingi bosqich
    await message.answer("📱 Raqamingiz qabul qilindi ✅", reply_markup=await get_dynamic_main_keyboard(message.from_user.id))
    await message.answer("💈 Endi xizmat turini tanlang:", reply_markup=await booking_keyboards.service_keyboard())
    await state.set_state(UserState.waiting_for_service)


# --- 4-qadam: Xizmat tanlash ---
async def book_step1(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split("_")[1]
    await state.update_data(service_id=service_id)
    await callback.message.edit_text(
        "🧑‍🎤 Usta tanlang:",
        reply_markup=await booking_keyboards.barber_keyboard(service_id)
    )
    await state.set_state(UserState.waiting_for_barber)
    await callback.answer()


# --- 5-qadam: Usta tanlash ---
# --- 5-qadam: Usta tanlash ---
async def book_step2(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("⚠️ Ma’lumot formati noto‘g‘ri. Iltimos, qayta tanlang.", show_alert=True)
        return

    _, service_id, barber_id = parts[:3]
    await state.update_data(service_id=service_id, barber_id=barber_id)

    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()



# --- 6-qadam: Sana tanlash ---
async def book_step3(callback: CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date = callback.data.split("_")
    await state.update_data(date=date)

    keyboard = await booking_keyboards.time_keyboard(service_id, barber_id, date)

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
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")
    await callback.message.edit_text(
        "📅 Sana tanlang:",
        reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
    )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer()

# ✅ Tasdiqlash bosqichi
@router.callback_query(F.data.startswith("confirm_"))
async def confirm(callback: types.CallbackQuery, state: FSMContext):
    """Buyurtmani yakuniy tasdiqlash — foydalanuvchidan to‘plangan barcha ma’lumotlarni DB ga saqlaydi."""
    data = callback.data or ""
    if not data.startswith("confirm_"):
        await callback.answer()
        return

    parts = data.split("_", 4)
    if len(parts) != 5:
        await callback.message.answer("⚠️ So'rov formati noto‘g‘ri. Iltimos, menyudan qayta tanlang.")
        await callback.answer()
        return

    _, service_id, barber_id, date_str, time_str = parts
    user_id = callback.from_user.id

    # 1️⃣ State’dagi ma’lumotlar
    user_state = await state.get_data()
    fullname = user_state.get("fullname")
    phone = user_state.get("phonenumber") or user_state.get("phone")

    # 2️⃣ Agar state bo‘sh bo‘lsa — DB'dan olish
    if not fullname or not phone:
        try:
            user = await get_user(user_id)
            if user:
                fullname = fullname or getattr(user, "fullname", None)
                phone = phone or getattr(user, "phone", None)
        except Exception as e:
            logger.exception("get_user xatoligi: %s", e)

    fullname = fullname or "Noma'lum"
    phone = phone or "Noma'lum"

    # 3️⃣ Sana va vaqtni formatlash
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        date_obj = date_str

    try:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
    except Exception:
        time_obj = time_str

    # 4️⃣ Buyurtma ma’lumotlarini tayyorlash
    order = {
        "user_id": user_id,
        "fullname": fullname,
        "phonenumber": phone,
        "service_id": service_id,
        "barber_id": barber_id,
        "date": date_obj,
        "time": time_obj,
    }

    # 5️⃣ DB'ga saqlash
    try:
        await save_order(order)
    except Exception as e:
        logger.exception("DB save error: %s", e)
        await callback.message.answer(
            "❌ Buyurtmangizni saqlashda xato yuz berdi. Iltimos, keyinroq urinib ko‘ring."
        )
        await callback.answer()
        return

    # 6️⃣ Foydalanuvchiga natijani ko‘rsatish
    await callback.message.edit_text(
        f"✅ <b>Buyurtmangiz muvaffaqiyatli saqlandi!</b>\n\n"
        f"👤 <b>Ism:</b> {fullname}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"💈 <b>Xizmat:</b> {service_id}\n"
        f"👨‍💼 <b>Usta:</b> {barber_id}\n"
        f"📅 <b>Sana:</b> {date_str}\n"
        f"🕔 <b>Vaqt:</b> {time_str}",
        parse_mode="HTML"
    )

    await state.clear()

    # 🟩 Shu joyda — ekranning o‘rtasida “✅ Tasdiqlandi” chiqadi va yo‘qoladi
    await callback.answer("✅ Navbat olindi", show_alert=False)

    # 🎉 Yakuniy xabar (chatga yuboriladi)
    await callback.message.answer(
        "🎉 <b>Rahmat!</b> Sizning buyurtmangiz qabul qilindi.\n"
        "Usta siz bilan belgilangan vaqtda bog‘lanadi.\n\n"
        "🏠 Asosiy menyuga qaytish uchun pastdagi tugmadan foydalaning:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
