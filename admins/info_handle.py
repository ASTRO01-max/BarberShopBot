from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sql.db_info import update_info_expanded_fields, update_info_fields
from sql.db_info_profile import (
    ALLOWED_INFO_HIDDEN_FIELDS,
    get_info_hidden_fields,
    set_info_field_visibility,
)
from utils.info_profile import (
    build_info_text,
    build_social_link_rows,
    get_field_display_value,
    get_info_profile_snapshot,
    normalize_instagram,
    normalize_telegram,
    normalize_website,
)
from .admin_buttons import ADMIN_MAIN_MENU_BACK_CB
from .service_admin_common import ensure_admin_callback, ensure_admin_message

router = Router()

INFO_PROFILE_MESSAGE_ID_KEY = "info_profile_message_id"
INFO_PROFILE_FIELD_KEY = "info_profile_field"
INFO_PREVIEW_CB = "admin_info_preview"
INFO_HIDE_MENU_CB = "admin_info_hide_menu"
INFO_EDIT_MENU_CB = "admin_info_edit_menu"
INFO_MAP_EDIT_CB = "admin_info_map_edit"
INFO_HIDE_FIELD_PREFIX = "admin_info_hide_field"
INFO_EDIT_FIELD_PREFIX = "admin_info_edit_field"

CLEAR_COMMANDS = {"yo'q", "yoq", "-", "none", "null"}

EDITABLE_INFO_FIELDS = {
    "telegram": {
        "label": "Telegram",
        "emoji": "✈️",
        "table": "info",
        "example": "@barbershop",
        "max_length": 150,
    },
    "instagram": {
        "label": "Instagram",
        "emoji": "📷",
        "table": "info",
        "example": "@barbershop_uz",
        "max_length": 150,
    },
    "website": {
        "label": "Website",
        "emoji": "🌐",
        "table": "info",
        "example": "barbershop.uz",
        "max_length": 200,
    },
    "phone_number": {
        "label": "Telefon 1",
        "emoji": "📞",
        "table": "info_expanded",
        "example": "+998901234567",
        "max_length": 30,
    },
    "phone_number2": {
        "label": "Telefon 2",
        "emoji": "📞",
        "table": "info_expanded",
        "example": "+998901234568",
        "max_length": 30,
    },
    "region": {
        "label": "Hudud",
        "emoji": "🏙",
        "table": "info",
        "example": "Toshkent",
        "max_length": 120,
    },
    "district": {
        "label": "Tuman",
        "emoji": "🏘",
        "table": "info",
        "example": "Chilonzor",
        "max_length": 120,
    },
    "street": {
        "label": "Ko'cha",
        "emoji": "🛣",
        "table": "info",
        "example": "Bunyodkor ko'chasi, 12-uy",
        "max_length": 200,
    },
    "address_text": {
        "label": "Manzil",
        "emoji": "📍",
        "table": "info",
        "example": "Toshkent, Chilonzor tumani, Bunyodkor ko'chasi 12-uy",
        "max_length": 400,
    },
    "work_time_text": {
        "label": "Ish vaqti",
        "emoji": "🕒",
        "table": "info",
        "example": "09:00-21:00",
        "max_length": 200,
    },
}

HIDEABLE_INFO_FIELDS = {
    key: value for key, value in EDITABLE_INFO_FIELDS.items() if key in ALLOWED_INFO_HIDDEN_FIELDS
}


class InfoAdminState(StatesGroup):
    waiting_for_field_value = State()
    waiting_for_location = State()


def _normalize_phone(raw_phone: str) -> str | None:
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if len(digits) == 9:
        return f"+998{digits}"
    return None


def _with_cancel_hint(text: str) -> str:
    return f"{text}\n\nBekor qilish: /cancel"


def _build_admin_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🙈 Ma'lumotlarni yashirish", callback_data=INFO_HIDE_MENU_CB)],
            [InlineKeyboardButton(text="✏️ Ma'lumotlarni o'zgartirish", callback_data=INFO_EDIT_MENU_CB)],
            [InlineKeyboardButton(text="🗺 Xaritani o'zgartirish", callback_data=INFO_MAP_EDIT_CB)],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=ADMIN_MAIN_MENU_BACK_CB)],
        ]
    )


def _build_info_preview_markup(include_links: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    rows = list(include_links)
    rows.extend(_build_admin_preview_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_hide_menu_keyboard(hidden_fields: set[str]) -> InlineKeyboardMarkup:
    def label(field_key: str) -> str:
        config = HIDEABLE_INFO_FIELDS[field_key]
        if field_key in hidden_fields:
            return f"🙈 {config['label']}"
        return f"{config['emoji']} {config['label']}"

    rows = [
        [
            InlineKeyboardButton(
                text=label("telegram"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'telegram'}",
            ),
            InlineKeyboardButton(
                text=label("instagram"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'instagram'}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=label("website"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'website'}",
            ),
            InlineKeyboardButton(
                text=label("phone_number"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'phone_number'}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=label("phone_number2"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'phone_number2'}",
            ),
            InlineKeyboardButton(
                text=label("work_time_text"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'work_time_text'}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=label("region"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'region'}",
            ),
            InlineKeyboardButton(
                text=label("district"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'district'}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=label("street"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'street'}",
            ),
            InlineKeyboardButton(
                text=label("address_text"),
                callback_data=f"{INFO_HIDE_FIELD_PREFIX}:{'address_text'}",
            ),
        ],
        [InlineKeyboardButton(text="🔙 Previewga qaytish", callback_data=INFO_PREVIEW_CB)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_edit_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✈️ Telegram",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:telegram",
            ),
            InlineKeyboardButton(
                text="📷 Instagram",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:instagram",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🌐 Website",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:website",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📞 Telefon 1",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:phone_number",
            ),
            InlineKeyboardButton(
                text="📞 Telefon 2",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:phone_number2",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🏙 Hudud",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:region",
            ),
            InlineKeyboardButton(
                text="🏘 Tuman",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:district",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🛣 Ko'cha",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:street",
            ),
            InlineKeyboardButton(
                text="📍 Manzil",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:address_text",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🕒 Ish vaqti",
                callback_data=f"{INFO_EDIT_FIELD_PREFIX}:work_time_text",
            ),
        ],
        [InlineKeyboardButton(text="🔙 Previewga qaytish", callback_data=INFO_PREVIEW_CB)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_or_send_text(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> int:
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return message_id
        except Exception:
            pass

    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    return sent.message_id


async def _show_info_preview(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    snapshot = await get_info_profile_snapshot()
    text = build_info_text(snapshot)
    if notice:
        text = f"{notice}\n\n{text}"
    markup = _build_info_preview_markup(
        build_social_link_rows(snapshot, include_website=True)
    )
    return await _edit_or_send_text(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=markup,
    )


async def _show_hide_menu(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    hidden_fields = set(await get_info_hidden_fields())
    text = (
        "<b>Ma'lumotlarni yashirish</b>\n\n"
        "Tugmani bossangiz maydon yashiriladi, qayta bossangiz yana ko'rinadi."
    )
    if notice:
        text = f"{notice}\n\n{text}"
    return await _edit_or_send_text(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=_build_hide_menu_keyboard(hidden_fields),
    )


async def _show_edit_menu(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    text = "<b>Ma'lumotlarni o'zgartirish</b>\n\nQaysi maydonni tahrirlash kerakligini tanlang."
    if notice:
        text = f"{notice}\n\n{text}"
    return await _edit_or_send_text(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=_build_edit_menu_keyboard(),
    )


async def _show_map_prompt(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
) -> int:
    return await _edit_or_send_text(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=(
            "<b>Xaritani o'zgartirish</b>\n\n"
            "Telegram orqali lokatsiya yoki venue yuboring. Lokatsiya kelgach latitude va longitude yangilanadi."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Previewga qaytish", callback_data=INFO_PREVIEW_CB)]
            ]
        ),
    )


def _build_field_prompt(field_key: str, current_value: str) -> str:
    config = EDITABLE_INFO_FIELDS[field_key]
    lines = [
        f"{config['emoji']} <b>{escape(config['label'])}</b>",
        "",
        f"Joriy qiymat: <b>{escape(current_value)}</b>",
        "",
        "Yangi qiymatni yuboring.",
    ]

    example = config.get("example")
    if example:
        lines.append(f"Namuna: <code>{escape(example)}</code>")

    lines.append('"yo\'q" deb yuborsangiz qiymat o\'chiriladi.')
    return _with_cancel_hint("\n".join(lines))


def _normalize_field_value(field_key: str, raw_text: str) -> tuple[object, str | None]:
    normalized_token = raw_text.strip().lower()
    config = EDITABLE_INFO_FIELDS[field_key]

    if normalized_token in CLEAR_COMMANDS:
        return None, None

    max_length = int(config["max_length"])
    if len(raw_text) > max_length:
        return None, f"{config['label']} {max_length} belgidan oshmasligi kerak."

    if field_key == "telegram":
        if normalize_telegram(raw_text) is None:
            return None, "Telegram username yoki link noto'g'ri."
        return raw_text, None

    if field_key == "instagram":
        if normalize_instagram(raw_text) is None:
            return None, "Instagram username yoki link noto'g'ri."
        return raw_text, None

    if field_key == "website":
        if normalize_website(raw_text) is None:
            return None, "Website manzili noto'g'ri."
        return raw_text, None

    if field_key in {"phone_number", "phone_number2"}:
        phone = _normalize_phone(raw_text)
        if phone is None:
            return None, "Telefon formati noto'g'ri. Masalan: +998901234567"
        return phone, None

    return raw_text, None


async def open_info_panel(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        return

    await state.clear()
    shown_message_id = await _show_info_preview(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=None,
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})


@router.callback_query(F.data == INFO_PREVIEW_CB)
async def back_to_info_preview(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    shown_message_id = await _show_info_preview(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await callback.answer()


@router.callback_query(F.data == INFO_HIDE_MENU_CB)
async def open_hide_info_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    shown_message_id = await _show_hide_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await callback.answer()


@router.callback_query(F.data.startswith(f"{INFO_HIDE_FIELD_PREFIX}:"))
async def toggle_info_field_visibility(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    field_key = (callback.data or "").split(":", 1)[1]
    if field_key not in HIDEABLE_INFO_FIELDS:
        await callback.answer("Maydon topilmadi.", show_alert=True)
        return

    current_hidden = set(await get_info_hidden_fields())
    target_hidden = field_key not in current_hidden
    await set_info_field_visibility(field_key, target_hidden)

    shown_message_id = await _show_hide_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        notice=(
            f"<b>{escape(HIDEABLE_INFO_FIELDS[field_key]['label'])} yashirildi.</b>"
            if target_hidden
            else f"<b>{escape(HIDEABLE_INFO_FIELDS[field_key]['label'])} yana ko'rsatildi.</b>"
        ),
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await callback.answer()


@router.callback_query(F.data == INFO_EDIT_MENU_CB)
async def open_edit_info_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    shown_message_id = await _show_edit_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await callback.answer()


@router.callback_query(F.data.startswith(f"{INFO_EDIT_FIELD_PREFIX}:"))
async def ask_info_field_value(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    field_key = (callback.data or "").split(":", 1)[1]
    if field_key not in EDITABLE_INFO_FIELDS:
        await callback.answer("Maydon topilmadi.", show_alert=True)
        return

    snapshot = await get_info_profile_snapshot()
    await state.clear()
    await state.set_state(InfoAdminState.waiting_for_field_value)
    await state.update_data(
        **{
            INFO_PROFILE_MESSAGE_ID_KEY: callback.message.message_id,
            INFO_PROFILE_FIELD_KEY: field_key,
        }
    )
    await callback.message.answer(
        _build_field_prompt(field_key, get_field_display_value(snapshot, field_key)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == INFO_MAP_EDIT_CB)
async def ask_info_location(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    await state.set_state(InfoAdminState.waiting_for_location)
    shown_message_id = await _show_map_prompt(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await callback.message.answer(
        _with_cancel_hint("📍 Yangi lokatsiyani Telegram location yoki venue ko'rinishida yuboring."),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(
    Command("cancel"),
    StateFilter(
        InfoAdminState.waiting_for_field_value,
        InfoAdminState.waiting_for_location,
    ),
)
async def cancel_info_edit(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    data = await state.get_data()
    preview_message_id = data.get(INFO_PROFILE_MESSAGE_ID_KEY)
    await state.clear()
    shown_message_id = await _show_info_preview(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=preview_message_id,
        notice="<b>Amal bekor qilindi.</b>",
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await message.answer("Amal bekor qilindi.")


@router.message(InfoAdminState.waiting_for_field_value)
async def save_info_field(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer(
            _with_cancel_hint("❌ Iltimos, matn yuboring."),
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    field_key = data.get(INFO_PROFILE_FIELD_KEY)
    preview_message_id = data.get(INFO_PROFILE_MESSAGE_ID_KEY)
    if field_key not in EDITABLE_INFO_FIELDS:
        await state.clear()
        await message.answer("❌ Jarayon buzildi. Qayta urinib ko'ring.")
        return

    normalized_value, error_text = _normalize_field_value(field_key, raw_text)
    if error_text:
        await message.answer(
            _with_cancel_hint(f"❌ {error_text}"),
            parse_mode="HTML",
        )
        return

    config = EDITABLE_INFO_FIELDS[field_key]
    if config["table"] == "info":
        await update_info_fields({field_key: normalized_value})
    else:
        await update_info_expanded_fields({field_key: normalized_value})

    if field_key in HIDEABLE_INFO_FIELDS:
        await set_info_field_visibility(field_key, False)

    await state.clear()
    shown_message_id = await _show_info_preview(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=preview_message_id,
        notice=f"<b>{escape(config['label'])} yangilandi.</b>",
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await message.answer(f"{config['label']} yangilandi.")


@router.message(InfoAdminState.waiting_for_location)
async def save_info_location(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    location = message.location
    venue = message.venue
    if location is None and venue is not None:
        location = venue.location

    if location is None:
        await message.answer(
            _with_cancel_hint("❌ Lokatsiya yoki venue yuboring."),
            parse_mode="HTML",
        )
        return

    updates = {
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
    }
    if venue is not None and str(getattr(venue, "address", "") or "").strip():
        updates["address_text"] = venue.address.strip()

    await update_info_fields(updates)
    preview_message_id = (await state.get_data()).get(INFO_PROFILE_MESSAGE_ID_KEY)
    await state.clear()
    shown_message_id = await _show_info_preview(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=preview_message_id,
        notice="<b>Xarita ma'lumotlari yangilandi.</b>",
    )
    await state.update_data(**{INFO_PROFILE_MESSAGE_ID_KEY: shown_message_id})
    await message.answer("Xarita yangilandi.")
