import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sql.db import async_session
from sql.models import Barbers, Order, Services
from sql.db_barber_inbox import inbox_add, inbox_get_undelivered, inbox_mark_delivered
from .panel_presence import is_barber_active

logger = logging.getLogger(__name__)


def _notify_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Batafsil ko'rish",
                    callback_data=f"barber_order_detail:{order_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Yopish",
                    callback_data=f"barber_order_close:{order_id}"
                ),
            ]
        ]
    )


async def _service_name(session, service_id_raw: str) -> str:
    if not service_id_raw:
        return "Noma'lum"
    try:
        sid = int(service_id_raw)
        service = await session.get(Services, sid)
        if service:
            return service.name
    except Exception:
        pass
    return str(service_id_raw)


async def _get_barber_tg_id(barber_db_id: int) -> int | None:
    async with async_session() as session:
        try:
            barber = await session.get(Barbers, int(barber_db_id))
            if barber and getattr(barber, "tg_id", None):
                return int(barber.tg_id)
            return None
        except Exception:
            logger.exception("_get_barber_tg_id failed")
            return None


async def _build_short_text(order_id: int) -> str:
    async with async_session() as session:
        order = await session.get(Order, int(order_id))
        if not order:
            return "⚠️ Buyurtma topilmadi."
        service_name = await _service_name(session, order.service_id)

        # Qisqa preview uchun username fallback
        username = "—"

        return (
            "🆕 <b>Yangi navbat!</b>\n\n"
            f"👤 <b>Mijoz:</b> {order.fullname}\n"
            f"💈 <b>Xizmat:</b> {service_name}\n"
            f"📅 <b>Sana:</b> {order.date}\n"
            f"🕒 <b>Vaqt:</b> {order.time}\n"
            f"🧾 <b>Order ID:</b> {order.id}\n"
            f"👤 <b>Username:</b> {username}"
        )


async def notify_barber_realtime(bot: Bot, order_id: int, barber_db_id: int) -> None:
    barber_tg_id = await _get_barber_tg_id(barber_db_id)
    if not barber_tg_id:
        logger.warning("notify_barber_realtime: barber tg_id topilmadi, barber_db_id=%s", barber_db_id)
        return

    inbox_row = await inbox_add(order_id=int(order_id), barber_tg_id=int(barber_tg_id))
    if not inbox_row:
        return

    if is_barber_active(barber_tg_id):
        try:
            text = await _build_short_text(order_id)
            await bot.send_message(
                chat_id=barber_tg_id,
                text=text,
                parse_mode="HTML",
                reply_markup=_notify_keyboard(order_id),
                disable_web_page_preview=True
            )
            await inbox_mark_delivered(inbox_row.id)
        except Exception:
            logger.exception("notify_barber_realtime send_message failed")
            # yuborilmasa inboxda qoladi


async def flush_undelivered_to_barber(bot: Bot, barber_tg_id: int) -> None:
    rows = await inbox_get_undelivered(int(barber_tg_id))
    if not rows:
        return

    for row in rows:
        try:
            text = await _build_short_text(row.order_id)
            await bot.send_message(
                chat_id=barber_tg_id,
                text=text,
                parse_mode="HTML",
                reply_markup=_notify_keyboard(row.order_id),
                disable_web_page_preview=True
            )
            await inbox_mark_delivered(row.id)
        except Exception:
            logger.exception("flush_undelivered_to_barber failed for order_id=%s", row.order_id)
            continue
