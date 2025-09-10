from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from config import ADMINS
from database import services_barbers_utils as sb_utils
import re

router = Router()

@router.message(F.text == "💈 Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    await state.set_state(AdminStates.adding_service)
    await message.answer("📝 Yangi servis nomini kiriting:")

@router.message(AdminStates.adding_service)
async def save_service_name(message: types.Message, state: FSMContext):
    service_name = message.text.strip()
    services = sb_utils.load_services()

    for val in services.values():
        if val[0].lower() == service_name.lower():
            await message.answer("⚠️ Bu servis allaqachon mavjud.")
            return await state.clear()

    raw_id = service_name.lower().replace(" ", "_")
    service_id = re.sub(r"[^a-z0-9_]", "", raw_id)

    base_id = service_id
    i = 1
    while service_id in services:
        service_id = f"{base_id}_{i}"
        i += 1

    await state.update_data(service_id=service_id, service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer("💵 Servis narxini kiriting (so'mda, faqat raqam):")

@router.message(AdminStates.adding_service_price)
async def save_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Narx faqat raqam bo‘lishi kerak. Qayta kiriting:")
    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("⏰ Servis davomiyligini kiriting (masalan: 30 daqiqa):")

@router.message(AdminStates.adding_service_duration)
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    data = await state.get_data()

    services = sb_utils.load_services()
    services[data["service_id"]] = (data["service_name"], data["price"], duration)
    sb_utils.save_services(services)

    await message.answer(
        f"✅ Servis qo‘shildi:\n\n"
        f"✂️ {data['service_name']} – {data['price']} so'm ({duration})"
    )
    await state.clear()
