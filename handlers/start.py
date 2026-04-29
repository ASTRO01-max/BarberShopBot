# handlers/start.py
import logging
import unicodedata

import unidecode
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from keyboards.main_buttons import get_dynamic_main_keyboard
from keyboards.main_menu import get_main_menu
from keyboards.start_btns import start_button
from sql.db import async_session
from sql.db_start_vd_or_img import (
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    get_start_media_payload,
)
from sql.models import OrdinaryUser

router = Router()
logger = logging.getLogger(__name__)

START_ENTRY_CAPTION = (
    "👋 Assalomu alaykum!\n"
    "Bu bot orqali barbershop xizmatlariga onlayn navbat olishingiz mumkin.\n\n"
    "👇 Boshlash tugmasini bosing:"
)

WELCOME_TEXT = "👋 Xush kelibsiz! Quyidagi menyudan birini tanlang:"
MAIN_MENU_TEXT =  "🏠 <b>Asosiy menyudan kerakli bo‘limni tanlang 👇</b>"


def normalize_fancy(text: str) -> str | None:
    if not text:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = unidecode.unidecode(normalized)
    clean = "".join(ch for ch in ascii_text if ch.isalnum())
    return clean or None


async def _ensure_ordinary_user(user: types.User) -> None:
    tg_id = user.id
    first_name = normalize_fancy(user.first_name)
    last_name = normalize_fancy(user.last_name)
    username = user.username

    async with async_session() as session:
        result = await session.execute(
            select(OrdinaryUser).where(OrdinaryUser.tg_id == tg_id)
        )
        existing_user = result.scalars().first()

        if existing_user is None:
            session.add(
                OrdinaryUser(
                    tg_id=tg_id,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                )
            )
            await session.commit()


async def _launch_bot_home(
    message: types.Message,
    state: FSMContext,
    user: types.User,
) -> None:
    await state.clear()
    await _ensure_ordinary_user(user)

    keyboard = await get_dynamic_main_keyboard(user.id)

    await message.answer(
        WELCOME_TEXT,
        reply_markup=keyboard,
    )
    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    media_type, file_id = await get_start_media_payload()
    if file_id:
        try:
            if media_type == MEDIA_TYPE_VIDEO:
                await message.answer_video(
                    video=file_id,
                    caption=START_ENTRY_CAPTION,
                    reply_markup=start_button,
                )
                return
            if media_type == MEDIA_TYPE_IMAGE:
                await message.answer_photo(
                    photo=file_id,
                    caption=START_ENTRY_CAPTION,
                    reply_markup=start_button,
                )
                return
        except TelegramBadRequest:
            logger.warning(
                "Stored start media file_id is invalid. Falling back to direct start."
            )

    await _launch_bot_home(message, state, message.from_user)


@router.callback_query(lambda c: c.data == "start_bot")
async def start_bot_pressed(callback: types.CallbackQuery, state: FSMContext):
    if callback.message is None:
        await callback.answer()
        return

    await _launch_bot_home(callback.message, state, callback.from_user)
    await callback.answer("Bot ishga tushdi")
