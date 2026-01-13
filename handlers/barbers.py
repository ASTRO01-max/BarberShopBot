# handlers/barbers.py
from aiogram import Router, types
from sqlalchemy.future import select
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from sql.db import async_session
from sql.models import Barbers, BarberPhotos
from keyboards.booking_keyboards import back_button

router = Router()


# Pagination tugmalari
def barber_nav_keyboard(index: int, total: int, barber_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"barber_prev_{index}"
                ),
                InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"barber_next_{index}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗓️ Navbat olish",
                    callback_data=f"book_barber_{barber_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data="back"
                )
            ],
        ]
    )


# Bitta barberni chiqarish
async def send_barber(callback: types.CallbackQuery, barbers, index: int):
    barber = barbers[index]

    caption = (
        f"👨‍🎤 <b>{barber.barber_first_name} {barber.barber_last_name}</b>\n\n"
        f"💼 <b>Tajribasi:</b> {barber.experience}\n"
        f"📅 <b>Ish kunlari:</b> {barber.work_days}\n"
        f"📞 <b>Aloqa:</b> <code>{barber.phone}</code>\n\n"
        f"📌 <i>({index + 1} / {len(barbers)})</i>"
    )

    keyboard = barber_nav_keyboard(index, len(barbers), barber.id)

    async with async_session() as session:
        result = await session.execute(
            select(BarberPhotos.photo)
            .where(BarberPhotos.barber_id == barber.id)
            .order_by(BarberPhotos.id.desc())
            .limit(1)
        )
        barber_photo = result.scalar()

    if barber_photo:
        try:
            await callback.message.edit_media(
                types.InputMediaPhoto(
                    media=barber_photo,
                    caption=caption,
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        except:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=barber_photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    else:
        try:
            await callback.message.edit_text(
                caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except:
            await callback.message.delete()
            await callback.message.answer(
                caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


# Barberlar ro‘yxati
async def show_barbers(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(Barbers))
        barbers = result.scalars().all()

    if not barbers:
        await callback.message.edit_text(
            "⚠️ Ustalar mavjud emas.",
            reply_markup=back_button()
        )
        return

    await send_barber(callback, barbers, 0)


# Next / Prev
async def navigate_barbers(callback: types.CallbackQuery):
    action, index = callback.data.split("_")[1], int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(select(Barbers))
        barbers = result.scalars().all()

    if action == "next":
        index = (index + 1) % len(barbers)
    else:
        index = (index - 1) % len(barbers)

    await send_barber(callback, barbers, index)
    await callback.answer()
