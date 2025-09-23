from aiogram import types, html
from aiogram.types import Message
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import *

async def start_handler(message: Message):
    await message.answer(
        f"Assalomu alaykum, botga xush kelibsiz, {html.bold(message.from_user.full_name)}!",
        parse_mode="HTML",
        reply_markup=get_dynamic_main_keyboard(message.from_user.id)  # Barcha tugmalar birlashtirilgan
    )
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        reply_markup=get_main_menu()
    )
