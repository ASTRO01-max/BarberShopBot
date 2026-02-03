# admins/add_service.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.future import select

from utils.states import AdminStates
from sql.models import Services
from sql.db import async_session
from utils.emoji_map import SERVICE_EMOJIS

router = Router()


@router.message(F.text == "💈 Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.adding_service)
    await message.answer("📝 Yangi xizmat nomini kiriting:")


@router.message(StateFilter(AdminStates.adding_service))
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


@router.message(StateFilter(AdminStates.adding_service_price))
async def save_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Narx faqat raqam bo‘lishi kerak. Qayta kiriting:")

    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("⏰ Xizmat davomiyligini kiriting (masalan: 30 daqiqa):")


@router.message(StateFilter(AdminStates.adding_service_duration))
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    await state.update_data(duration=duration)

    # ✅ Endi rasm qo'shasizmi?
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📸 Rasm qo‘shaman", callback_data="add_service_photo_yes"),
                types.InlineKeyboardButton(text="➡️ Rasm kerak emas", callback_data="add_service_photo_no"),
            ]
        ]
    )

    await state.set_state(AdminStates.adding_service_photo)
    await message.answer("Xizmat uchun rasm qo‘shasizmi?", reply_markup=markup)


@router.callback_query(F.data == "add_service_photo_no", StateFilter(AdminStates.adding_service_photo))
async def save_service_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        new_service = Services(
            name=data["service_name"],
            price=data["price"],
            duration=data["duration"],
            photo=None,
        )
        session.add(new_service)
        await session.commit()

    emoji = SERVICE_EMOJIS.get(data["service_name"], "🔹")

    await call.message.answer(
        "✅ <b>Yangi xizmat qo‘shildi!</b>\n\n"
        f"{emoji} <b>{data['service_name']}</b>\n"
        f"💵 Narxi: <b>{data['price']}</b> so‘m\n"
        f"⏰ Davomiyligi: <b>{data['duration']}</b>\n"
        f"📸 Rasm: <i>Yo'q</i>",
        parse_mode="HTML",
    )

    await state.clear()
    await call.answer()


@router.callback_query(F.data == "add_service_photo_yes", StateFilter(AdminStates.adding_service_photo))
async def ask_service_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    # shu state ichida photo kutamiz
    await state.set_state(AdminStates.adding_service_photo)
    await call.message.answer("📸 Iltimos, xizmat rasmini yuboring.")


@router.message(StateFilter(AdminStates.adding_service_photo), F.photo)
async def add_service_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()

    # Agar admin oldingi tugmani bosmagan bo'lsa ham, tekshiruv:
    if not data.get("service_name") or not data.get("price") or not data.get("duration"):
        await message.answer("❌ Xizmat ma'lumotlari topilmadi. Qayta boshlang.")
        await state.clear()
        return

    async with async_session() as session:
        new_service = Services(
            name=data["service_name"],
            price=data["price"],
            duration=data["duration"],
            photo=photo_file_id,  # ✅ DB ga file_id saqlaymiz
        )
        session.add(new_service)
        await session.commit()

    emoji = SERVICE_EMOJIS.get(data["service_name"], "🔹")

    await message.answer(
        "✅ <b>Xizmat rasm bilan saqlandi!</b>\n\n"
        f"{emoji} <b>{data['service_name']}</b>\n"
        f"💵 Narxi: <b>{data['price']}</b> so‘m\n"
        f"⏰ Davomiyligi: <b>{data['duration']}</b>\n"
        f"📸 Rasm: <i>mavjud</i>",
        parse_mode="HTML",
    )

    await state.clear()


@router.message(StateFilter(AdminStates.adding_service_photo))
async def expected_photo_or_choice(message: types.Message):
    await message.answer("❌ Iltimos, rasm yuboring (📸) yoki rasm tanlash tugmalaridan foydalaning.")
