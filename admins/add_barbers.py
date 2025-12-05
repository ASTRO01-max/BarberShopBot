# admins/add_barbers.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.states import AdminStates
from sqlalchemy import select
from sql.db import async_session
from sql.models import Barbers, OrdinaryUser

router = Router()


# --------------------------- 1) START ----------------------------
@router.message(F.text == "💈 Barber qo'shish")
async def add_barber_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.adding_barber_fullname)

    await message.answer(
        "💈 <b>Yangi barber qo‘shish</b>\n\n"
        "Iltimos barberning <b>to‘liq ismini</b> kiriting.\n"
        "Namuna: <i>Abdulloh Karimov</i>",
        parse_mode="HTML"
    )


# --------------------------- 2) FULLNAME ----------------------------
@router.message(StateFilter(AdminStates.adding_barber_fullname))
async def add_barber_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()

    if len(fullname.split()) < 2:
        return await message.answer("❌ Iltimos, to‘liq ism kiriting (Ism Familiya).")

    first_name, last_name = fullname.split(" ", 1)

    async with async_session() as session:

        existing = await session.execute(
            select(Barbers).where(
                Barbers.barber_first_name.ilike(first_name),
                Barbers.barber_last_name.ilike(last_name)
            )
        )
        if existing.scalar():
            return await message.answer("⚠️ Bu barber allaqachon ro‘yxatda bor.")

        user_query = await session.execute(
            select(OrdinaryUser).where(
                OrdinaryUser.first_name.ilike(first_name),
                OrdinaryUser.last_name.ilike(last_name)
            )
        )
        user = user_query.scalar()

        if not user:
            fallback = await session.execute(
                select(OrdinaryUser).where(
                    OrdinaryUser.first_name.ilike(first_name)
                )
            )
            user = fallback.scalar()

        tg_id = user.tg_id if user else None
        tg_username = user.username if user else None

    await state.update_data(
        first_name=first_name,
        last_name=last_name,
        tg_id=tg_id,
        tg_username=tg_username
    )

    await state.set_state(AdminStates.adding_barber_phone)
    await message.answer(
        f"📞 Endi barberning telefon raqamini kiriting.\n\n"
        f"🔎 <b>Telegramdan topildi:</b> <code>{tg_id if tg_id else 'Topilmadi'}</code>",
        parse_mode="HTML"
    )


# --------------------------- 3) PHONE ----------------------------
@router.message(StateFilter(AdminStates.adding_barber_phone))
async def add_barber_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    if not phone.startswith("+998") or len(phone) != 13 or not phone[1:].isdigit():
        return await message.answer(
            "❌ Telefon raqam noto‘g‘ri.\n"
            "Namuna: <b>+998901234567</b>",
            parse_mode="HTML"
        )

    await state.update_data(phone=phone)
    await state.set_state(AdminStates.adding_barber_experience)

    await message.answer(
        "💼 Barberning ish tajribasini kiriting.\n"
        "Masalan: <b>3 yil</b>",
        parse_mode="HTML"
    )


# --------------------------- 4) EXPERIENCE ----------------------------
@router.message(StateFilter(AdminStates.adding_barber_experience))
async def add_barber_experience(message: types.Message, state: FSMContext):
    experience = message.text.strip()

    if len(experience) < 2:
        return await message.answer("❌ Tajriba juda qisqa. Qayta kiriting.")

    await state.update_data(experience=experience)
    await state.set_state(AdminStates.adding_barber_work_days)

    await message.answer(
        "📅 Barberning ish kunlarini kiriting.\n"
        "Masalan: <b>Dushanba–Juma</b>",
        parse_mode="HTML"
    )


# --------------------------- 5) WORK DAYS + ASK PHOTO ----------------------------
@router.message(StateFilter(AdminStates.adding_barber_work_days))
async def add_barber_work_days(message: types.Message, state: FSMContext):
    work_days = message.text.strip()

    if len(work_days) < 3:
        return await message.answer("❌ Ish kunlari noto‘g‘ri.")

    await state.update_data(work_days=work_days)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📸 Rasm qo‘shaman", callback_data="add_photo_yes"),
                InlineKeyboardButton(text="➡️ Rasm kerak emas", callback_data="add_photo_no")
            ]
        ]
    )

    await state.set_state(AdminStates.adding_photo_choice)
    await message.answer(
        "🖼 Barber uchun rasm qo‘shasizmi?",
        reply_markup=markup
    )


# --------------------------- 6) PHOTO CHOICE ----------------------------
@router.callback_query(F.data == "add_photo_yes", StateFilter(AdminStates.adding_photo_choice))
async def ask_for_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AdminStates.adding_barber_photo)
    await call.message.answer("📸 Iltimos, barberning rasmini yuboring.")


@router.callback_query(F.data == "add_photo_no", StateFilter(AdminStates.adding_photo_choice))
async def save_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        barber = Barbers(
            barber_first_name=data["first_name"],
            barber_last_name=data["last_name"],
            tg_id=data["tg_id"],
            tg_username=data["tg_username"],
            phone=data["phone"],
            experience=data["experience"],
            work_days=data["work_days"],
            photo=None
        )
        session.add(barber)
        await session.commit()

    await call.message.answer(
        "✅ <b>Barber muvaffaqiyatli qo‘shildi!</b>\n\n"
        f"👨‍🎤 <b>{data['first_name']} {data['last_name']}</b>\n"
        f"📞 {data['phone']}\n"
        f"💼 {data['experience']}\n"
        f"📅 {data['work_days']}\n"
        f"🖼 Rasm: <i>Yo‘q</i>",
        parse_mode="HTML"
    )

    await state.clear()
    await call.answer()


# === YAGONA: rasm qabul qiluvchi handler (faqat bitta bo'lsin!) ===
@router.message(StateFilter(AdminStates.adding_barber_photo), F.photo)
async def add_barber_photo(message: types.Message, state: FSMContext):
    """
    Faol: message.photo[-1].file_id saqlaydi (TELEGRAM file_id)
    E'tibor: eski bytea yuklovchi funksiyani BUTUNLAY o'chiring.
    """
    photo_file_id = message.photo[-1].file_id

    data = await state.get_data()
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    phone = data.get("phone")
    experience = data.get("experience")
    work_days = data.get("work_days")
    tg_id = data.get("tg_id")
    tg_username = data.get("tg_username")

    if not all([first_name, last_name, phone, experience, work_days]):
        await message.answer("❌ Ma'lumotlar yetarli emas. Jarayon buzildi. Qayta boshlang.")
        await state.clear()
        return

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=first_name,
            barber_last_name=last_name,
            tg_id=tg_id,
            tg_username=tg_username,
            phone=phone,
            experience=experience,
            work_days=work_days,
            photo=photo_file_id   
        )
        session.add(new_barber)
        await session.commit()

    await message.answer(
        f"✅ Barber rasm bilan saqlandi!\n\n"
        f"👨‍🎤 <b>{first_name} {last_name}</b>\n"
        f"📞 {phone}\n"
        f"💼 {experience}\n"
        f"📅 {work_days}",
        parse_mode="HTML"
    )

    await state.clear()


# fallback — agar user rasm o‘rniga matn yuborsa
@router.message(StateFilter(AdminStates.adding_barber_photo))
async def expected_photo(message: types.Message):
    await message.answer("❌ Iltimos, rasm yuboring (📸).")
