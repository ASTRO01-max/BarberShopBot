# admins/admin_menus.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from .admin_buttons import (
    SERVICE_MENU_TEXT,
    BARBER_MENU_TEXT,
    INFO_MENU_TEXT,
    SERVICE_ADD_CB,
    SERVICE_DEL_CB,
    BARBER_ADD_CB,
    BARBER_DEL_CB,
    get_service_inline_actions_kb,
    get_barber_inline_actions_kb,
    get_info_inline_actions_kb,
)
from .add_service import add_service_prompt
from .service_shutdown import list_services_for_delete
from .add_barbers import add_barber_start
from .barbers_shutdown import list_barbers_for_delete

router = Router()


@router.message(F.text == SERVICE_MENU_TEXT)
async def open_service_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Servis bo'limi:", reply_markup=get_service_inline_actions_kb())


@router.message(F.text == BARBER_MENU_TEXT)
async def open_barber_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Barber bo'limi:", reply_markup=get_barber_inline_actions_kb())


@router.message(F.text == INFO_MENU_TEXT)
async def open_info_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Info bo'limi:", reply_markup=get_info_inline_actions_kb())


@router.callback_query(F.data == SERVICE_ADD_CB)
async def service_add_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await add_service_prompt(callback.message, state)


@router.callback_query(F.data == SERVICE_DEL_CB)
async def service_del_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await list_services_for_delete(callback.message)


@router.callback_query(F.data == BARBER_ADD_CB)
async def barber_add_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await add_barber_start(callback.message, state)


@router.callback_query(F.data == BARBER_DEL_CB)
async def barber_del_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await list_barbers_for_delete(callback.message)
