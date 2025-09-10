from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from utils.states import BroadcastState
from config import ADMINS
import json

router = Router()
USERS_FILE = "database/users.json"  # foydalanuvchi IDlari saqlanadigan fayl

@router.message(F.text == "✉️ Mahsus xabar yuborish")
async def ask_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return await message.answer("❌ Siz admin emassiz!")
    await message.answer("📨 Yubormoqchi bo'lgan xabaringizni kiriting:")
    await state.set_state(BroadcastState.waiting_for_message)

@router.message(BroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext, bot: Bot):
    text = message.text
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = []

    sent_count = 0
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=f"📢 Admin xabari:\n\n{text}")
            sent_count += 1
        except:
            pass

    await message.answer(f"✅ Xabar {sent_count} ta foydalanuvchiga yuborildi.")
    await state.clear()
