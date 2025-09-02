from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from config import ADMINS
from utils.states import AdminStates
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

    # mavjudligini tekshirish (fayldan yangisini olish)
    services = sb_utils.load_services()
    for val in services.values():
        if val[0].lower() == service_name.lower():
            await message.answer("⚠️ Bu servis allaqachon mavjud.")
            await state.clear()
            return

    # xavfsiz ID yaratish
    raw_id = service_name.lower().replace(" ", "_")
    service_id = re.sub(r"[^a-z0-9_]", "", raw_id)

    base_id = service_id
    i = 1
    while service_id in services:
        service_id = f"{base_id}_{i}"
        i += 1

    # vaqtinchalik saqlash
    await state.update_data(service_id=service_id, service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer("💵 Servis narxini kiriting (so'mda, faqat raqam):")


@router.message(AdminStates.adding_service_price)
async def save_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Narx faqat raqam bo‘lishi kerak. Qayta kiriting:")
        return

    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("⏰ Servis davomiyligini kiriting (masalan: 30 daqiqa):")


@router.message(AdminStates.adding_service_duration)
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    data = await state.get_data()

    service_id = data["service_id"]
    service_name = data["service_name"]
    price = data["price"]

    # fayldan yangisini olish va qo‘shish
    services = sb_utils.load_services()
    services[service_id] = (service_name, price, duration)
    sb_utils.save_services(services)

    await message.answer(
        f"✅ Servis qo‘shildi:\n\n"
        f"✂️ {service_name} – {price} so'm ({duration})"
    )
    await state.clear()
