# admins/admin_menus.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from .admin_buttons import (
    INFO_MENU_TEXT,
)

router = Router()

@router.message(F.text == INFO_MENU_TEXT)
async def open_info_menu(message: types.Message, state: FSMContext):
    from .info_handle import open_info_panel
    await open_info_panel(message, state)
