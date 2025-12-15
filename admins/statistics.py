#admins/statistics.py
import logging
from datetime import date
from typing import Union

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from sqlalchemy import select, func, and_
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import Order, Barbers

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.sticker)
async def ignore_stickers(message: types.Message):
    await message.answer("⚠️ Iltimos, stiker emas, faqat matn yuboring.")


async def send_overall_stats(target: Union[types.Message, types.Chat, types.CallbackQuery]):
    """Send overall statistics. `target` should support `.answer(...)` (Message or CallbackQuery)."""
    today = date.today()

    try:
        async with async_session() as session:
            total_orders = await session.scalar(select(func.count(Order.id)))
            total_users = await session.scalar(select(func.count(func.distinct(Order.user_id))))
            today_orders = await session.scalar(select(func.count(Order.id)).where(Order.booked_date == today))
            today_users = await session.scalar(
                select(func.count(func.distinct(Order.user_id))).where(Order.booked_date == today)
            )
            barbers = (await session.execute(select(Barbers))).scalars().all()

    except SQLAlchemyError as e:
        logger.exception("DB error when fetching overall stats: %s", e)
        # try to answer via target; if not possible, just return
        try:
            if hasattr(target, "answer"):
                await target.answer("❌ Ma'lumotlarni olishda xatolik yuz berdi.")
        except Exception as send_err:
            logger.exception("Failed to notify about DB error: %s", send_err)
        return

    # normalize None -> 0
    total_orders = int(total_orders or 0)
    total_users = int(total_users or 0)
    today_orders = int(today_orders or 0)
    today_users = int(today_users or 0)

    # build inline keyboard
    if barbers:
        buttons = [
            [InlineKeyboardButton(text=f"💈 {b.barber_first_name} {b.barber_last_name}", callback_data=f"barber:{int(b.id)}")]
            for b in barbers
        ]
    else:
        buttons = [[InlineKeyboardButton(text="❌ Barberlar mavjud emas", callback_data="none")]]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        f"📊 <b>Umumiy Statistika</b>\n\n"
        f"📦 <b>Jami buyurtmalar:</b> {total_orders}\n"
        f"👥 <b>Foydalanuvchilar soni:</b> {total_users}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {today_orders}\n"
        f"🙋‍♂️ <b>Bugungi foydalanuchilar:</b> {today_users}\n\n"
        f"💈 <b>Barberlar bo‘yicha statistika:</b>"
    )

    # prefer target.answer(); callback.query has .message but also supports .answer if it's a CallbackQuery
    try:
        if isinstance(target, CallbackQuery):
            # send as a new message into the chat where callback came from
            await target.message.answer(text, reply_markup=markup, parse_mode="HTML")
            await target.answer()  # remove loading state
        elif hasattr(target, "answer"):
            await target.answer(text, reply_markup=markup, parse_mode="HTML")
        else:
            logger.warning("send_overall_stats: target has no .answer attribute: %r", type(target))
    except Exception as e:
        logger.exception("Failed to send overall stats message: %s", e)


@router.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    await send_overall_stats(message)


@router.callback_query(F.data.startswith("barber:"))
async def barber_stats(callback: types.CallbackQuery):
    try:
        _, barber_id_raw = callback.data.split(":", 1)
        barber_id = int(barber_id_raw)
    except Exception as e:
        logger.warning("Invalid callback.data for barber_stats: %r (%s)", callback.data, e)
        return await callback.answer("❌ Noto‘g‘ri barber ID!", show_alert=True)

    today = date.today()

    try:
        async with async_session() as session:
            barber = await session.get(Barbers, barber_id)
            if not barber:
                return await callback.answer("❌ Barber topilmadi!", show_alert=True)

            # 🔥 Muammo shu joyda edi — endi fullname bo‘yicha solishtiramiz:
            total_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.barber_id == barber.barber_first_name)
            )
            today_orders = await session.scalar(
                select(func.count(Order.id)).where(
                    and_(Order.barber_id == barber.barber_first_name, func.date(Order.booked_date) == today)
                )
            )
    except SQLAlchemyError as e:
        logger.exception("DB error when fetching barber stats: %s", e)
        return await callback.answer("❌ Ma'lumotni olishda xatolik yuz berdi.", show_alert=True)

    total_orders = int(total_orders or 0)
    today_orders = int(today_orders or 0)

    text = (
        f"💈 <b>{barber.barber_first_name}</b> statistikasi:\n\n"
        f"📦 <b>Jami buyurtmalar:</b> {total_orders}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {today_orders}"
    )

    back_button = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_stats")]]
    )

    try:
        await callback.message.edit_text(text, reply_markup=back_button, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_button, parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data == "back_to_stats")
async def back_to_stats(callback: CallbackQuery):
    try:
        if callback.message:
            try:
                await callback.message.delete()
            except Exception:
                logger.debug("Could not delete callback.message (maybe already deleted).")
        await send_overall_stats(callback)
        await callback.answer()
    except Exception as e:
        logger.exception("Error in back_to_stats: %s", e)
        await callback.answer("❌ Qaytishda xatolik yuz berdi.", show_alert=True)


@router.callback_query(F.data == "none")
async def none_callback(callback: CallbackQuery):
    await callback.answer("ℹ️ Hozircha maʼlumot yo‘q.", show_alert=True)
