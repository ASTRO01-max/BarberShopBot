from aiogram import types
from database.static_data import services
from keyboards.booking_keyboards import back_button

async def show_services(callback: types.CallbackQuery):
    text = "📋 Xizmatlar ro'yxati:\n" + "\n".join(
        f"{s[0]} – {s[1]} so'm ({s[2]})" for s in services.values()
    )
    await callback.message.edit_text(text, reply_markup=back_button())
