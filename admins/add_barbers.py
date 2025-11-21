from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from utils.states import AdminStates
from sqlalchemy.future import select
from sql.db import async_session
from sql.models import Barbers

router = Router()

# --- 1️⃣ Boshlanish ---
@router.message(F.text == "👨‍🎤 Barber qo'shish")
async def add_barber_start(message: types.Message, state: FSMContext):
    await state.set_state(AdminStates.adding_barber_fullname)
    await message.answer("🧔‍♂️ Yangi barberning to‘liq ismini kiriting:")


# --- 2️⃣ To‘liq ismni olish ---
@router.message(StateFilter(AdminStates.adding_barber_fullname))
async def add_barber_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if len(fullname) < 3:
        return await message.answer("❌ To‘liq ism juda qisqa. Qaytadan kiriting:")

    # Bunday ism mavjudligini tekshirish
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.barber_fullname.ilike(fullname)))
        existing = result.scalar()
        if existing:
            return await message.answer("⚠️ Bu ismli barber allaqachon mavjud.")

    await state.update_data(fullname=fullname)
    await state.set_state(AdminStates.adding_barber_phone)
    await message.answer("📞 Barber telefon raqamini kiriting (+998 bilan):")


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


# --- 5️⃣ Ish kunlarini olish va bazaga yozish ---
@router.message(StateFilter(AdminStates.adding_barber_work_days))
async def add_barber_work_days(message: types.Message, state: FSMContext):
    work_days = message.text.strip()
    if len(work_days) < 3:
        return await message.answer("❌ Ish kunlari noto‘g‘ri kiritildi. Qaytadan kiriting:")

    await state.update_data(work_days=work_days)

    await state.set_state(AdminStates.adding_barber_photo)
    await message.answer("🖼 Endi barberning rasmini yuboring (1 dona, JPG/PNG):")


# --- 6️⃣ Rasmni qabul qilish va BARCHA ma’lumotni bir martada SQLga yozish ---
@router.message(StateFilter(AdminStates.adding_barber_photo), F.photo)
async def add_barber_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    file = await message.bot.get_file(photo_file_id)
    photo_bytes = await message.bot.download_file(file.file_path)

    data = await state.get_data()

    async with async_session() as session:
        new_barber = Barbers(
            barber_fullname=data["fullname"],
            phone=data["phone"],
            experience=data["experience"],
            work_days=data["work_days"],
            photo=photo_bytes.read()
        )
        session.add(new_barber)
        await session.commit()

    await message.answer(
        f"✅ Yangi barber muvaffaqiyatli qo‘shildi!\n\n"
        f"👨‍🎤 <b>{data['fullname']}</b>\n"
        f"📞 <b>{data['phone']}</b>\n"
        f"💼 <b>{data['experience']}</b>\n"
        f"📅 <b>{data['work_days']}</b>",
        parse_mode="HTML"
    )

    await state.clear()

