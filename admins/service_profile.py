# admins/servie_profile.py
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sql.db_services import (
    get_service_by_id,
    list_services_ordered,
    normalize_service_price,
    service_name_exists,
    update_service,
)
from sql.models import Services
from utils.discounts import format_discount_percent
from utils.service_pricing import get_service_price_snapshot
from utils.states import AdminServiceProfileStates
from utils.validators import INT32_MAX
from .admin_buttons import ADMIN_SERVICE_PROFILE_MENU_CB, ADMIN_MAIN_MENU_BACK_CB
from .service_admin_common import (
    ensure_admin_callback,
    ensure_admin_message,
    format_price,
    render_empty_services_text,
    render_service_text,
    show_admin_main_menu,
    show_service_card,
    with_cancel_hint,
)

router = Router()

SERVICE_PROFILE_TITLE = "<b>💈 Xizmat profili</b>"
SERVICE_PROFILE_NAV_PREFIX = "admin_service_profile_nav"
SERVICE_PROFILE_OPEN_PREFIX = "admin_service_profile_open"
SERVICE_PROFILE_EDIT_MENU_PREFIX = "admin_service_profile_edit_menu"
SERVICE_PROFILE_FIELD_PREFIX = "admin_service_profile_field"
SERVICE_PROFILE_PHOTO_PREFIX = "admin_service_profile_photo"
SERVICE_PROFILE_BACK_TO_LIST_PREFIX = "admin_service_profile_back_to_list"
SERVICE_PROFILE_BACK_TO_PROFILE_PREFIX = "admin_service_profile_back_to_profile"

SERVICE_PROFILE_FIELDS = {
    "name": "Xizmat nomi",
    "price": "Xizmat narxi",
    "duration": "Xizmat davomiyligi",
}


def _service_profile_list_keyboard(index: int, service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{SERVICE_PROFILE_NAV_PREFIX}:prev:{index}",
                ),
                InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"{SERVICE_PROFILE_NAV_PREFIX}:next:{index}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛠 Tahrirlash",
                    callback_data=f"{SERVICE_PROFILE_OPEN_PREFIX}:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=ADMIN_MAIN_MENU_BACK_CB,
                )
            ],
        ]
    )


def _service_profile_keyboard(service_id: int, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Rasmni o'zgartirish",
                    callback_data=f"{SERVICE_PROFILE_PHOTO_PREFIX}:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Ma'lumotlarni o'zgartirish",
                    callback_data=f"{SERVICE_PROFILE_EDIT_MENU_PREFIX}:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=f"{SERVICE_PROFILE_BACK_TO_LIST_PREFIX}:{index}",
                )
            ],
        ]
    )


def _service_profile_fields_keyboard(service_id: int, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Xizmat nomi",
                    callback_data=f"{SERVICE_PROFILE_FIELD_PREFIX}:name:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💵 Xizmat narxi",
                    callback_data=f"{SERVICE_PROFILE_FIELD_PREFIX}:price:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Xizmat davomiyligi",
                    callback_data=f"{SERVICE_PROFILE_FIELD_PREFIX}:duration:{service_id}:{index}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=f"{SERVICE_PROFILE_BACK_TO_PROFILE_PREFIX}:{service_id}:{index}",
                )
            ],
        ]
    )


async def _resolve_service_context(
    *,
    service_id: int | None = None,
    index: int = 0,
) -> tuple[list[Services], int, Services | None]:
    services = await list_services_ordered()
    if not services:
        return [], 0, None

    if service_id is not None:
        for current_index, service in enumerate(services):
            if int(service.id) == int(service_id):
                return services, current_index, service

    normalized_index = index % len(services)
    return services, normalized_index, services[normalized_index]


def _service_list_text(service: Services, index: int, total: int, notice: str | None = None) -> str:
    text = render_service_text(
        service,
        title=SERVICE_PROFILE_TITLE,
        index=index,
        total=total,
        extra_lines=("Profilni tahrirlash uchun <b>🛠 Tahrirlash</b> tugmasini bosing.",),
    )
    if notice:
        text = f"{notice}\n\n{text}"
    return text


def _service_profile_text(service: Services, index: int, total: int, notice: str | None = None) -> str:
    photo_status = "mavjud" if getattr(service, "photo", None) else "yo'q"
    text = render_service_text(
        service,
        title=SERVICE_PROFILE_TITLE,
        index=index,
        total=total,
        extra_lines=(
            f"🆔 <b>ID:</b> <code>{service.id}</code>",
            f"🖼 <b>Rasm:</b> {photo_status}",
        ),
    )
    if notice:
        text = f"{notice}\n\n{text}"
    return text


def _build_field_prompt(service: Services, field_key: str) -> str:
    label = SERVICE_PROFILE_FIELDS[field_key]

    if field_key == "name":
        current_value = escape((service.name or "").strip() or "Kiritilmagan")
        hint = "Yangi xizmat nomini yuboring."
        example = "Masalan: <code>Soqol olish</code>"
    elif field_key == "price":
        snapshot = get_service_price_snapshot(service)
        current_value = f"{format_price(snapshot.base_price)} so'm"
        hint = "Yangi narxni faqat raqam ko'rinishida yuboring."
        if snapshot.has_discount:
            percent_text = format_discount_percent(snapshot.discount_percent)
            hint += (
                f"\nAmaldagi chegirma: <b>{percent_text}%</b>"
                f" ({format_price(snapshot.current_price)} so'm)."
                " Narx o'zgarsa, chegirmali narx ham avtomatik qayta hisoblanadi."
            )
        example = f"Maksimal qiymat: <code>{INT32_MAX}</code>"
    else:
        current_value = escape(str(service.duration or "Kiritilmagan"))
        hint = "Yangi davomiylik matnini yuboring."
        example = "Masalan: <code>45 daqiqa</code>"

    return with_cancel_hint(
        f"<b>{escape(label)}</b>\n\n"
        f"Joriy qiymat: <b>{current_value}</b>\n\n"
        f"{hint}\n{example}"
    )


async def _show_service_profile_list(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    index: int = 0,
    notice: str | None = None,
) -> tuple[int, int, int | None]:
    services, normalized_index, service = await _resolve_service_context(index=index)
    if service is None:
        text = render_empty_services_text(
            title=SERVICE_PROFILE_TITLE,
            description="⚠️ Tahrirlash uchun xizmat topilmadi.",
        )
        shown_message_id = await show_service_card(
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            service=None,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Orqaga",
                            callback_data=ADMIN_MAIN_MENU_BACK_CB,
                        )
                    ]
                ]
            ),
        )
        return shown_message_id, 0, None

    shown_message_id = await show_service_card(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        service=service,
        text=_service_list_text(service, normalized_index, len(services), notice),
        reply_markup=_service_profile_list_keyboard(normalized_index, int(service.id)),
    )
    return shown_message_id, normalized_index, int(service.id)


async def _show_service_profile(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    service_id: int,
    index: int = 0,
    notice: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> tuple[int, int, Services | None]:
    services, normalized_index, service = await _resolve_service_context(
        service_id=service_id,
        index=index,
    )
    if service is None:
        text = render_empty_services_text(
            title=SERVICE_PROFILE_TITLE,
            description="⚠️ Tanlangan xizmat topilmadi.",
        )
        shown_message_id = await show_service_card(
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            service=None,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Orqaga",
                            callback_data=ADMIN_MAIN_MENU_BACK_CB,
                        )
                    ]
                ]
            ),
        )
        return shown_message_id, 0, None

    shown_message_id = await show_service_card(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        service=service,
        text=_service_profile_text(
            service,
            normalized_index,
            len(services),
            notice,
        ),
        reply_markup=reply_markup or _service_profile_keyboard(int(service.id), normalized_index),
    )
    return shown_message_id, normalized_index, service


def _parse_nav_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 3:
        return None

    action = parts[1]
    if action not in {"prev", "next"}:
        return None

    try:
        index = int(parts[2])
    except ValueError:
        return None

    return action, index


def _parse_service_and_index(data: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 3:
        return None

    try:
        service_id = int(parts[1])
        index = int(parts[2])
    except ValueError:
        return None

    return service_id, index


def _parse_field_callback(data: str) -> tuple[str, int, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None

    field_key = parts[1]
    if field_key not in SERVICE_PROFILE_FIELDS:
        return None

    try:
        service_id = int(parts[2])
        index = int(parts[3])
    except ValueError:
        return None

    return field_key, service_id, index


@router.callback_query(F.data == ADMIN_SERVICE_PROFILE_MENU_CB)
async def open_service_profile_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    shown_message_id, page_index, service_id = await _show_service_profile_list(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=0,
    )
    await state.clear()
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=service_id,
        service_index=page_index,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_NAV_PREFIX}:"))
async def navigate_service_profile_pages(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_nav_callback(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    action, index = parsed
    services = await list_services_ordered()
    if not services:
        shown_message_id, page_index, service_id = await _show_service_profile_list(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice="⚠️ Xizmatlar topilmadi.",
        )
        await state.clear()
        await state.update_data(
            profile_message_id=shown_message_id,
            service_id=service_id,
            service_index=page_index,
        )
        await callback.answer("Xizmatlar topilmadi.", show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(services)
    else:
        index = (index - 1) % len(services)

    shown_message_id, page_index, service_id = await _show_service_profile_list(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=index,
    )
    await state.clear()
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=service_id,
        service_index=page_index,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_OPEN_PREFIX}:"))
async def open_service_profile(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_service_and_index(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    shown_message_id, page_index, service = await _show_service_profile(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        service_id=service_id,
        index=index,
    )
    if service is None:
        await state.clear()
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=int(service.id),
        service_index=page_index,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_BACK_TO_LIST_PREFIX}:"))
async def back_to_service_profile_list(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    try:
        index = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    shown_message_id, page_index, service_id = await _show_service_profile_list(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=index,
    )
    await state.clear()
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=service_id,
        service_index=page_index,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_EDIT_MENU_PREFIX}:"))
async def open_service_profile_field_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_service_and_index(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    shown_message_id, page_index, service = await _show_service_profile(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        service_id=service_id,
        index=index,
        reply_markup=_service_profile_fields_keyboard(service_id, index),
    )
    if service is None:
        await state.clear()
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminServiceProfileStates.selecting_field)
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=int(service.id),
        service_index=page_index,
    )
    await callback.answer("Tahrirlash uchun maydonni tanlang.")


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_BACK_TO_PROFILE_PREFIX}:"))
async def back_to_service_profile_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_service_and_index(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    shown_message_id, page_index, service = await _show_service_profile(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        service_id=service_id,
        index=index,
    )
    if service is None:
        await state.clear()
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        profile_message_id=shown_message_id,
        service_id=int(service.id),
        service_index=page_index,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_PHOTO_PREFIX}:"))
async def ask_service_profile_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_service_and_index(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    service = await get_service_by_id(service_id)
    if service is None:
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminServiceProfileStates.waiting_for_photo)
    await state.update_data(
        profile_message_id=callback.message.message_id,
        service_id=int(service.id),
        service_index=index,
    )
    await callback.message.answer(
        with_cancel_hint("🖼 Yangi xizmat rasmini yuboring."),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_PROFILE_FIELD_PREFIX}:"))
async def ask_service_profile_field_value(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_field_callback(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    field_key, service_id, index = parsed
    service = await get_service_by_id(service_id)
    if service is None:
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminServiceProfileStates.waiting_for_field_value)
    await state.update_data(
        profile_message_id=callback.message.message_id,
        service_id=int(service.id),
        service_index=index,
        service_field=field_key,
    )
    await callback.message.answer(
        _build_field_prompt(service, field_key),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(
    Command("cancel"),
    StateFilter(
        AdminServiceProfileStates.selecting_field,
        AdminServiceProfileStates.waiting_for_field_value,
        AdminServiceProfileStates.waiting_for_photo,
    ),
)
async def cancel_service_profile_edit(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    data = await state.get_data()
    profile_message_id = data.get("profile_message_id")
    service_id = data.get("service_id")
    service_index = int(data.get("service_index", 0))

    if service_id:
        await _show_service_profile(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=profile_message_id,
            service_id=int(service_id),
            index=service_index,
            notice="❌ Tahrirlash bekor qilindi.",
        )
    else:
        await show_admin_main_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=profile_message_id,
            notice="❌ Tahrirlash bekor qilindi.",
        )

    await state.clear()


@router.message(AdminServiceProfileStates.waiting_for_photo, F.photo)
async def save_service_profile_photo(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    profile_message_id = data.get("profile_message_id")
    service_index = int(data.get("service_index", 0))

    if not service_id:
        await state.clear()
        await message.answer("❌ Jarayon buzildi. Qayta urinib ko'ring.")
        return

    updated_service = await update_service(
        int(service_id),
        {"photo": message.photo[-1].file_id},
    )
    if updated_service is None:
        await state.clear()
        await message.answer("❌ Xizmat topilmadi. Qayta urinib ko'ring.")
        return

    await _show_service_profile(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=profile_message_id,
        service_id=int(updated_service.id),
        index=service_index,
        notice="✅ Xizmat rasmi yangilandi.",
    )
    await state.clear()


@router.message(AdminServiceProfileStates.waiting_for_photo)
async def expected_service_profile_photo(message: types.Message) -> None:
    await message.answer(
        with_cancel_hint("❌ Iltimos, rasm yuboring."),
        parse_mode="HTML",
    )


@router.message(AdminServiceProfileStates.waiting_for_field_value)
async def save_service_profile_field(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer(
            with_cancel_hint("❌ Iltimos, yangi qiymatni yuboring."),
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    profile_message_id = data.get("profile_message_id")
    service_index = int(data.get("service_index", 0))
    field_key = data.get("service_field")

    if not service_id or field_key not in SERVICE_PROFILE_FIELDS:
        await state.clear()
        await message.answer("❌ Jarayon buzildi. Qayta urinib ko'ring.")
        return

    updates: dict[str, object] = {}
    error_text: str | None = None

    if field_key == "name":
        if await service_name_exists(raw_text, exclude_service_id=int(service_id)):
            error_text = "Bunday xizmat nomi allaqachon mavjud."
        else:
            updates["name"] = raw_text
    elif field_key == "price":
        normalized_price = normalize_service_price(raw_text)
        if normalized_price is None:
            error_text = (
                "Narx faqat raqam bo'lishi kerak va ruxsat etilgan "
                f"maksimal qiymat {INT32_MAX} dan oshmasligi kerak."
            )
        else:
            updates["price"] = normalized_price
    elif field_key == "duration":
        updates["duration"] = raw_text
    else:
        error_text = "Maydon topilmadi."

    if error_text:
        await message.answer(
            with_cancel_hint(f"❌ {error_text}"),
            parse_mode="HTML",
        )
        return

    updated_service = await update_service(int(service_id), updates)
    if updated_service is None:
        await state.clear()
        await message.answer("❌ Xizmatni yangilab bo'lmadi. Qayta urinib ko'ring.")
        return

    field_label = SERVICE_PROFILE_FIELDS[field_key]
    await _show_service_profile(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=profile_message_id,
        service_id=int(updated_service.id),
        index=service_index,
        notice=f"✅ {escape(field_label)} yangilandi.",
    )
    await state.clear()
