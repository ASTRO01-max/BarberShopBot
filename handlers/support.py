from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

router = Router()

# Har bir foydalanuvchi uchun bot yuborgan va foydalanuvchi yuborgan xabar IDlari
user_messages = {}

async def send_and_store(message: Message, text: str, reply_markup=None):
    """
    Bot yuborgan xabarni jo‘natadi va ID sini saqlaydi.
    """
    sent = await message.answer(text, reply_markup=reply_markup)
    user_messages.setdefault(message.from_user.id, []).append(sent.message_id)
    return sent


async def safe_delete(bot, chat_id: int, message_id: int):
    """
    Xabarni xavfsiz o‘chirish, xatolarga chidamli.
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


@router.message(Command("support"))
async def support_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # 🔹 Foydalanuvchi yuborgan xabarni o‘chirishga urinish
    await safe_delete(message.bot, chat_id, message.message_id)

    # 🔹 Bot yuborgan eski xabarlarni o‘chirish
    if user_id in user_messages:
        for msg_id in user_messages[user_id]:
            await safe_delete(message.bot, chat_id, msg_id)
        user_messages[user_id] = []

    # 🔹 FSMContext ni ham tozalash
    await state.clear()


    # 📌 Yangi support panelni yuborish
    await send_and_store(
        message,
        "📞 *Support paneliga xush kelibsiz!*\n"
        "Savolingizni yozib yuboring yoki tugmalardan foydalaning.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="📨 Operator bilan bog‘lanish", callback_data="connect_support")],
                [types.InlineKeyboardButton(text="❌ Chiqish", callback_data="exit_support")]
            ]
        )
    )


# 🔹 Tugmalar uchun callbacklar
@router.callback_query(F.data == "connect_support")
async def connect_support(callback: CallbackQuery):
    await send_and_store(callback.message, "✅ Operator bilan tez orada bog‘lanasiz.")
    await callback.answer()


@router.callback_query(F.data == "exit_support")
async def exit_support(callback: CallbackQuery):
    await callback.message.edit_text("❌ Support panelidan chiqdingiz.")
    await callback.answer()
