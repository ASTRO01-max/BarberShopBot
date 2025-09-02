from aiogram import types
from keyboards.main_menu import get_main_menu
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.answer(
        "Quyidagi buyruqlardan birini tanlang!",
        reply_markup=get_main_menu()
    )


