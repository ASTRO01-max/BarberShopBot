#handlers/back.py
from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import get_main_menu

router = Router()

async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "Quyidagi buyruqlardan birini tanlang!",
        reply_markup=get_main_menu()
    )
    await callback.answer()


