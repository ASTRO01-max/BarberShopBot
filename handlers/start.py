# handlers/start.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sql.db import async_session
from sql.models import OrdinaryUser
from keyboards.main_buttons import get_dynamic_main_keyboard  
from keyboards.main_menu import get_main_menu

router = Router()

@router.message(CommandStart())
async def register_user(message: types.Message, state: FSMContext):
    """Foydalanuvchini birinchi marta start bosganda bazaga yozadi va menyuni ko‘rsatadi."""
    tg_id = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username

    async with async_session() as session:
        # Foydalanuvchi bazada bor-yo‘qligini tekshirish
        result = await session.execute(
            select(OrdinaryUser).where(OrdinaryUser.tg_id == tg_id)
        )
        user = result.scalars().first()

        # Agar yo‘q bo‘lsa, yangi foydalanuvchi qo‘shiladi
        if not user:
            new_user = OrdinaryUser(
                tg_id=tg_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(new_user)
            await session.commit()

    # Har qanday holatda (yangi yoki eski foydalanuvchi) FSM tozalanadi
    await state.clear()

    # Asosiy menyu klaviaturasini olamiz
    keyboard = await get_dynamic_main_keyboard(tg_id)

    await message.answer(
        "👋 Assalomu alaykum, botga xush kelibsiz!\n"
        "Quyidagi menyudan birini tanlang:",
        reply_markup=keyboard
    )

    # Agar kerak bo‘lsa, qo‘shimcha menyu ham chiqadi
    await message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )
