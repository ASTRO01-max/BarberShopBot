from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.booking_keyboards import back_button
from sql.db_services import list_services_ordered
from utils.emoji_map import SERVICE_EMOJIS
from utils.service_pricing import build_service_price_lines

router = Router()


def service_nav_keyboard(index: int, total: int, service_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"services_prev_{index}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"services_next_{index}"),
            ],
            [
                InlineKeyboardButton(
                    text="🗓️ Navbat boshlash",
                    callback_data=f"book_service_{service_id}",
                ),
            ],
            [
                InlineKeyboardButton(text="🔙 Orqaga", callback_data="back"),
            ],
        ]
    )


async def send_service(callback: types.CallbackQuery, services, index: int):
    service = services[index]
    emoji = SERVICE_EMOJIS.get(service.name, "🔹")
    price_lines = "\n".join(build_service_price_lines(service))

    caption = (
        f"{emoji} <b>{service.name}</b>\n"
        f"{price_lines}\n"
        f"🕒 <b>Davomiyligi:</b> {service.duration}\n"
        f"\n📌 <i>({index + 1} / {len(services)})</i>"
    )

    keyboard = service_nav_keyboard(index, len(services), service.id)
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
    services = await list_services_ordered()

    if not services:
        await callback.message.edit_text(
            "⚠️ Hozircha xizmatlar mavjud emas.",
            reply_markup=back_button(),
        )
        return

    await send_service(callback, services, 0)


async def navigate_services(callback: types.CallbackQuery):
    action, index = callback.data.split("_")[1], int(callback.data.split("_")[2])
    services = await list_services_ordered()

    if not services:
        await callback.answer("⚠️ Xizmatlar topilmadi.", show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(services)
    else:
        index = (index - 1) % len(services)

    await send_service(callback, services, index)
    await callback.answer()
