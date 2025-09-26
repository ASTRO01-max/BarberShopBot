from aiogram import F, types, Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from utils.states import UserState, UserForm
from database.order_utils import delete_last_order_by_user, load_orders
from keyboards.main_menu import get_main_menu
from utils.validators import validate_fullname, validate_phone
from database.users_utils import save_user, update_user, get_user
from datetime import datetime

router = Router()

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
    """Foydalanuvchining bugungi buyurtmalarini ko‘rsatadi."""
    user_id = str(message.from_user.id)
    orders = load_orders()

    # Foydalanuvchiga tegishli buyurtmalar
    user_orders = [o for o in orders if str(o.get("user_id")) == user_id]

    if not user_orders:
        await message.answer("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")
    todays_orders = [o for o in user_orders if o.get("date") == today]

    if not todays_orders:
        # Bugungi buyurtma yo‘q → Inline button chiqadi
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📂 Oldingi buyurtmalarni ko'rish",
                                      callback_data="show_all_orders")]
            ]
        )
        await message.answer("❌ Siz bugun buyurtma qilmadingiz.", reply_markup=markup)
        return

    # Bugungi buyurtmalarni chiqarish
    response_lines = ["🗂 *Bugungi buyurtmalaringiz:*\n"]
    for idx, order in enumerate(todays_orders, start=1):
        sana = order.get("date", "Nomaʼlum")
        vaqt = order.get("time", "Nomaʼlum")
        barber = order.get("barber") or order.get("barber_id", "Nomaʼlum")
        xizmat = order.get("service") or order.get("service_id", "Nomaʼlum")

        response_lines.append(
            f"{idx}. 📅 {sana}, ⏰ {vaqt}\n"
            f"   💈 Barber: {barber}\n"
            f"   ✂️ Xizmat: {xizmat}\n"
        )

    await message.answer("\n".join(response_lines), parse_mode="Markdown")


@router.callback_query(F.data == "show_all_orders")
async def show_all_orders(callback: CallbackQuery):
    """Foydalanuvchining barcha buyurtmalarini ko‘rsatadi."""
    user_id = str(callback.from_user.id)
    orders = load_orders()

    user_orders = [o for o in orders if str(o.get("user_id")) == user_id]

    if not user_orders:
        await callback.message.edit_text("🛒 Sizda hech qanday buyurtma topilmadi.")
        return

    response_lines = ["🗂 *Sizning barcha buyurtmalaringiz:*\n"]
    for idx, order in enumerate(user_orders, start=1):
        sana = order.get("date", "Nomaʼlum")
        vaqt = order.get("time", "Nomaʼlum")
        barber = order.get("barber") or order.get("barber_id", "Nomaʼlum")
        xizmat = order.get("service") or order.get("service_id", "Nomaʼlum")

        response_lines.append(
            f"{idx}. 📅 {sana}, ⏰ {vaqt}\n"
            f"   💈 Barber: {barber}\n"
            f"   ✂️ Xizmat: {xizmat}\n"
        )

    await callback.message.edit_text("\n".join(response_lines), parse_mode="Markdown")
    await callback.answer()

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
    if not phone.startswith("+998") or len(phone) != 13:
        await message.answer("❌ Telefon raqam noto‘g‘ri. Masalan: +998901234567")
        return

    user_data = await state.get_data()
    new_fullname = user_data.get("new_fullname")

    success = update_user(
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
