from aiogram import F, Router, types
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from sqlalchemy import select

from sql.db import async_session
from sql.db_barbers_expanded import (
    add_service_to_barber,
    get_barber_services,
    remove_service_from_barber,
)
from sql.models import Barbers, Services
from utils.emoji_map import SERVICE_EMOJIS

router = Router()

BARBER_SERVICE_NAV_PREFIX = "barber_srv"
BARBER_SERVICE_PREV_CB = f"{BARBER_SERVICE_NAV_PREFIX}_prev_"
BARBER_SERVICE_NEXT_CB = f"{BARBER_SERVICE_NAV_PREFIX}_next_"
BARBER_SERVICE_TOGGLE_CB = f"{BARBER_SERVICE_NAV_PREFIX}_toggle_"


async def is_barber(tg_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none() is not None


async def get_barber_by_tg_id(tg_id: int):
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none()


async def _fetch_services() -> list[Services]:
    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
    return result.scalars().all()


def _service_toggle_keyboard(
    index: int,
    service_id: int,
    is_selected: bool,
) -> InlineKeyboardMarkup:
    action_text = "❌ Xizmatni chiqarib tashlash" if is_selected else "✅ Xizmatni kiritish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{BARBER_SERVICE_PREV_CB}{index}",
                ),
                InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"{BARBER_SERVICE_NEXT_CB}{index}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=action_text,
                    callback_data=f"{BARBER_SERVICE_TOGGLE_CB}{service_id}_{index}",
                )
            ],
        ]
    )


def _service_caption(service: Services, index: int, total: int) -> str:
    emoji = SERVICE_EMOJIS.get(service.name, "🔹")
    return (
        f"💈 <b>Xizmatni tanlang</b>\n\n"
        f"{emoji} <b>{service.name}</b>\n"
        f"💵 <b>Narx:</b> {service.price} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {service.duration}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _render_catalog_callback(
    callback: CallbackQuery,
    caption: str,
    keyboard: InlineKeyboardMarkup,
    photo: str | None = None,
):
    if photo:
        try:
            await callback.message.edit_media(
                InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                reply_markup=keyboard,
            )
            return
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(
                photo=photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

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


async def _send_catalog_message(
    message: types.Message,
    caption: str,
    keyboard: InlineKeyboardMarkup,
    photo: str | None = None,
):
    if photo:
        await message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _show_service_page_callback(
    callback: CallbackQuery,
    barber_id: int,
    index: int = 0,
    services: list[Services] | None = None,
) -> bool:
    if services is None:
        services = await _fetch_services()

    if not services:
        await _render_catalog_callback(
            callback,
            "⚠️ Hozircha xizmatlar mavjud emas.",
            InlineKeyboardMarkup(inline_keyboard=[]),
        )
        return False

    index = index % len(services)
    service = services[index]
    selected_service_ids = set(await get_barber_services(barber_id))
    keyboard = _service_toggle_keyboard(
        index=index,
        service_id=int(service.id),
        is_selected=int(service.id) in selected_service_ids,
    )
    await _render_catalog_callback(
        callback,
        _service_caption(service, index, len(services)),
        keyboard,
        getattr(service, "photo", None),
    )
    return True


async def _show_service_page_message(
    message: types.Message,
    barber_id: int,
    index: int = 0,
    services: list[Services] | None = None,
) -> bool:
    if services is None:
        services = await _fetch_services()

    if not services:
        await message.answer("⚠️ Hozircha xizmatlar mavjud emas.")
        return False

    index = index % len(services)
    service = services[index]
    selected_service_ids = set(await get_barber_services(barber_id))
    keyboard = _service_toggle_keyboard(
        index=index,
        service_id=int(service.id),
        is_selected=int(service.id) in selected_service_ids,
    )
    await _send_catalog_message(
        message,
        _service_caption(service, index, len(services)),
        keyboard,
        getattr(service, "photo", None),
    )
    return True


@router.message(F.text == "➕ Xizmat kiritish")
async def show_add_service_menu(message: types.Message):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    services = await _fetch_services()
    await _show_service_page_message(message, barber.id, index=0, services=services)


@router.callback_query(F.data.startswith(BARBER_SERVICE_PREV_CB))
@router.callback_query(F.data.startswith(BARBER_SERVICE_NEXT_CB))
async def barber_service_nav(callback: CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    action = parts[2]
    try:
        index = int(parts[3])
    except ValueError:
        await callback.answer("❌ Noto'g'ri sahifa.", show_alert=True)
        return

    services = await _fetch_services()
    if not services:
        await callback.answer("⚠️ Xizmatlar mavjud emas.", show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(services)
    elif action == "prev":
        index = (index - 1) % len(services)
    else:
        await callback.answer("❌ Noto'g'ri navigatsiya.", show_alert=True)
        return

    await _show_service_page_callback(callback, barber.id, index=index, services=services)
    await callback.answer()


@router.callback_query(F.data.startswith(BARBER_SERVICE_TOGGLE_CB))
async def barber_service_toggle(callback: CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) != 5:
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    if not parts[3].isdigit() or not parts[4].isdigit():
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    service_id = int(parts[3])
    page_index = int(parts[4])

    services = await _fetch_services()
    if not any(int(service.id) == service_id for service in services):
        await callback.answer("❌ Xizmat topilmadi.", show_alert=True)
        return

    selected_service_ids = set(await get_barber_services(barber.id))
    if service_id in selected_service_ids:
        removed = await remove_service_from_barber(barber.id, service_id)
        notice = "✅ Xizmat ro'yxatdan chiqarildi." if removed else "⚠️ Xizmat allaqachon chiqarilgan."
    else:
        added = await add_service_to_barber(barber.id, service_id)
        notice = "✅ Xizmat ro'yxatga qo'shildi." if added else "⚠️ Xizmat allaqachon qo'shilgan."

    await _show_service_page_callback(callback, barber.id, index=page_index, services=services)
    await callback.answer(notice)
