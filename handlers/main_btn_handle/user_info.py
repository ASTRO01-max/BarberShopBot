# handlers/main_btn_handle/user_info.py
import re
from typing import Optional

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from keyboards.main_menu import get_main_menu
from sql.db_users_utils import delete_user, get_user, save_user, update_user
from utils.states import UserForm, UserState
from utils.validators import validate_fullname, validate_phone

router = Router()


def get_user_database_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ma'lumotlarini o'chirish", callback_data="user_delete")],
            [InlineKeyboardButton(text="📥 Ma'lumotlarini o'zgartirish", callback_data="user_edit")],
        ]
    )


def _normalize_phone(phone_raw: Optional[str]) -> Optional[str]:
    if not phone_raw:
        return None

    digits = re.sub(r"\D", "", phone_raw)
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if len(digits) == 9:
        return f"+998{digits}"
    if phone_raw.startswith("+") and len(digits) >= 9:
        return f"+{digits}"
    return None


@router.message(F.text.in_({"📥Foydalanuvchini saqlash", "📥 Foydalanuvchini saqlash"}))
async def ask_fullname(message: types.Message, state: FSMContext):
    await state.set_state(UserForm.fullname)
    await message.answer("👤 To'liq ismingizni kiriting:")


@router.message(UserForm.fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    fullname = (message.text or "").strip()
    if not validate_fullname(fullname):
        await message.answer("❌ Ism noto'g'ri formatda.")
        return

    await state.update_data(fullname=fullname)
    await state.set_state(UserForm.phone)
    await message.answer("📞 Telefon raqamingizni kiriting (+998 bilan)")
    await message.answer(
        "Telefon raqamingizni button orqali yuborishingiz mumkin",
        reply_markup=phone_request_keyboard,
    )


@router.message(UserForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone_raw = None
    if message.contact and getattr(message.contact, "phone_number", None):
        phone_raw = message.contact.phone_number
    elif message.text:
        phone_raw = message.text.strip()
    else:
        await message.answer(
            "📱 Iltimos telefon raqamingizni yuboring - matn sifatida (+998901234567) yoki 'Kontakt yuborish' tugmasi orqali."
        )
        return

    normalized = _normalize_phone(phone_raw)
    if not normalized or not validate_phone(normalized):
        await message.answer(
            "❌ Telefon raqami noto'g'ri. Iltimos +998901234567 formatida yuboring yoki Kontakt yuboring."
        )
        return

    user_data = await state.get_data()
    fullname = user_data.get("fullname") or message.from_user.full_name

    payload = {
        "id": message.from_user.id,
        "tg_id": message.from_user.id,
        "fullname": fullname,
        "phone": normalized,
    }

    saved = await save_user(payload)
    if not saved:
        await message.answer("❌ Ma'lumotlarni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
        return

    await state.clear()
    keyboard = await get_dynamic_main_keyboard(message.from_user.id)

    await message.answer(
        f"✅ Ma'lumotlar saqlandi!\n\n👤 Ism: {saved.fullname or fullname}\n📞 Tel: {saved.phone}",
        reply_markup=keyboard,
    )
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )


@router.message(F.text.in_({"📥 Foydalanuvchi ma'lumotlari", "📥Foydalanuvchi ma'lumotlari"}))
async def show_user_database_actions(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        keyboard = await get_dynamic_main_keyboard(message.from_user.id)
        await message.answer("⚠️ Saqlangan ma'lumot topilmadi.", reply_markup=keyboard)
        return

    await state.clear()
    fullname = user.fullname or "Kiritilmagan"
    phone = user.phone or "Kiritilmagan"
    user_db_id = user.id if user.id is not None else "Kiritilmagan"
    user_tg_id = user.tg_id if user.tg_id is not None else message.from_user.id

    await message.answer(
        "📄 Foydalanuvchi ma'lumotlari:\n\n"
        f"🆔 ID: {user_db_id}\n"
        f"🆔 Telegram ID: {user_tg_id}\n"
        f"👤 To'liq ism: {fullname}\n"
        f"📞 Telefon: {phone}\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=get_user_database_inline_keyboard(),
    )

    # await message.answer(
    #     "Quyidagi amallardan birini tanlang:",
    #     reply_markup=get_user_database_inline_keyboard(),
    # )


@router.callback_query(F.data == "user_delete")
async def delete_user_data_inline(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    deleted = await delete_user(user_id)
    keyboard = await get_dynamic_main_keyboard(user_id)

    if deleted:
        await callback.message.answer(
            "🗑 Foydalanuvchi ma'lumotlari muvaffaqiyatli o'chirildi!",
            reply_markup=keyboard,
        )
    else:
        await callback.message.answer(
            "⚠️ Saqlangan foydalanuvchi ma'lumoti topilmadi.",
            reply_markup=keyboard,
        )

    await callback.message.answer("Quyidagi menyudan birini tanlang:", reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "user_edit")
async def start_user_edit_inline(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        keyboard = await get_dynamic_main_keyboard(callback.from_user.id)
        await callback.message.answer("⚠️ Saqlangan foydalanuvchi ma'lumoti topilmadi.", reply_markup=keyboard)
        await callback.answer("Ma'lumot topilmadi", show_alert=True)
        return

    await state.set_state(UserState.waiting_for_new_fullname)
    await callback.message.answer("✏️ Yangi to'liq ismingizni kiriting:")
    await callback.answer()


@router.message(UserState.waiting_for_new_fullname)
async def process_new_fullname(message: Message, state: FSMContext):
    new_fullname = (message.text or "").strip()
    if not validate_fullname(new_fullname):
        await message.answer("❌ Ism noto'g'ri formatda.")
        return

    await state.update_data(new_fullname=new_fullname)
    await message.answer("📱 Endi yangi telefon raqamingizni kiriting (+998 bilan):")
    await state.set_state(UserState.waiting_for_new_phone)
    await message.answer(
        "Telefon raqamingizni button orqali yuborishingiz mumkin",
        reply_markup=phone_request_keyboard,
    )


@router.message(UserState.waiting_for_new_phone, F.content_type.in_({"text", "contact"}))
async def process_new_phone(message: types.Message, state: FSMContext):
    phone_raw = None
    if message.contact and getattr(message.contact, "phone_number", None):
        phone_raw = message.contact.phone_number
    elif message.text:
        phone_raw = message.text.strip()
    else:
        await message.answer(
            "📱 Iltimos, telefon raqamingizni yuboring - matn sifatida (+998901234567) yoki 'Kontakt yuborish' tugmasi orqali."
        )
        return

    normalized_phone = _normalize_phone(phone_raw)
    if not normalized_phone or not validate_phone(normalized_phone):
        await message.answer("❌ Iltimos, telefon raqamini to'g'ri kiriting (masalan: +998901234567).")
        return

    user_data = await state.get_data()
    fullname = user_data.get("new_fullname")

    success = await update_user(
        user_id=message.from_user.id,
        new_fullname=fullname,
        new_phone=normalized_phone,
    )

    if success:
        keyboard = await get_dynamic_main_keyboard(message.from_user.id)
        await message.answer(
            f"✅ Ma'lumotlaringiz yangilandi!\n\n👤 Ism: {fullname}\n📱 Telefon: {normalized_phone}",
            reply_markup=keyboard,
        )
    else:
        await message.answer("❌ Ma'lumotni yangilashda xatolik yuz berdi.")

    await state.clear()
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "❌ Foydalanuvchi ma'lumotlarini o'chirish")
async def delete_user_data(message: types.Message):
    user_id = message.from_user.id
    deleted = await delete_user(user_id)
    keyboard = await get_dynamic_main_keyboard(user_id)

    if deleted:
        await message.answer("🗑 Foydalanuvchi ma'lumotlari muvaffaqiyatli o'chirildi!", reply_markup=keyboard)
    else:
        await message.answer("⚠️ Foydalanuvchi topilmadi yoki o'chirishda xatolik yuz berdi.", reply_markup=keyboard)

    await message.answer("Quyidagi menyudan birini tanlang:", reply_markup=get_main_menu())
