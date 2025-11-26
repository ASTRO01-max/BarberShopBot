# admins/add_barbers.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from utils.states import AdminStates
from sqlalchemy import select
from sql.db import async_session
from sql.models import Barbers
from sql.models import OrdinaryUser

router = Router()


# --- 1️⃣ Boshlanish ---
@router.message(F.text == "👨‍🎤 Barber qo'shish")
async def add_barber_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.adding_barber_fullname)
    await message.answer("🧔‍♂️ Yangi barberning to‘liq ismini kiriting:")


# --- 2️⃣ To‘liq ismni olish ---
@router.message(StateFilter(AdminStates.adding_barber_fullname))
async def add_barber_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if len(fullname.split()) < 2:
        return await message.answer("❌ Iltimos to‘liq ism (Ism Familiya) kiriting.")

    first_name, last_name = fullname.split(" ", 1)

    async with async_session() as session:

        q = select(Barbers).where(Barbers.barber_first_name.ilike(f"%{fullname}%"))
        existing = (await session.execute(q)).scalars().first()
        if existing:
            return await message.answer("⚠️ Bu ismga o‘xshash barber allaqachon mavjud.")

        u = select(OrdinaryUser).where(
            OrdinaryUser.first_name.ilike(f"%{first_name}%"),
            OrdinaryUser.last_name.ilike(f"%{last_name}%")
        )
        user = (await session.execute(u)).scalars().first()

        tg_id = user.tg_id if user else None

    await state.update_data(fullname=fullname, tg_id=tg_id)
    await state.set_state(AdminStates.adding_barber_phone)
    await message.answer("📞 Barber telefon raqamini kiriting (masalan: +998901234567):")


# --- 3️⃣ Telefon raqamini olish ---
@router.message(StateFilter(AdminStates.adding_barber_phone))
async def add_barber_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    if not phone.startswith("+998") or len(phone) != 13 or not phone[1:].isdigit():
        return await message.answer("❌ Telefon raqam formati noto‘g‘ri. Namuna: +998901234567")

    await state.update_data(phone=phone)
    await state.set_state(AdminStates.adding_barber_experience)
    await message.answer("💼 Barberning ish tajribasini kiriting (masalan: 3 yil, 5 oy):")


# --- 4️⃣ Tajribani olish ---
@router.message(StateFilter(AdminStates.adding_barber_experience))
async def add_barber_experience(message: types.Message, state: FSMContext):
    experience = message.text.strip()
    if len(experience) < 2:
        return await message.answer("❌ Tajriba ma’lumoti juda qisqa. Qaytadan kiriting:")

    await state.update_data(experience=experience)
    await state.set_state(AdminStates.adding_barber_work_days)
    await message.answer("📅 Barberning ish kunlarini kiriting (masalan: Dushanba–Juma):")


# --- 5️⃣ Ish kunlarini olish va foto kerakligini so'rash ---
@router.message(StateFilter(AdminStates.adding_barber_work_days))
async def add_barber_work_days(message: types.Message, state: FSMContext):
    work_days = message.text.strip()
    if len(work_days) < 3:
        return await message.answer("❌ Ish kunlari noto‘g‘ri kiritildi. Qaytadan kiriting:")

    await state.update_data(work_days=work_days)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Ha ✅", callback_data="add_photo_yes"),
            InlineKeyboardButton(text="Yo‘q ❌", callback_data="add_photo_no"),
        ]
    ])

    await message.answer("🖼 Barber uchun rasm qo‘shasizmi?", reply_markup=markup)
    await state.set_state(AdminStates.adding_photo_choice)


# --- Callback: admin "Yo'q" tanlasa (rasmsiz saqlash) ---
@router.callback_query(F.data == "add_photo_no", StateFilter(AdminStates.adding_photo_choice))
async def save_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fullname = data.get("fullname")
    phone = data.get("phone")
    experience = data.get("experience")
    work_days = data.get("work_days")

    if not (fullname and phone and experience and work_days):
        await call.answer("❌ Ma'lumotlar yetarli emas. Iltimos jarayonni qayta boshlang.", show_alert=True)
        await state.clear()
        return

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=fullname,
            phone=phone,
            experience=experience,
            work_days=work_days,
            photo=None
        )
        session.add(new_barber)
        await session.commit()

    await call.message.answer(
        f"✅ Rasm qo‘shilmasdan barber saqlandi!\n\n"
        f"👨‍🎤 <b>{fullname}</b>\n"
        f"📞 <b>{phone}</b>\n"
        f"💼 <b>{experience}</b>\n"
        f"📅 <b>{work_days}</b>",
        parse_mode="HTML"
    )

    await state.clear()
    await call.answer()


# --- Callback: admin "Ha" tanlasa (rasm yuborish bosqichi) ---
@router.callback_query(F.data == "add_photo_yes", StateFilter(AdminStates.adding_photo_choice))
async def ask_for_photo(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_barber_photo)
    await call.message.answer("🖼 Iltimos, barberning rasmini yuboring (JPG/PNG):")
    await call.answer()


# --- 6️⃣ Rasmni qabul qilish va BARCHA ma’lumotni bir martada SQLga yozish ---
@router.message(StateFilter(AdminStates.adding_barber_photo), F.photo)
async def add_barber_photo(message: types.Message, state: FSMContext):
    photo_file = message.photo[-1]
    file = await message.bot.get_file(photo_file.file_id)
    photo_stream = await message.bot.download_file(file.file_path)
    photo_bytes = photo_stream.read()

    data = await state.get_data()
    fullname = data.get("fullname")
    phone = data.get("phone")
    experience = data.get("experience")
    work_days = data.get("work_days")

    if not (fullname and phone and experience and work_days):
        await message.answer("❌ Ma'lumotlar yetarli emas. Iltimos jarayonni qayta boshlang.")
        await state.clear()
        return

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=fullname,
            phone=phone,
            experience=experience,
            work_days=work_days,
            photo=photo_bytes
        )
        session.add(new_barber)
        await session.commit()

    await message.answer(
        f"✅ Rasm bilan barber qo‘shildi!\n\n"
        f"👨‍🎤 <b>{fullname}</b>\n"
        f"📞 <b>{phone}</b>\n"
        f"💼 <b>{experience}</b>\n"
        f"📅 <b>{work_days}</b>",
        parse_mode="HTML"
    )

    await state.clear()


# Optional: fallback — agar admin rasm yuborish o'rniga boshqa matn yuborsa
@router.message(StateFilter(AdminStates.adding_barber_photo))
async def photo_expected_but_got_text(message: types.Message, state: FSMContext):
    await message.answer("❌ Iltimos rasm yuboring yoki 'Yo‘q ❌' tugmasini bosib rasm qo‘shmaslikni tanlang.")
