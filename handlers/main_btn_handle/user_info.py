#handlers/main_btn_handle/user_info.py
import re

from aiogram import F, Router, types
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from keyboards.main_menu import get_main_menu
from sql.db_users_utils import save_user, delete_user
from utils.states import UserState, UserForm
from utils.validators import validate_fullname, validate_phone

router = Router()

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

