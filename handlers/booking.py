#handlers/booking.py
import logging
import re
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
from sql.db_users_utils import get_user, save_user
from sql.db_order_utils import get_booked_times, save_order
from superadmins.order_realtime_notify import notify_barber_realtime
from utils.states import UserState
from aiogram.filters import StateFilter
from utils.validators import parse_user_date

logger = logging.getLogger(__name__)
router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


@router.message(
    StateFilter(
        UserState.waiting_for_fullname,
        UserState.waiting_for_phonenumber,
        UserState.waiting_for_service,
        UserState.waiting_for_barber,
        UserState.waiting_for_date,
        UserState.waiting_for_time,        
    ),
    F.text.startswith("/cancel"),
)

async def cancel_booking(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Navbat olish jarayoni bekor qilindi.\n\n🏠 Asosiy menyuga qaytdingiz.",
        reply_markup=get_main_menu(),
    )

# --- 1-qadam: Boshlash ---
async def start_booking(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await get_user(user_id)

    if user:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=with_cancel_hint("💈 Xizmat turini tanlang:"),
                reply_markup=await booking_keyboards.service_keyboard()
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("💈 Xizmat turini tanlang:"),
                reply_markup=await booking_keyboards.service_keyboard()
            )

        await state.set_state(UserState.waiting_for_service)

    else:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=with_cancel_hint("Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):")
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):")
            )

        await state.set_state(UserState.waiting_for_fullname)

    await callback.answer("Navbat olish boshlandi ✅")


# --- Barber orqali boshlash ---
async def start_booking_from_barber(callback: CallbackQuery, state: FSMContext):
    barber_id = callback.data.split("_")[2]
    user_id = callback.from_user.id

    # Barber tanlovini saqlab qo'yamiz (keyingi step1 da kerak bo'ladi)
    await state.update_data(barber_id=barber_id)

    user = await get_user(user_id)

    if user:
        text = with_cancel_hint("💈 Xizmat turini tanlang:")
        keyboard = await booking_keyboards.service_keyboard()

        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)

        await state.set_state(UserState.waiting_for_service)
        await callback.answer("🧑‍🎤 Barber tanlandi, navbat boshlandi ✅")

    else:
        text = with_cancel_hint("Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):")

        if callback.message.photo:
            await callback.message.edit_caption(caption=text)
        else:
            await callback.message.edit_text(text)

        await state.set_state(UserState.waiting_for_fullname)
        await callback.answer("🧑‍🎤 Barber tanlandi, ro'yxatdan o'tish boshlandi ✅")


# --- Service orqali boshlash ---
async def start_booking_from_service(callback: CallbackQuery, state: FSMContext):
    # callback_data: book_service_{service_name}
    service_id = callback.data.split("_", 2)[2]  # "Soch olish" kabi nomlar
    user_id = callback.from_user.id

    # Service tanlovini saqlab qo'yamiz (keyingi step2/step3 uchun)
    await state.update_data(service_id=service_id)

    user = await get_user(user_id)

    if user:
        text = with_cancel_hint("💈 Barberni tanlang:")
        keyboard = await booking_keyboards.barber_keyboard(service_id)

        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)

        await state.set_state(UserState.waiting_for_barber)
        await callback.answer("💈 Xizmat tanlandi, navbat boshlandi ✅")

    else:
        text = with_cancel_hint("Iltimos, to‘liq ismingizni kiriting (masalan: Aliyev Valijon):")

        if callback.message.photo:
            await callback.message.edit_caption(caption=text)
        else:
            await callback.message.edit_text(text)

        # service_id saqlangan, user ro'yxatdan o'tgach siz book_step1/2 oqimini davom ettirasiz
        await state.set_state(UserState.waiting_for_fullname)
        await callback.answer("💈 Xizmat tanlandi, ro'yxatdan o'tish boshlandi ✅")



# --- 2-qadam: Ism ---
async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip()

    if len(fullname.split()) < 2:
        await message.answer(
            with_cancel_hint("❗ Iltimos, ism va familiyani to‘liq kiriting (masalan: Aliyev Valijon).")
        )
        return

    await state.update_data(fullname=fullname)

    await message.answer(
        with_cancel_hint("📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:"),
        reply_markup=phone_request_keyboard
    )

    await state.set_state(UserState.waiting_for_phonenumber)


# --- 3-qadam: Telefon ---
async def process_phonenumber(message: Message, state: FSMContext):
    raw_phone = None

    if message.contact and message.contact.phone_number:
        raw_phone = message.contact.phone_number
    elif message.text:
        raw_phone = message.text.strip()

    if not raw_phone:
        await message.answer(with_cancel_hint("❌ Iltimos, telefon raqamini yuboring (masalan: +998901234567)."))
        return

    digits = re.sub(r"\D", "", raw_phone)

    # Mobil Telegram ko'pincha: "998901234567" ko'rinishida yuboradi
    if digits.startswith("998") and len(digits) == 12:
        phonenumber = f"+{digits}"
    # Ba'zan foydalanuvchi 9 xonali lokal format yuborishi mumkin: "901234567"
    elif len(digits) == 9:
        phonenumber = f"+998{digits}"
    else:
        phonenumber = None

    if not phonenumber or not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer(
            with_cancel_hint("❌ Iltimos, telefon raqamini to‘g‘ri kiriting (masalan: +998901234567).")
        )
        return

    data = await state.get_data()
    fullname = data.get("fullname") or message.from_user.full_name or "Ism kiritilmagan"

    await state.update_data(fullname=fullname, phonenumber=phonenumber)

    await message.answer(
        "📱 Raqamingiz qabul qilindi ✅",
        reply_markup=await get_dynamic_main_keyboard(message.from_user.id)
    )

    await message.answer(
        with_cancel_hint("💈 Endi xizmat turini tanlang:"),
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
                caption=with_cancel_hint("📅 Sana tanlang:"),
                reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("📅 Sana tanlang:"),
                reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
            )

        await state.set_state(UserState.waiting_for_date)
        await callback.answer("💈 Xizmat turi tanlandi ✅")
        return

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=with_cancel_hint("💈 Barberni tanlang:"),
            reply_markup=await booking_keyboards.barber_keyboard(service_id)
        )
    else:
        await callback.message.edit_text(
            with_cancel_hint("💈 Barberni tanlang:"),
            reply_markup=await booking_keyboards.barber_keyboard(service_id)
        )

    await state.set_state(UserState.waiting_for_barber)
    await callback.answer("💈 Xizmat turi tanlandi ✅")


# --- 5-qadam: Barber ---
async def book_step2(callback: CallbackQuery, state: FSMContext):
    _, service_id, barber_id = callback.data.split("_")[:3]

    await state.update_data(
        service_id=service_id,
        barber_id=barber_id
    )

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
        )
    else:
        await callback.message.edit_text(
            with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
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
                caption=with_cancel_hint("❌ Kechirasiz, bu kunga barcha vaqtlar band."),
                reply_markup=back_markup
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("❌ Kechirasiz, bu kunga barcha vaqtlar band."),
                reply_markup=back_markup
            )
    else:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=with_cancel_hint("⏰ Vaqt tanlang:"),
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("⏰ Vaqt tanlang:"),
                reply_markup=keyboard
            )

    await state.set_state(
        UserState.waiting_for_date if keyboard is None else UserState.waiting_for_time
    )
    await callback.answer("📅 Sana qabul qilindi ✅")


# --- Sana (matn) ---
@router.message(UserState.waiting_for_date)
async def book_step3_message(message: Message, state: FSMContext):
    date = parse_user_date(message.text.strip())

    if not date:
        await message.answer(
            with_cancel_hint("❌ Kechirasiz, biz faqat joriy oy ichidagi sanalarni qabul qilamiz.")
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
        await message.answer(with_cancel_hint("❌ Bu kunda bo‘sh vaqt yo‘q."))
        return

    await message.answer(with_cancel_hint("⏰ Vaqtni tanlang:"), reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_time)


# --- Orqaga ---
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id)
        )
    else:
        await callback.message.edit_text(
            with_cancel_hint("📅 Sana tanlang:"),
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

    # 1️⃣ UI: bosilgan vaqt tugmasini olib tashlash
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

    booked_times = await get_booked_times(barber_id, date_str)
    if time_str in booked_times:
        await callback.answer(
            "⛔ Ushbu vaqt hozirgina band bo‘ldi.\nBoshqa vaqt tanlang.",
            show_alert=True
        )
        return

    # 3️⃣ Foydalanuvchi ma’lumotlari
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

    # Faqat to'liq ma'lumot bo'lsa users jadvaliga upsert qilamiz.
    if fullname != "Noma'lum" and phone != "Noma'lum":
        saved_user = await save_user(
            {
                "tg_id": user_id,
                "fullname": fullname,
                "phone": phone,
            }
        )
        if saved_user:
            fullname = saved_user.fullname or fullname
            phone = saved_user.phone or phone

    # 4️⃣ Buyurtmani DB ga saqlash
    order = {
        "user_id": user_id,
        "fullname": fullname,
        "phonenumber": phone,
        "service_id": service_id,
        "barber_id": barber_id,
        "date": date_str,
        "time": time_str,
    }

    created = await save_order(order)
    try:
        await notify_barber_realtime(callback.bot, created.id, int(barber_id))
    except Exception:
        logger.exception("notify_barber_realtime failed")

    # 5️⃣ Natijani foydalanuvchiga ko‘rsatish
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
    await callback.answer("⏰ Vaqt tanlandi ✅")
    await callback.message.answer(
        "📱 Menyu yangilandi:",
        reply_markup=await get_dynamic_main_keyboard(user_id),
    )
    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )
    
