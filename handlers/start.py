# handlers/start.py
from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sql.db import async_session
from sql.models import OrdinaryUser
from keyboards.main_buttons import get_dynamic_main_keyboard  
from keyboards.main_menu import get_main_menu

import unicodedata
import unidecode

router = Router()

# --- Lotinlashtiruvchi funksiya ---
def normalize_fancy(text: str) -> str:
    if not text:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = unidecode.unidecode(normalized)
    clean = ''.join(ch for ch in ascii_text if ch.isalnum())
    return clean


@router.message(CommandStart())
async def register_user(message: types.Message, state: FSMContext):
    """Foydalanuvchini birinchi marta start bosganda bazaga yozadi va menyuni ko‘rsatadi."""
    tg_id = message.from_user.id

    # --- Foydalanuvchini olamiz ---
    first_name_raw = message.from_user.first_name
    last_name_raw = message.from_user.last_name
    username = message.from_user.username

    # --- 🔥 Autolatin / normalize qilish ---
    first_name = normalize_fancy(first_name_raw)
    last_name = normalize_fancy(last_name_raw)

    async with async_session() as session:
        # Foydalanuvchi bor-yo‘qligini tekshirish
        result = await session.execute(
            select(OrdinaryUser).where(OrdinaryUser.tg_id == tg_id)
        )
        user = result.scalars().first()

        # Yangi foydalanuvchini yaratish
        if not user:
            new_user = OrdinaryUser(
                tg_id=tg_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(new_user)
            await session.commit()

    # FSM tozalanadi
    await state.clear()

    # Asosiy menyu
    keyboard = await get_dynamic_main_keyboard(tg_id)

    await message.answer(
        "👋 Assalomu alaykum, botga xush kelibsiz!\n"
        "Quyidagi menyudan birini tanlang:",
        reply_markup=keyboard
    )

    await message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )
