from aiogram import Router, types
from aiogram.filters import Command
from config import ADMINS
from .admin_buttons import markup

router = Router()

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMINS:
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
    await message.answer("🔐 Admin panelga xush kelibsiz!", reply_markup=markup)
