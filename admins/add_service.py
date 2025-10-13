from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from config import ADMINS
from sql.models import Services
from sql.db import async_session
from sqlalchemy.future import select
import re

router = Router()

# --- 1️⃣ Admin xizmat qo‘shishni boshlaydi ---
@router.message(F.text == "💈 Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return await message.answer("⛔ Sizda bu amalni bajarish uchun huquq yo‘q.")
    
    await state.set_state(AdminStates.adding_service)
    await message.answer("📝 Yangi xizmat nomini kiriting:")


# --- 2️⃣ Xizmat nomini qabul qilish ---
@router.message(AdminStates.adding_service)
async def save_service_name(message: types.Message, state: FSMContext):
    service_name = message.text.strip()

    async with async_session() as session:
        result = await session.execute(select(Services).where(Services.name.ilike(service_name)))
        existing = result.scalar()

        if existing:
            await message.answer("⚠️ Bunday xizmat allaqachon mavjud.")
            return await state.clear()

    await state.update_data(service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer("💵 Xizmat narxini kiriting (so‘mda, faqat raqam):")


# --- 3️⃣ Xizmat narxini qabul qilish ---
@router.message(AdminStates.adding_service_price)
async def save_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Narx faqat raqam bo‘lishi kerak. Qayta kiriting:")

    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("⏰ Xizmat davomiyligini kiriting (masalan: 30 daqiqa):")


# --- 4️⃣ Xizmat davomiyligini qabul qilib, DB'ga saqlash ---
@router.message(AdminStates.adding_service_duration)
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    data = await state.get_data()

    # ✅ Xizmatni ma'lumotlar bazasiga saqlash
    async with async_session() as session:
        new_service = Services(
            name=data["service_name"],
            price=data["price"],
            duration=duration
        )
        session.add(new_service)
        await session.commit()

    await message.answer(
        f"✅ Yangi xizmat qo‘shildi!\n\n"
        f"💈 <b>{data['service_name']}</b>\n"
        f"💵 Narxi: {data['price']} so‘m\n"
        f"⏰ Davomiyligi: {duration}",
        parse_mode="HTML"
    )
    await state.clear()
