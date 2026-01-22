#superadmins/own_special_message.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sql.db import async_session
from sql.models import Order
from .superadmin import get_barber_by_tg_id
from utils.states import BarberPage

router = Router()


@router.message(F.text == "✉️ Maxsus xabar")
async def start_special_message(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    barber_key = str(barber.id)

    async with async_session() as session:
        result = await session.execute(
            select(Order.user_id).where(Order.barber_id == barber_key).distinct()
        )
        client_ids = result.scalars().all()

    await state.set_state(BarberPage.waiting_for_message)

    await message.answer(
        f"✏️ <b>Maxsus xabar yuborish</b>\n\n"
        f"Iltimos, yubormoqchi bo'lgan xabaringizni kiriting.\n"
        f"U barcha mijozlaringizga yuboriladi.\n\n"
        f"👥 Mijozlar soni: <b>{len(client_ids)}</b>\n\n"
        f"❌ Bekor qilish: /cancel",
        parse_mode="HTML"
    )


@router.message(BarberPage.waiting_for_message)
async def send_special_message(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.")

    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await state.clear()
        return await message.answer("❌ Xatolik yuz berdi.")

    text = message.text.strip()
    if len(text) < 10:
        return await message.answer("❌ Xabar juda qisqa. Kamida 10 ta belgi kiriting.")

    barber_key = str(barber.id)

    async with async_session() as session:
        result = await session.execute(
            select(Order.user_id).where(Order.barber_id == barber_key).distinct()
        )
        client_ids = result.scalars().all()

    if not client_ids:
        await state.clear()
        return await message.answer("❌ Sizda hali mijozlar yo'q.")

    status_msg = await message.answer("📨 Xabarlar yuborilmoqda...")

    sent = 0
    failed = 0

    for client_id in client_ids:
        try:
            await message.bot.send_message(
                chat_id=client_id,
                text=(
                    f"📣 <b>{barber.barber_first_name} ustadan xabar</b>\n\n"
                    f"{text}\n\n"
                    f"--------------------\n"
                    f"<i>Bu maxsus xabar sizning ustangiz tomonidan yuborildi.</i>"
                ),
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1

    try:
        await status_msg.delete()
    except Exception:
        pass

    await state.clear()

    result_text = (
        f"✅ <b>Xabar yuborildi</b>\n\n"
        f"📨 Yuborilgan xabar:\n"
        f"<code>{text[:100]}{'...' if len(text) > 100 else ''}</code>\n\n"
        f"--------------------\n"
        f"✅ Muvaffaqiyatli: <b>{sent}</b>\n"
        f"❌ Xato: <b>{failed}</b>\n"
        f"👥 Jami: <b>{len(client_ids)}</b>"
    )

    await message.answer(result_text, parse_mode="HTML")
