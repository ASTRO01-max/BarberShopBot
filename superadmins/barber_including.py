from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from sqlalchemy import select

from sql.db import async_session
from sql.db_barber_services import (
    create_barber_service,
    delete_barber_service,
    get_barber_service_by_id,
    get_barber_service_by_pair,
    get_barber_services,
    normalize_duration_minutes,
    normalize_money,
    update_barber_service,
)
from sql.models import Barbers, Services
from utils.emoji_map import SERVICE_EMOJIS
from utils.service_pricing import (
    build_service_price_lines,
    format_duration_minutes,
)

router = Router()

BARBER_SERVICE_NAV_CB = "barber_srv_nav"
BARBER_SERVICE_ADD_CB = "barber_srv_add"
BARBER_SERVICE_PRICE_CB = "barber_srv_price"
BARBER_SERVICE_DURATION_CB = "barber_srv_duration"
BARBER_SERVICE_DELETE_CB = "barber_srv_delete"
CANCEL_HINT = "\n\nBekor qilish uchun /cancel yuboring."


class BarberServiceStates(StatesGroup):
    waiting_for_price = State()
    waiting_for_duration = State()
    waiting_for_update_price = State()
    waiting_for_update_duration = State()


async def is_barber(tg_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Barbers.id).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none() is not None


async def get_barber_by_tg_id(tg_id: int):
    async with async_session() as session:
        result = await session.execute(select(Barbers).where(Barbers.tg_id == tg_id))
        return result.scalar_one_or_none()


async def _fetch_services() -> list[Services]:
    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        return list(result.scalars().all())


async def _selected_service_map(barber_id: int):
    items = await get_barber_services(barber_id)
    return {int(item.service_id): item for item in items}


def _service_keyboard(
    *,
    index: int,
    service_id: int,
    barber_service_id: int | None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"{BARBER_SERVICE_NAV_CB}:prev:{index}",
            ),
            InlineKeyboardButton(
                text="➡️ Keyingi",
                callback_data=f"{BARBER_SERVICE_NAV_CB}:next:{index}",
            ),
        ],
    ]

    if barber_service_id is None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Xizmatlarimga qo'shish",
                    callback_data=f"{BARBER_SERVICE_ADD_CB}:{service_id}:{index}",
                )
            ]
        )
    else:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="💵 Narxni o'zgartirish",
                        callback_data=f"{BARBER_SERVICE_PRICE_CB}:{barber_service_id}:{index}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🕒 Davomiylikni o'zgartirish",
                        callback_data=f"{BARBER_SERVICE_DURATION_CB}:{barber_service_id}:{index}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Xizmatlarimdan o'chirish",
                        callback_data=f"{BARBER_SERVICE_DELETE_CB}:{barber_service_id}:{index}",
                    )
                ],
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _service_caption(
    service: Services,
    index: int,
    total: int,
    barber_service=None,
) -> str:
    emoji = SERVICE_EMOJIS.get(service.name, "🔹")
    lines = [
        "💈 <b>Xizmatlarim</b>",
        "",
        f"{emoji} <b>{service.name}</b>",
    ]

    if barber_service is None:
        lines.append("Holat: <b>ulanmagan</b>")
    else:
        lines.append("Holat: <b>ulangan</b>")
        lines.extend(build_service_price_lines(barber_service))
        lines.append(
            f"🕒 <b>Davomiyligi:</b> {format_duration_minutes(barber_service.duration_minutes)}"
        )

    lines.extend(["", f"📌 <i>({index + 1} / {total})</i>"])
    return "\n".join(lines)


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
    selected = await _selected_service_map(barber_id)
    barber_service = selected.get(int(service.id))
    keyboard = _service_keyboard(
        index=index,
        service_id=int(service.id),
        barber_service_id=(int(barber_service.id) if barber_service else None),
    )
    await _render_catalog_callback(
        callback,
        _service_caption(service, index, len(services), barber_service),
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
    selected = await _selected_service_map(barber_id)
    barber_service = selected.get(int(service.id))
    keyboard = _service_keyboard(
        index=index,
        service_id=int(service.id),
        barber_service_id=(int(barber_service.id) if barber_service else None),
    )
    await _send_catalog_message(
        message,
        _service_caption(service, index, len(services), barber_service),
        keyboard,
        getattr(service, "photo", None),
    )
    return True


def _parse_triplet(data: str, prefix: str) -> tuple[int, int] | None:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != prefix:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


@router.message(F.text == "➕ Xizmatlarimni kiritish")
async def show_add_service_menu(message: types.Message, state: FSMContext):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    await state.clear()
    services = await _fetch_services()
    await _show_service_page_message(message, int(barber.id), index=0, services=services)


@router.callback_query(F.data.startswith(f"{BARBER_SERVICE_NAV_CB}:"))
async def barber_service_nav(callback: CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"prev", "next"}:
        await callback.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("❌ Noto'g'ri sahifa.", show_alert=True)
        return

    services = await _fetch_services()
    if not services:
        await callback.answer("⚠️ Xizmatlar mavjud emas.", show_alert=True)
        return

    index = (index + 1) % len(services) if parts[1] == "next" else (index - 1) % len(services)
    await _show_service_page_callback(callback, int(barber.id), index=index, services=services)
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BARBER_SERVICE_ADD_CB}:"))
async def ask_barber_service_price(callback: CallbackQuery, state: FSMContext):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parsed = _parse_triplet(callback.data or "", BARBER_SERVICE_ADD_CB)
    if parsed is None:
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    service_id, page_index = parsed
    existing = await get_barber_service_by_pair(int(barber.id), service_id)
    if existing is not None:
        await callback.answer("Bu xizmat allaqachon ulangan.", show_alert=True)
        await _show_service_page_callback(callback, int(barber.id), index=page_index)
        return

    await state.clear()
    await state.set_state(BarberServiceStates.waiting_for_price)
    await state.update_data(service_id=service_id, page_index=page_index)
    await callback.message.answer(
        f"💵 Ushbu xizmat uchun narxingizni kiriting (so'mda, faqat raqam).{CANCEL_HINT}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BARBER_SERVICE_PRICE_CB}:"))
async def ask_barber_service_update_price(callback: CallbackQuery, state: FSMContext):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parsed = _parse_triplet(callback.data or "", BARBER_SERVICE_PRICE_CB)
    if parsed is None:
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    barber_service_id, page_index = parsed
    barber_service = await get_barber_service_by_id(barber_service_id)
    if barber_service is None or int(barber_service.barber_id) != int(barber.id):
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(BarberServiceStates.waiting_for_update_price)
    await state.update_data(barber_service_id=barber_service_id, page_index=page_index)
    await callback.message.answer(
        f"💵 Yangi narxni kiriting (so'mda, faqat raqam).{CANCEL_HINT}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BARBER_SERVICE_DURATION_CB}:"))
async def ask_barber_service_update_duration(callback: CallbackQuery, state: FSMContext):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parsed = _parse_triplet(callback.data or "", BARBER_SERVICE_DURATION_CB)
    if parsed is None:
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    barber_service_id, page_index = parsed
    barber_service = await get_barber_service_by_id(barber_service_id)
    if barber_service is None or int(barber_service.barber_id) != int(barber.id):
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(BarberServiceStates.waiting_for_update_duration)
    await state.update_data(barber_service_id=barber_service_id, page_index=page_index)
    await callback.message.answer(
        f"🕒 Yangi davomiylikni minutda kiriting. Masalan: 45{CANCEL_HINT}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BARBER_SERVICE_DELETE_CB}:"))
async def delete_barber_service_callback(callback: CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return

    parsed = _parse_triplet(callback.data or "", BARBER_SERVICE_DELETE_CB)
    if parsed is None:
        await callback.answer("❌ Noto'g'ri xizmat.", show_alert=True)
        return

    barber_service_id, page_index = parsed
    barber_service = await get_barber_service_by_id(barber_service_id)
    if barber_service is None or int(barber_service.barber_id) != int(barber.id):
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    deleted = await delete_barber_service(barber_service_id)
    await _show_service_page_callback(callback, int(barber.id), index=page_index)
    await callback.answer(
        "✅ Xizmat o'chirildi." if deleted else "⚠️ Xizmat o'chirilmadi.",
        show_alert=True,
    )


@router.message(
    Command("cancel"),
    StateFilter(
        BarberServiceStates.waiting_for_price,
        BarberServiceStates.waiting_for_duration,
        BarberServiceStates.waiting_for_update_price,
        BarberServiceStates.waiting_for_update_duration,
    ),
)
async def cancel_barber_service_flow(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")


@router.message(BarberServiceStates.waiting_for_price)
async def save_barber_service_price(message: types.Message, state: FSMContext):
    price = normalize_money((message.text or "").strip())
    if price is None:
        await message.answer(f"❌ Narx faqat raqam bo'lishi kerak.{CANCEL_HINT}")
        return

    await state.update_data(price=price)
    await state.set_state(BarberServiceStates.waiting_for_duration)
    await message.answer(f"🕒 Davomiylikni minutda kiriting. Masalan: 45{CANCEL_HINT}")


@router.message(BarberServiceStates.waiting_for_duration)
async def save_barber_service_duration(message: types.Message, state: FSMContext):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await state.clear()
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    duration = normalize_duration_minutes((message.text or "").strip())
    if duration is None:
        await message.answer("❌ Davomiylik 1 dan 1440 gacha minut bo'lishi kerak.")
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    price = data.get("price")
    page_index = int(data.get("page_index", 0))
    if not service_id or price is None:
        await state.clear()
        await message.answer("❌ Jarayon buzildi. Qayta boshlang.")
        return

    created = await create_barber_service(
        int(barber.id),
        int(service_id),
        int(price),
        int(duration),
    )
    await state.clear()
    if created is None:
        await message.answer("❌ Xizmatni ulab bo'lmadi. Ma'lumotlarni tekshiring.")
        return

    await message.answer("✅ Xizmat narx va davomiylik bilan ulandi.")
    await _show_service_page_message(message, int(barber.id), index=page_index)


@router.message(BarberServiceStates.waiting_for_update_price)
async def save_barber_service_update_price(message: types.Message, state: FSMContext):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await state.clear()
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    price = normalize_money((message.text or "").strip())
    if price is None:
        await message.answer(f"❌ Narx faqat raqam bo'lishi kerak.{CANCEL_HINT}")
        return

    data = await state.get_data()
    barber_service_id = data.get("barber_service_id")
    page_index = int(data.get("page_index", 0))
    item = await get_barber_service_by_id(int(barber_service_id or 0))
    if item is None or int(item.barber_id) != int(barber.id):
        await state.clear()
        await message.answer("❌ Xizmat topilmadi.")
        return

    await update_barber_service(int(item.id), {"price": price})
    await state.clear()
    await message.answer("✅ Narx yangilandi.")
    await _show_service_page_message(message, int(barber.id), index=page_index)


@router.message(BarberServiceStates.waiting_for_update_duration)
async def save_barber_service_update_duration(message: types.Message, state: FSMContext):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await state.clear()
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return

    duration = normalize_duration_minutes((message.text or "").strip())
    if duration is None:
        await message.answer("❌ Davomiylik 1 dan 1440 gacha minut bo'lishi kerak.")
        return

    data = await state.get_data()
    barber_service_id = data.get("barber_service_id")
    page_index = int(data.get("page_index", 0))
    item = await get_barber_service_by_id(int(barber_service_id or 0))
    if item is None or int(item.barber_id) != int(barber.id):
        await state.clear()
        await message.answer("❌ Xizmat topilmadi.")
        return

    await update_barber_service(int(item.id), {"duration_minutes": duration})
    await state.clear()
    await message.answer("✅ Davomiylik yangilandi.")
    await _show_service_page_message(message, int(barber.id), index=page_index)
