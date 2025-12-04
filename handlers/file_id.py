from aiogram import Router, types

router = Router()

@router.message()
async def get_file_id(message: types.Message):
    if message.photo:
        file_id = message.photo[-1].file_id  # eng sifatli o'lcham
        await message.answer(
            f"📁 Photo file_id:\n\n`{file_id}`",
            parse_mode="Markdown"
        )
