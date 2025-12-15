#handlers/contact.py
from aiogram import types
from keyboards.booking_keyboards import back_button

async def contact(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📞 Biz bilan bog'lanish:\n"
        "📍 Manzil: Toshkent, Chilonzor 10\n"
        "📱 Tel:tel:+998901234567\n"
        "🕒 Ish vaqti: 09:00 – 21:00",
        reply_markup=back_button()
    )
