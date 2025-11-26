# admins/add_barbers.py

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.states import AdminStates
from sqlalchemy import select
from sql.db import async_session
from sql.models import Barbers, OrdinaryUser

router = Router()


# 1) Admin barber qo‘shishni boshlaydi
@router.message(F.text == "👨‍🎤 Barber qo'shish")
async def add_barber_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.adding_barber_fullname)
    await message.answer("🧔‍♂️ Yangi barberning to‘liq ismini kiriting:\n\n"
                         "Namuna: <b>Abdulloh Karimov</b>")


# 2) To‘liq ismni qabul qilamiz va database dan qidiramiz
@router.message(StateFilter(AdminStates.adding_barber_fullname))
async def add_barber_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()

    # to‘liq ism bo‘lmasa xato
    if len(fullname.split()) < 2:
        return await message.answer("❌ To‘liq ism kiriting (Ism Familiya).")

    first_name, last_name = fullname.split(" ", 1)

    async with async_session() as session:

        # 1) Avval barber jadvalidan tekshiramiz
        existing = await session.execute(
            select(Barbers).where(
                Barbers.barber_first_name.ilike(first_name),
                Barbers.barber_last_name.ilike(last_name)
            )
        )
        exists = existing.scalars().first()

        if exists:
            return await message.answer("⚠️ Bu barber allaqachon ro‘yxatda bor.")

        # 2) OrdinaryUser dan qidirish — full match qilish
        user_query = await session.execute(
            select(OrdinaryUser).where(
                OrdinaryUser.first_name.ilike(first_name),
                OrdinaryUser.last_name.ilike(last_name)
            )
        )
        user = user_query.scalars().first()

        # 3) Agar (ism+familiya) topilmasa → fallback: faqat ism bilan qidiramiz
        if not user:
            fallback = await session.execute(
                select(OrdinaryUser).where(
                    OrdinaryUser.first_name.ilike(first_name)
                )
            )
            user = fallback.scalars().first()

        # 4) Natija bo‘yicha tg_id va username
        tg_id = user.tg_id if user else None
        tg_username = user.username if user else None

    # Ma'lumotlarni FSM ga saqlaymiz
    await state.update_data(
        first_name=first_name,
        last_name=last_name,
        tg_id=tg_id,
        tg_username=tg_username
    )

    await state.set_state(AdminStates.adding_barber_phone)
    await message.answer(
        f"📞 Endi barber telefon raqamini kiriting:\n\n"
        f"🔎 Topildi: <b>{tg_id if tg_id else 'Topilmadi (start bosmagan)'}</b>"
    )


# 3) Telefon raqam qabul qilish
@router.message(StateFilter(AdminStates.adding_barber_phone))
async def add_barber_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    if not phone.startswith("+998") or len(phone) != 13 or not phone[1:].isdigit():
        return await message.answer("❌ Telefon raqam noto'g'ri.\nNamuna: +998901234567")

    await state.update_data(phone=phone)
    await state.set_state(AdminStates.adding_barber_experience)
    await message.answer("💼 Barberning ish tajribasini kiriting:\nMasalan: <b>3 yil</b>")


# 4) Tajriba qabul qilish
@router.message(StateFilter(AdminStates.adding_barber_experience))
async def add_barber_experience(message: types.Message, state: FSMContext):
    experience = message.text.strip()

    if len(experience) < 2:
        return await message.answer("❌ Tajriba juda qisqa. Qaytadan kiriting.")

    await state.update_data(experience=experience)
    await state.set_state(AdminStates.adding_barber_work_days)
    await message.answer("📅 Ish kunlarini kiriting:\nMasalan: <b>Dushanba–Juma</b>")


# 5) Ish kunlari + Rasm so‘rash
@router.message(StateFilter(AdminStates.adding_barber_work_days))
async def add_barber_work_days(message: types.Message, state: FSMContext):
    work_days = message.text.strip()

    if len(work_days) < 3:
        return await message.answer("❌ Ish kunlari noto‘g‘ri.")

    await state.update_data(work_days=work_days)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ha, rasm qo‘shaman", callback_data="add_photo_yes"),
                InlineKeyboardButton(text="Yo‘q, rasm kerak emas", callback_data="add_photo_no")
            ]
        ]
    )

    await message.answer("🖼 Barber uchun rasm qo‘shasizmi?", reply_markup=markup)
    await state.set_state(AdminStates.adding_photo_choice)


# 6) Rasmsiz saqlash
@router.callback_query(F.data == "add_photo_no", StateFilter(AdminStates.adding_photo_choice))
async def save_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=data["first_name"],
            barber_last_name=data["last_name"],
            tg_id=data["tg_id"],
            tg_username=data["tg_username"],
            phone=data["phone"],
            experience=data["experience"],
            work_days=data["work_days"],
            photo=None
        )
        session.add(new_barber)
        await session.commit()

    await call.message.answer(
        f"✅ Barber rasmga ega emas, ammo muvaffaqiyatli qo‘shildi!\n\n"
        f"👨‍🎤 <b>{data['first_name']} {data['last_name']}</b>\n"
        f"📞 {data['phone']}\n"
        f"💼 {data['experience']}\n"
        f"📅 {data['work_days']}\n"
        f"🆔 TG ID: {data['tg_id']}"
    )

    await state.clear()
    await call.answer()


# 7) Rasm so‘ralganda
@router.callback_query(F.data == "add_photo_yes", StateFilter(AdminStates.adding_photo_choice))
async def ask_for_photo(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_barber_photo)
    await call.message.answer("📸 Barberning rasmini yuboring:")
    await call.answer()


# 8) Rasm bilan saqlash
@router.message(StateFilter(AdminStates.adding_barber_photo), F.photo)
async def add_barber_photo(message: types.Message, state: FSMContext):
    photo_file = message.photo[-1]
    file = await message.bot.get_file(photo_file.file_id)
    photo_stream = await message.bot.download_file(file.file_path)
    photo_bytes = photo_stream.read()

    data = await state.get_data()

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=data["first_name"],
            barber_last_name=data["last_name"],
            tg_id=data["tg_id"],
            tg_username=data["tg_username"],
            phone=data["phone"],
            experience=data["experience"],
            work_days=data["work_days"],
            photo=photo_bytes
        )
        session.add(new_barber)
        await session.commit()

    await message.answer(
        f"✅ Rasm bilan barber qo‘shildi!\n\n"
        f"👨‍🎤 <b>{data['first_name']} {data['last_name']}</b>\n"
        f"📞 {data['phone']}\n"
        f"💼 {data['experience']}\n"
        f"📅 {data['work_days']}\n"
        f"🆔 TG ID: {data['tg_id']}"
    )

    await state.clear()


# fallback — agar user rasm o‘rniga matn yozsa
@router.message(StateFilter(AdminStates.adding_barber_photo))
async def expected_photo(message: types.Message):
    await message.answer("❌ Iltimos, rasm yuboring.")
