#handlers/start.py
from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sql.db import async_session
from sql.models import OrdinaryUser
from aiogram.types import FSInputFile   
from keyboards.start_btns import start_button
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


# --- 1. /start → video + tugma chiqarish ---
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    video_id = "BAACAgIAAxkBAAMHaUtvuBLcaxS54Lhvt4xwqBMLQ2QAAq2JAAIPe2BKpIl-BG9XL-c2BA"

    await message.answer_video(
        video=video_id,
        caption=(
            "👋 Assalomu alaykum!\n"
            "Bu bot orqali barbershop xizmatlariga onlayn navbat olishingiz mumkin.\n\n"
            "👇 Boshlash tugmasini bosing:"
        ),
        reply_markup=start_button
    )


# --- 2. Boshlash tugmasi bosilganda → userni ro‘yxatga olish ---
@router.callback_query(lambda c: c.data == "start_bot")
async def start_bot_pressed(callback: types.CallbackQuery, state: FSMContext):
    message = callback.message
    tg_id = callback.from_user.id

    first_name = normalize_fancy(callback.from_user.first_name)
    last_name = normalize_fancy(callback.from_user.last_name)
    username = callback.from_user.username

    async with async_session() as session:
        result = await session.execute(
            select(OrdinaryUser).where(OrdinaryUser.tg_id == tg_id)
        )
        user = result.scalars().first()

        if not user:
            session.add(
                OrdinaryUser(
                    tg_id=tg_id,
                    first_name=first_name,
                    last_name=last_name,
                    username=username
                )
            )
            await session.commit()

    await state.clear()

    keyboard = await get_dynamic_main_keyboard(tg_id)

    await message.answer(
        "👋 Xush kelibsiz! Quyidagi menyudan birini tanlang:",
        reply_markup=keyboard
    )

    await message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )

    await callback.answer("🚀 Bot ishga tushdi")

