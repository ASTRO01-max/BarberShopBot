from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from database import static_data
from config import ADMINS
import re

router = Router()

@router.message(F.text == "👨‍🎤 Barber qo'shish")
async def add_barber_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    await state.set_state(AdminStates.adding_barber)
    await message.answer("🧔‍♂️ Yangi barber nomini kiriting:")

@router.message(AdminStates.adding_barber)
async def save_barber(message: types.Message, state: FSMContext):
    barber_name = message.text.strip()

    for barber in static_data.barbers:
        if barber["name"].lower() == barber_name.lower():
            await message.answer("⚠️ Bu barber allaqachon mavjud.")
            return await state.clear()

    raw_id = barber_name.lower().replace(" ", "_")
    barber_id = re.sub(r"[^a-z0-9_]", "", raw_id)

    base_id = barber_id
    i = 1
    existing_ids = {b["id"] for b in static_data.barbers}
    while barber_id in existing_ids:
        barber_id = f"{base_id}_{i}"
        i += 1

    new_barber = {"id": barber_id, "name": barber_name, "exp": "0 yil", "days": "Noma’lum"}
    static_data.barbers.append(new_barber)

    await message.answer(f"✅ Barber qo‘shildi: {barber_name}")
    await state.clear()
