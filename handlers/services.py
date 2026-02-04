# handlers/services.py
from aiogram import Router, types
from sqlalchemy.future import select
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from sql.db import async_session
from sql.models import Services
from keyboards.booking_keyboards import back_button
from utils.emoji_map import SERVICE_EMOJIS

router = Router()


def service_nav_keyboard(index: int, total: int, service_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"services_prev_{index}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"services_next_{index}"),
            ],
            [
                InlineKeyboardButton(text="🗓️ Navbat boshlash", callback_data=f"book_service_{service_name}"),
            ],
            [
                InlineKeyboardButton(text="🔙 Orqaga", callback_data="back"),
            ],
        ]
    )


async def send_service(callback: types.CallbackQuery, services, index: int):
    service = services[index]

    emoji = SERVICE_EMOJIS.get(service.name, "🔹")

    caption = (
        f"{emoji} <b>{service.name}</b>\n"
        f"💵 <b>Narx:</b> {service.price} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {service.duration}\n"
        f"\n📌 <i>({index + 1} / {len(services)})</i>"
    )

    keyboard = service_nav_keyboard(index, len(services), service.name)

    # Sizning modelda rasm Services.photo ichida saqlanadi (file_id)
    service_photo = getattr(service, "photo", None)

    if service_photo:
        try:
            await callback.message.edit_media(
                types.InputMediaPhoto(
                    media=service_photo,
                    caption=caption,
                    parse_mode="HTML",
                ),
                reply_markup=keyboard,
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(
                photo=service_photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
    else:
        try:
            await callback.message.edit_text(
                caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )


async def show_services(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        services = result.scalars().all()

    if not services:
        await callback.message.edit_text(
            "⚠️ Hozircha xizmatlar mavjud emas.",
            reply_markup=back_button(),
        )
        return

    await send_service(callback, services, 0)


async def navigate_services(callback: types.CallbackQuery):
    action, index = callback.data.split("_")[1], int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        services = result.scalars().all()

    if not services:
        await callback.answer("⚠️ Xizmatlar topilmadi.", show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(services)
    else:
        index = (index - 1) % len(services)

    await send_service(callback, services, index)
    await callback.answer()
