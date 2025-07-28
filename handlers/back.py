from aiogram import types
from keyboards.main_menu import get_main_menu

async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.answer(
        "Quyidagi buyruqlardan birini tanlang!",
        reply_markup=get_main_menu()
    )
