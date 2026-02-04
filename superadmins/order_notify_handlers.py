import logging
from aiogram import Router, types, F
from sql.db import async_session
from sql.models import Order
from sql.db_barber_inbox import inbox_mark_seen_by_order

logger = logging.getLogger(__name__)
router = Router()


def _order_detail_text(order: Order, username: str) -> str:
    # id, user_id, barber_id ni CHIQARMAYMIZ
    return (
        "📌 <b>Buyurtma batafsil</b>\n\n"
        f"👤 <b>Username:</b> {username}\n"
        f"👤 <b>Fullname:</b> {order.fullname}\n"
        f"📱 <b>Phone:</b> {order.phonenumber}\n"
        f"💈 <b>Service:</b> {order.service_id}\n"
        f"🧑‍🎤 <b>Barber name:</b> {order.barber_id_name}\n"
        f"📅 <b>Navbat sanasi:</b> {order.date}\n"
        f"🕒 <b>Navbat vaqti:</b> {order.time}\n"
        f"🗓 <b>Yaratilgan sana:</b> {order.booked_date}\n"
        f"⏱ <b>Yaratilgan vaqt:</b> {order.booked_time}\n"
    )


@router.callback_query(F.data.startswith("barber_order_detail:"))
async def barber_order_detail(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    barber_tg_id = callback.from_user.id

    async with async_session() as session:
        order = await session.get(Order, order_id)

    if not order:
        await callback.answer("Buyurtma topilmadi", show_alert=True)
        return

    # Username majburiy:
    username = "username yo'q"
    try:
        chat = await callback.bot.get_chat(int(order.user_id))
        if getattr(chat, "username", None):
            username = f"@{chat.username}"
        else:
            username = "username yo'q"
    except Exception:
        username = "username yo'q"

    await inbox_mark_seen_by_order(order_id=order_id, barber_tg_id=barber_tg_id)

    text = _order_detail_text(order, username)

    # Detailni xabar ichida chiqaramiz
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=callback.message.reply_markup
        )
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=callback.message.reply_markup)

    await callback.answer()


@router.callback_query(F.data.startswith("barber_order_close:"))
async def barber_order_close(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    barber_tg_id = callback.from_user.id

    await inbox_mark_seen_by_order(order_id=order_id, barber_tg_id=barber_tg_id)

    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_text("✅ Yopildi")
        except Exception:
            pass

    await callback.answer("Yopildi ✅")
