from aiogram import types
from database.static_data import barbers
from keyboards.booking_keyboards import back_button

async def show_barbers(callback: types.CallbackQuery):
    text = "👨‍🎤 Ustalar:\n" + "\n".join(
        f"{b['name']} – {b['exp']} tajriba – Ish kunlari: {b['days']}" for b in barbers
    )
    await callback.message.edit_text(text, reply_markup=back_button())
