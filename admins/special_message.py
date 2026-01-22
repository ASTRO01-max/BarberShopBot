# admins/special_message.py
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sql.db import async_session
from sql.models import OrdinaryUser
from utils.states import BroadcastState

router = Router()

# --- Tugma bosilganda boshlanadi ---
@router.message(F.text == "✉️ Mahsus xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    """Admin xabar yuborishni boshlaydi"""
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "✏️ Yubormoqchi bo‘lgan xabaringizni kiriting.\n\n"
        "❗ Xabar barcha foydalanuvchilarga yuboriladi.\n"
        "❌ Bekor qilish uchun /cancel yuboring."
    )

# --- Bekor qilish buyrug'i ---
@router.message(StateFilter(BroadcastState.waiting_for_message), F.text == "/cancel")
async def cancel_broadcast(message: types.Message, state: FSMContext):
    """Yuborish jarayonini bekor qilish"""
    await state.clear()
    await message.answer("❌ Xabar yuborish bekor qilindi.")

# --- Xabarni qabul qilib, barcha foydalanuvchilarga yuborish ---
@router.message(BroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    """Admin yuborgan xabarni barcha oddiy foydalanuvchilarga tarqatadi"""
    text = message.text
    sent = 0
    failed = 0

    await message.answer("📨 Xabar yuborilmoqda, iltimos kuting...")

    async with async_session() as session:
        # Barcha ordinary_users dan tg_id larni olish
        result = await session.execute(select(OrdinaryUser.tg_id))
        user_ids = [row[0] for row in result]

    # Har bir foydalanuvchiga yuborish
    for user_id in user_ids:
        try:
            await message.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception:
            failed += 1
            continue

    # await message.answer(
    #     f"Jo'natilgan xabar: {text}"
    # )

    await message.answer(
        f"✅ Xabar yuborildi.\n\n"
        f"Jo'natilgan xabar: {text}\n"
        f"📤 Jo‘natilgan: <b>{sent}</b>\n"
        f"⚠️ Yuborilmagan: <b>{failed}</b>",
        parse_mode="HTML"
    )
    await state.clear()
