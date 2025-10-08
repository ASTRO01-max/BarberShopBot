from aiogram import types, html, Router
from aiogram.types import Message
from aiogram.filters import CommandStart
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import get_dynamic_main_keyboard  

router = Router()

@router.message(CommandStart())
async def start_handler(message: Message):
    # Asosiy foydalanuvchi tugmalarini yuklash
    keyboard = await get_dynamic_main_keyboard(message.from_user.id)

    # Foydalanuvchiga xush kelibsiz xabari
    await message.answer(
        "Assalomu alaykum, botga xush kelibsiz!\nQuyidagi menyudan birini tanlang:",
        reply_markup=keyboard
    )

    # Asosiy menyu (xizmatlar, ustalar, navbat olish va hokazo)
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        reply_markup=get_main_menu()
    )
