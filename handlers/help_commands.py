# from aiogram import Router
# from aiogram.filters import Command
# from aiogram.types import Message
# from aiogram.fsm.context import FSMContext

# from handlers.booking import UserState

# router = Router()

# # Umumiy /help
# @router.message(Command("help"))
# async def help_command(message: Message, state: FSMContext):
#     current_state = await state.get_state()

#     if current_state == UserState.waiting_for_fullname:
#         await message.answer(
#             "ℹ️ Siz **to‘liq ismingizni** kiritish bosqichidasiz.\n\n"
#             "Masalan: `Aliyev Valijon`"
#         )
#     elif current_state == UserState.waiting_for_phonenumber:
#         await message.answer(
#             "ℹ️ Siz **telefon raqamingizni** kiritishingiz kerak.\n\n"
#             "Format: `+998901234567`"
#         )
#     elif current_state == UserState.waiting_for_service:
#         await message.answer(
#             "ℹ️ Siz **xizmat turini** tanlashingiz kerak.\n\n"
#             "Ro‘yxatdan kerakli xizmatni tanlang."
#         )
#     elif current_state == UserState.waiting_for_barber:
#         await message.answer(
#             "ℹ️ Siz **ustani** tanlashingiz kerak.\n\n"
#             "Kerakli ustani tugmalar orqali belgilang."
#         )
#     elif current_state == UserState.waiting_for_date:
#         await message.answer(
#             "ℹ️ Siz **sanani** tanlashingiz kerak.\n\n"
#             "Mavjud sanalardan birini tugmalar orqali tanlang."
#         )
#     elif current_state == UserState.waiting_for_time:
#         await message.answer(
#             "ℹ️ Siz **vaqtni** tanlashingiz kerak.\n\n"
#             "Mavjud bo‘sh vaqtni tanlang."
#         )
#     else:
#         # Umumiy yordam
#         await message.answer(
#             "📖 Botdan foydalanish bo‘yicha yordam:\n\n"
#             "➡️ /start - Botni qayta ishga tushirish\n"
#             "➡️ /help - Yordam olish\n\n"
#             "📌 Asosiy menyuda quyidagilar mavjud:\n"
#             "   • ✂️ Xizmatlarga yozilish\n"
#             "   • 🗂 Buyurtmalar tarixi\n"
#             "   • ❌ Buyurtmani bekor qilish\n"
#         )
