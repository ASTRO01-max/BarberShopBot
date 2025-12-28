# from aiogram import Router, F
# from aiogram.types import Message

# router = Router()

# @router.message(F.video)
# async def get_video_file_id(message: Message):
#     file_id = message.video.file_id
#     await message.answer(
#         f"🎬 Video file_id:\n\n<code>{file_id}</code>",
#         parse_mode="HTML"
#     )
