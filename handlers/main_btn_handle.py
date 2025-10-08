import re
from aiogram import F, types, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime

from utils.states import UserState, UserForm
from sql.db_order_utils import delete_last_order_by_user, load_orders
from sql.db_users_utils import save_user, update_user, delete_user, get_user
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from utils.validators import validate_fullname, validate_phone

router = Router()

# ❌ Buyurtmani bekor qilish
@router.message(F.text == "❌Buyurtmani bekor qilish")
async def cancel_last_order(message: Message):
    user_id = message.from_user.id
    deleted_order = await delete_last_order_by_user(user_id)

    if deleted_order:
        await message.answer(
            f"✅ Eng so‘nggi buyurtmangiz bekor qilindi:\n"
            f"📅 Sana: {deleted_order.date}\n"
            f"⏰ Vaqt: {deleted_order.time}\n"
            f"💇‍♂️ Barber ID: {deleted_order.barber_id}\n"
            f"🛎 Xizmat ID: {deleted_order.service_id}"
        )
    else:
        await message.answer("❗ Sizda bekor qilinadigan buyurtma topilmadi.")
        keyboard = await get_dynamic_main_keyboard(message.from_user.id)
        await message.answer("Asosiy menyu:", reply_markup=keyboard)


# 🗂 Buyurtmalar tarixi
@router.message(F.text == "🗂Buyurtmalar tarixi")
async def show_user_orders(message: Message):
    user_id = message.from_user.id
    orders = await load_orders()
    user_orders = [o for o in orders if o.user_id == user_id]

    if not user_orders:
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    today = datetime.now().date()
    todays_orders = [o for o in user_orders if o.date == today]

    if not todays_orders:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📂 Oldingi buyurtmalarni ko'rish", callback_data="show_all_orders")]
            ]
        )
        await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
        return

    response_lines = ["🗂 *Bugungi buyurtmalaringiz:*\n"]
    for idx, o in enumerate(todays_orders, start=1):
        response_lines.append(
            f"{idx}. 📅 {o.date}, ⏰ {o.time}\n"
            f"   💈 Barber: {o.barber_id}\n"
            f"   ✂️ Xizmat: {o.service_id}\n"
        )

    await message.answer("\n".join(response_lines), parse_mode="Markdown")


# 📂 Oldingi buyurtmalar
@router.callback_query(F.data == "show_all_orders")
async def show_all_orders(callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = await load_orders()
    user_orders = [o for o in orders if o.user_id == user_id]

    if not user_orders:
        await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    response_lines = ["🗂 *Sizning barcha buyurtmalaringiz:*\n"]
    for idx, o in enumerate(user_orders, start=1):
        response_lines.append(
            f"{idx}. 📅 {o.date}, ⏰ {o.time}\n"
            f"   💈 Barber: {o.barber_id}\n"
            f"   ✂️ Xizmat: {o.service_id}\n"
        )

    await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown")
    await callback.answer()


# ✅ Foydalanuvchini saqlash
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
    """
    Telefonni qabul qiladi — text ham contact orqali kelishini qo'llab-quvvatlaydi.
    """
    # 1) contact bor-yo'qligini tekshiramiz
    phone_raw = None
    if message.contact and getattr(message.contact, "phone_number", None):
        phone_raw = message.contact.phone_number
    elif message.text:
        phone_raw = message.text.strip()
    else:
        # Hech narsa yo'q — foydalanuvchini to'g'ri yuborishga yo'naltiramiz
        await message.answer("📱 Iltimos telefon raqamingizni yuboring — matn sifatida (+998901234567) yoki 'Kontakt yuborish' tugmasi orqali.")
        return

    # 2) normalize: faqat raqamlarni olib, + qo'shish / +998 formatga o'tkazish harakatlari
    digits = re.sub(r"\D", "", phone_raw)  # faqat raqamlar
    normalized = None

    if phone_raw.startswith("+") and len(digits) >= 9:
        normalized = "+" + digits
    elif digits.startswith("998") and len(digits) >= 12:
        normalized = "+" + digits
    elif digits.startswith("0") and len(digits) == 9:
        # mahalliy format: 0901234567 -> +998901234567
        normalized = "+998" + digits[1:]
    else:
        # umumiy fallback: + +digits
        normalized = "+" + digits

    # 3) validate (agar sizning validate_phone +998 formatini tekshirsa)
    if not validate_phone(normalized):
        await message.answer("❌ Telefon raqami noto‘g‘ri. Iltimos +998901234567 formatida yuboring yoki Kontakt yuboring.")
        return

    # 4) state dan boshqa ma'lumotlarni olamiz
    user_data = await state.get_data()
    # Agar state-da fullname mavjud bo'lmasa, fallback qilib Telegram full_name qo'yish mumkin:
    fullname = user_data.get("fullname") or message.from_user.full_name

    # 5) DB uchun dict tayyorlash — `save_user` sizning yangi versiyangizga mos
    payload = {
        "id": message.from_user.id,     # eski kodlarga mos kelishi uchun
        "tg_id": message.from_user.id,  # db_users_utils ichida ishlatiladi
        "fullname": fullname,
        "phone": normalized
    }

    saved = await save_user(payload)  # async, ichida session ishlatiladi
    if not saved:
        await message.answer("❌ Ma'lumotlarni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
        return

    # 6) state tozalaymiz va menyuni yangilaymiz
    await state.clear()
    keyboard = await get_dynamic_main_keyboard(message.from_user.id)

    await message.answer(
        f"✅ Ma’lumotlar saqlandi!\n\n👤 Ism: {saved.fullname or fullname}\n📞 Tel: {saved.phone}",
        reply_markup=keyboard
    )

# 📥 Foydalanuvchi ma’lumotlarini o‘zgartirish
@router.message(F.text == "📥Foydalanuvchi ma'lumotlarini o'zgartirish")
async def ask_new_fullname(message: Message, state: FSMContext):
    await message.answer("✏️ Yangi to‘liq ismingizni kiriting:")
    await state.set_state(UserState.waiting_for_new_fullname)


@router.message(UserState.waiting_for_new_fullname)
async def process_new_fullname(message: Message, state: FSMContext):
    await state.update_data(new_fullname=message.text.strip())
    await message.answer("📱 Endi yangi telefon raqamingizni kiriting (+998 bilan):")
    await state.set_state(UserState.waiting_for_new_phone)


@router.message(UserState.waiting_for_new_phone)
async def process_new_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer("❌ Telefon raqam noto‘g‘ri. Masalan: +998901234567")
        return

    user_data = await state.get_data()
    new_fullname = user_data.get("new_fullname")

    success = await update_user(
        user_id=message.from_user.id,
        new_fullname=new_fullname,
        new_phone=phone
    )

    if success:
        await message.answer(
            f"✅ Ma'lumotlaringiz yangilandi!\n\n"
            f"👤 Ism: {new_fullname}\n"
            f"📱 Telefon: {phone}"
        )
    else:
        await message.answer("❌ Foydalanuvchi topilmadi yoki xatolik yuz berdi.")

    await state.clear()
    keyboard = await get_dynamic_main_keyboard(message.from_user.id)
    await message.answer("Asosiy menyu:", reply_markup=keyboard)


# ❌ Foydalanuvchi ma'lumotlarini o'chirish
@router.message(F.text == "❌ Foydalanuvchi ma'lumotlarini o‘chirish")
async def delete_user_data(message: types.Message):
    user_id = message.from_user.id
    deleted = await delete_user(user_id)

    if deleted:
        await message.answer("🗑 Foydalanuvchi ma'lumotlari muvaffaqiyatli o‘chirildi!")
    else:
        await message.answer("⚠️ Foydalanuvchi topilmadi yoki o‘chirishda xatolik yuz berdi.")

    keyboard = await get_dynamic_main_keyboard(user_id)
    await message.answer("Asosiy menyu:", reply_markup=keyboard)
