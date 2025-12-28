# superadmins/own_special_message.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_back_to_menu_keyboard

router = Router()


class BarberMessageStates(StatesGroup):
    waiting_for_message = State()


@router.message(F.text == "✉️ Maxsus xabar")
async def start_special_message(message: types.Message, state: FSMContext):
    """Maxsus xabar yuborishni boshlash"""
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")
    
    # Mijozlar sonini aniqlash
    barber_name = f"{barber.barber_first_name} {barber.barber_last_name or ''}"
    
    async with async_session() as session:
        result = await session.execute(
            select(Order.user_id).where(Order.barber_id == barber_name).distinct()
        )
        client_count = len(result.scalars().all())
    
    await state.set_state(BarberMessageStates.waiting_for_message)
    
    await message.answer(
        f"✏️ <b>Maxsus xabar yuborish</b>\n\n"
        f"Sizning xabaringizni yozing.\n"
        f"U barcha mijozlaringizga yuboriladi.\n\n"
        f"👥 Mijozlar: <b>{client_count}</b>\n\n"
        f"❌ Bekor qilish uchun /cancel",
        parse_mode="HTML"
    )


@router.message(BarberMessageStates.waiting_for_message)
async def send_special_message(message: types.Message, state: FSMContext):
    """Xabarni barcha mijozlarga yuborish"""
    if message.text == "/cancel":
        await state.clear()
        return await message.answer(
            "❌ Bekor qilindi.",
            reply_markup=get_back_to_menu_keyboard()
        )
    
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)
    
    if not barber:
        await state.clear()
        return await message.answer("❌ Xatolik yuz berdi.")
    
    text = message.text.strip()
    
    if len(text) < 10:
        return await message.answer(
            "❌ Xabar juda qisqa. Kamida 10 ta belgi kiriting."
        )
    
    # Mijozlar ro'yxatini olish
    barber_name = f"{barber.barber_first_name} {barber.barber_last_name or ''}"
    
    async with async_session() as session:
        result = await session.execute(
            select(Order.user_id, Order.fullname).where(
                Order.barber_id == barber_name
            ).distinct()
        )
        clients = result.all()
    
    if not clients:
        await state.clear()
        return await message.answer(
            "❌ Sizda hali mijozlar yo'q.",
            reply_markup=get_back_to_menu_keyboard()
        )
    
    # Yuborish jarayonini boshlash
    status_msg = await message.answer("📨 Xabarlar yuborilmoqda...")
    
    sent = 0
    failed = 0
    
    for client in clients:
        try:
            await message.bot.send_message(
                chat_id=client.user_id,
                text=(
                    f"✉️ <b>Xabar {barber.barber_first_name} ustadan:</b>\n\n"
                    f"{text}\n\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"<i>Bu maxsus xabar sizning ustangiz tomonidan yuborildi.</i>"
                ),
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
            continue
    
    await status_msg.delete()
    await state.clear()
    
    result_text = (
        f"✅ <b>Xabar yuborildi!</b>\n\n"
        f"📨 Yuborilgan xabar:\n"
        f"<code>{text[:100]}{'...' if len(text) > 100 else ''}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"✅ Muvaffaqiyatli: <b>{sent}</b>\n"
        f"❌ Xato: <b>{failed}</b>\n"
        f"👥 Jami: <b>{len(clients)}</b>"
    )
    
    await message.answer(
        result_text,
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )
