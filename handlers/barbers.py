# handlers/barbers.py
from aiogram import Router, types
from sqlalchemy.future import select
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from sql.db import async_session
from sql.models import Barbers, BarberPhotos
from keyboards.booking_keyboards import back_button

router = Router()


def barber_nav_keyboard(index: int, total: int, barber_id: int, is_paused: bool):
    inline_keyboard = [
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
    ]

    # ✅ Pause bo'lsa — "Navbat olish" tugmasi chiqmaydi
    if not is_paused:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text="🗓️ Navbat olish",
                    callback_data=f"book_barber_{barber_id}"
                )
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="🔙 Orqaga",
                callback_data="back"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


async def send_barber(callback: types.CallbackQuery, barbers, index: int):
    barber = barbers[index]

    lines = []

    # Ism
    full_name = f"{barber.barber_first_name or ''} {barber.barber_last_name or ''}".strip()
    lines.append(f"👨‍🎤 <b>{full_name}</b>\n")

    # Status
    if getattr(barber, "is_paused", False):
        lines.append("ℹ️ <b>Holati:</b> ⛔️ Bugun ishlamaydi\n")
    else:
        lines.append("ℹ️ <b>Holati:</b> 🕒 Bugun ishda\n")

    # Faqat mavjud bo'lgan maydonlar
    if barber.experience:
        lines.append(f"💼 <b>Tajribasi:</b> {barber.experience}\n")

    if barber.work_days:
        lines.append(f"📅 <b>Ish kunlari:</b> {barber.work_days}\n")

    if barber.work_time:
        lines.append(f"⏰ <b>Ish vaqti:</b> {barber.work_time}\n")

    if barber.breakdown:
        lines.append(f"⏸️ <b>Tanafus vaqti:</b> {barber.breakdown}\n")

    if barber.phone:
        lines.append(f"📞 <b>Aloqa:</b> <code>{barber.phone}</code>\n")

    lines.append(f"\n📌 <i>({index + 1} / {len(barbers)})</i>")

    caption = "".join(lines)

    keyboard = barber_nav_keyboard(
        index,
        len(barbers),
        barber.id,
        getattr(barber, "is_paused", False)
    )

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
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
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
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


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
