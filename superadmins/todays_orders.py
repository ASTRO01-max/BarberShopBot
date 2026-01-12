from aiogram import Router, types, F
from sqlalchemy import select, and_
from datetime import date, datetime
from sql.db import async_session
from sql.models import Order, Services
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_order_actions_keyboard

router = Router()


async def _service_name(session, service_id_raw: str) -> str:
    if not service_id_raw:
        return "Noma'lum"
    # service_id string bo'lishi mumkin
    try:
        service = await session.get(Services, int(service_id_raw))
        if service:
            return service.name
    except Exception:
        pass
    return str(service_id_raw)


@router.message(F.text == "📋 Bugungi buyurtmalar")
async def show_todays_orders(message: types.Message):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    today = date.today()
    barber_key = str(barber.id)  # MUHIM: orders.barber_id = barber.id (string ko'rinishda)

    async with async_session() as session:
        result = await session.execute(
            select(Order).where(
                and_(Order.barber_id == barber_key, Order.date == today)
            ).order_by(Order.time)
        )
        orders = result.scalars().all()

        if not orders:
            return await message.answer(
                "📭 <b>Bugungi buyurtmalar yo'q</b>\n\n"
                "Hozircha bugun uchun navbatlar mavjud emas.",
                parse_mode="HTML"
            )

        await message.answer(
            f"📋 <b>Bugungi buyurtmalar</b>\n"
            f"Jami: <b>{len(orders)}</b>\n\n"
            f"Quyida bugungi barcha navbatlar ko'rsatilgan:",
            parse_mode="HTML"
        )

        current_time = datetime.now()

        for idx, order in enumerate(orders, 1):
            service_name = await _service_name(session, order.service_id)

            order_datetime = datetime.combine(today, order.time)
            time_diff = order_datetime - current_time

            minutes_left = int(time_diff.total_seconds() / 60)
            if time_diff.total_seconds() < 0:
                status = "⏰ O'tgan"
                time_status = ""
            elif time_diff.total_seconds() < 1800:
                status = "🔴 Yaqinlashmoqda"
                time_status = f"\n⚠️ <b>{minutes_left} daqiqadan keyin</b>"
            elif time_diff.total_seconds() < 3600:
                status = "🟡 Yaqin"
                time_status = f"\n⏰ {minutes_left} daqiqadan keyin"
            else:
                status = "🟢 Kutilmoqda"
                time_status = ""

            text = (
                f"--------------------\n"
                f"<b>Navbat #{idx}</b> {status}\n\n"
                f"👤 <b>Mijoz:</b> {order.fullname}\n"
                f"📞 <b>Telefon:</b> <code>{order.phonenumber}</code>\n"
                f"✂️ <b>Xizmat:</b> {service_name}\n"
                f"⏰ <b>Vaqt:</b> {order.time.strftime('%H:%M')}"
                f"{time_status}\n"
                f"--------------------"
            )

            keyboard = get_order_actions_keyboard(
                order_id=order.id,
                client_tg_id=order.user_id,
                phone=order.phonenumber
            )

            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

        await message.answer(
            "--------------------\n"
            f"📊 <b>Jami:</b> {len(orders)} ta buyurtma",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("barber_notify_"))
async def notify_client(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            return await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)

        service_name = await _service_name(session, order.service_id)

        try:
            await callback.bot.send_message(
                chat_id=order.user_id,
                text=(
                    f"🔔 <b>Eslatma!</b>\n\n"
                    f"Hurmatli {order.fullname}!\n\n"
                    f"Sizning navbatingiz yaqinlashmoqda:\n"
                    f"⏰ <b>Vaqt:</b> {order.time.strftime('%H:%M')}\n"
                    f"✂️ <b>Xizmat:</b> {service_name}\n\n"
                    f"Iltimos, o'z vaqtida keling!"
                ),
                parse_mode="HTML"
            )
            await callback.answer("✅ Xabar yuborildi!", show_alert=True)
        except Exception:
            await callback.answer("❌ Xabar yuborishda xatolik yuz berdi!", show_alert=True)


@router.callback_query(F.data.startswith("barber_complete_"))
async def complete_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            return await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)

        client_name = order.fullname
        client_id = order.user_id

        await session.delete(order)
        await session.commit()

    try:
        await callback.bot.send_message(
            chat_id=client_id,
            text=(
                f"✅ <b>Xizmat yakunlandi!</b>\n\n"
                f"Hurmatli {client_name}!\n\n"
                f"Xizmatimizdan foydalanganingiz uchun tashakkur!\n"
                f"Keyingi safar ham sizni kutamiz! 💈"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.message.edit_text(
        f"✅ <b>Buyurtma yakunlandi!</b>\n\nMijoz: {client_name}",
        parse_mode="HTML"
    )
    await callback.answer("✅ Buyurtma yakunlandi!")
