# from aiogram import Router, types
# from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
# from keyboards.main_menu import get_main_menu

# path = r"C:\Users\hp\Downloads\Telegram Desktop\barbershopbot.mp4"

# router = Router()

# @router.message()
# async def start_handler(message: Message):
#     inline_kb = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="🚀 Boshlash", callback_data="start_bot")]
#     ])

#     # Videoni yuborish
#     video = FSInputFile(path)
#     await message.answer_video(
#         video=video,
#         caption="💈 Bu *BarberShopBot*! \n\nSiz bu bot orqali onlayn tarzda navbatga yozilishingiz, xizmatlar va ustalar haqida ma'lumot olishingiz mumkin.",
#         parse_mode="Markdown",
#         reply_markup=inline_kb
#     )


# @router.callback_query(lambda c: c.data == "start_bot")
# async def process_start_button(callback_query: types.CallbackQuery):
#     # Eski xabarni o‘chirib tashlash
#     await callback_query.message.delete()

#     # Yangi menyuni chiqarish
#     await callback_query.message.answer(
#         "Quyidagi menyudan birini tanlang:",
#         reply_markup=get_main_menu()
#     )

from aiogram import types, html
from aiogram.types import Message
from keyboards.main_menu import get_main_menu
from keyboards.main_buttons import *

async def start_handler(message: Message):
    await message.answer(
        f"Assalomu alaykum, botga xush kelibsiz, {html.bold(message.from_user.full_name)}!",
        parse_mode="HTML", reply_markup=keyboard
    )
    await message.answer(
        "Quyidagi menyudan birini tanlang:",
        reply_markup=get_main_menu()
    )
