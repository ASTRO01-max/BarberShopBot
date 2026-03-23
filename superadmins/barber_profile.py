from html import escape

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import delete, update

from handlers.barber_cards import get_barber_card_content
from sql.db import async_session
from sql.db_barber_profile import (
    ALLOWED_HIDDEN_FIELDS,
    get_barber_hidden_fields,
    set_barber_field_visibility,
)
from sql.models import BarberPhotos, Barbers
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import (
    get_barber_profile_fields_keyboard,
    get_barber_profile_keyboard,
)

router = Router()

PROFILE_TITLE = "👤 <b>Profil</b>"
HIDE_COMMANDS = {"yashir"}
SHOW_COMMANDS = {"ko'rsat", "korsat"}
CLEAR_COMMANDS = {"yo'q", "yoq"}
EDITABLE_FIELDS = {
    "name": {"label": "Ism familiya", "emoji": "👤", "placeholder": "Aliyev Valijon"},
    "experience": {"label": "Tajriba", "emoji": "💼"},
    "work_days": {"label": "Ish kunlari", "emoji": "📅"},
    "work_time": {"label": "Ish vaqti", "emoji": "⏰", "format": "09:00-18:00"},
    "breakdown": {"label": "Tanaffus", "emoji": "⏸️", "format": "13:00-14:00"},
    "phone": {"label": "Aloqa", "emoji": "📞", "placeholder": "+998901234567"},
}
NON_CLEARABLE_FIELDS = {"name", "work_time"}


class BarberProfileState(StatesGroup):
    waiting_for_new_photo = State()
    waiting_for_field_value = State()


def _normalize_token(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace("’", "'")
        .replace("`", "'")
        .replace("ʻ", "'")
        .replace("‘", "'")
    )


def _parse_time_range(text: str) -> tuple[str, str] | None:
    if "-" not in text:
        return None

    parts = [part.strip() for part in text.split("-")]
    if len(parts) != 2:
        return None

    try:
        sh, sm = map(int, parts[0].split(":"))
        eh, em = map(int, parts[1].split(":"))
    except Exception:
        return None

    if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
        return None
    if (sh * 60 + sm) >= (eh * 60 + em):
        return None

    return parts[0], parts[1]


def _normalize_phone(raw_phone: str) -> str | None:
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if len(digits) == 9:
        return f"+998{digits}"
    return None


def _field_display_value(barber: Barbers, field_key: str) -> str:
    if field_key == "name":
        full_name = " ".join(
            [part for part in [barber.barber_first_name, barber.barber_last_name] if part]
        ).strip()
        return full_name or "Kiritilmagan"

    field_map = {
        "experience": barber.experience,
        "work_days": barber.work_days,
        "work_time": barber.work_time,
        "breakdown": barber.breakdown,
        "phone": barber.phone,
    }
    value = field_map.get(field_key)
    return str(value) if value else "Kiritilmagan"


def _build_field_prompt(barber: Barbers, field_key: str, hidden_fields: set[str]) -> str:
    config = EDITABLE_FIELDS[field_key]
    label = config["label"]
    emoji = config["emoji"]
    current_value = escape(_field_display_value(barber, field_key))
    lines = [
        f"{emoji} <b>{label}</b>",
        "",
        f"Joriy qiymat: <b>{current_value}</b>",
    ]

    if field_key in ALLOWED_HIDDEN_FIELDS:
        visibility = "yashirilgan" if field_key in hidden_fields else "ko'rinadi"
        lines.append(f"Holati: <b>{visibility}</b>")

    lines.extend(["", "Yangi qiymatni yuboring."])

    if placeholder := config.get("placeholder"):
        lines.append(f"Namuna: <code>{placeholder}</code>")

    if field_format := config.get("format"):
        lines.append(f"Format: <code>{field_format}</code>")

    if field_key in ALLOWED_HIDDEN_FIELDS:
        lines.append('"yashir" deb yuborsangiz, bu maydon profil kartasida ko\'rinmaydi.')
        lines.append('"ko\'rsat" deb yuborsangiz, maydon yana ko\'rinadi.')

    if field_key not in NON_CLEARABLE_FIELDS:
        lines.append('"yo\'q" deb yuborsangiz, qiymat o\'chiriladi.')

    if field_key == "breakdown":
        lines.append("Agar tanaffus bo'lmasa, <code>yo'q</code> yuboring.")

    lines.extend(["", "Bekor qilish: /cancel"])
    return "\n".join(lines)


async def _show_profile_exact(
    *,
    bot,
    chat_id: int,
    barber: Barbers,
    message_id: int | None,
) -> int:
    caption, photo = await get_barber_card_content(
        barber,
        title=PROFILE_TITLE,
        include_status=True,
    )
    keyboard = get_barber_profile_keyboard()

    if message_id:
        if photo:
            try:
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=types.InputMediaPhoto(
                        media=photo,
                        caption=caption,
                        parse_mode="HTML",
                    ),
                    reply_markup=keyboard,
                )
                return message_id
            except Exception:
                pass
        else:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return message_id
            except Exception:
                pass

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    if photo:
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    return sent.message_id


async def _get_barber_or_alert(callback: types.CallbackQuery):
    barber = await get_barber_by_tg_id(callback.from_user.id)
    if not barber:
        await callback.answer("❌ Bu bo'lim faqat barberlar uchun.", show_alert=True)
        return None
    return barber


async def _get_barber_or_message(message: types.Message):
    barber = await get_barber_by_tg_id(message.from_user.id)
    if not barber:
        await message.answer("❌ Bu bo'lim faqat barberlar uchun.")
        return None
    return barber


async def _refresh_barber(barber_id: int):
    async with async_session() as session:
        return await session.get(Barbers, barber_id)


async def _handle_field_update(barber: Barbers, field_key: str, raw_text: str) -> tuple[Barbers | None, str | None]:
    normalized = _normalize_token(raw_text)

    if normalized in CLEAR_COMMANDS and field_key in NON_CLEARABLE_FIELDS:
        return None, "Bu maydonni bo'sh qoldirib bo'lmaydi."

    values: dict[str, str | None] = {}

    if field_key == "name":
        parts = [part for part in raw_text.split() if part]
        if len(parts) < 2:
            return None, "Iltimos, ism va familiyani birga kiriting."
        values["barber_first_name"] = parts[0]
        values["barber_last_name"] = " ".join(parts[1:])
    elif field_key == "experience":
        values["experience"] = None if normalized in CLEAR_COMMANDS else raw_text
        if values["experience"] is not None and len(raw_text) < 2:
            return None, "Tajriba juda qisqa. Qayta kiriting."
    elif field_key == "work_days":
        values["work_days"] = None if normalized in CLEAR_COMMANDS else raw_text
        if values["work_days"] is not None and len(raw_text) < 3:
            return None, "Ish kunlari juda qisqa. Qayta kiriting."
    elif field_key == "work_time":
        parsed = _parse_time_range(raw_text)
        if not parsed:
            return None, "Ish vaqti formati noto'g'ri. Masalan: 09:00-18:00"
        values["work_time"] = f"{parsed[0]}-{parsed[1]}"
    elif field_key == "breakdown":
        if normalized in CLEAR_COMMANDS:
            values["breakdown"] = None
        else:
            parsed = _parse_time_range(raw_text)
            if not parsed:
                return None, "Tanaffus vaqti noto'g'ri. Masalan: 13:00-14:00"
            values["breakdown"] = f"{parsed[0]}-{parsed[1]}"
    elif field_key == "phone":
        if normalized in CLEAR_COMMANDS:
            values["phone"] = None
        else:
            phone = _normalize_phone(raw_text)
            if not phone:
                return None, "Telefon formati noto'g'ri. Masalan: +998901234567"
            values["phone"] = phone
    else:
        return None, "Maydon topilmadi."

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(**values)
        )
        await session.commit()
        refreshed = await session.get(Barbers, barber.id)

    if field_key in ALLOWED_HIDDEN_FIELDS:
        await set_barber_field_visibility(barber.id, field_key, False)

    return refreshed, None


@router.callback_query(F.data == "barber_profile_open")
async def open_barber_profile(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    await _show_profile_exact(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        barber=barber,
        message_id=callback.message.message_id,
    )
    await callback.answer()


@router.callback_query(F.data == "barber_profile_edit_photo")
async def ask_new_profile_photo(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    await state.set_state(BarberProfileState.waiting_for_new_photo)
    await state.update_data(profile_message_id=callback.message.message_id)
    await callback.message.answer(
        "🖼 Yangi rasm yuboring.\n\nBekor qilish: /cancel"
    )
    await callback.answer()


@router.callback_query(F.data == "barber_profile_edit_info")
async def open_profile_edit_menu(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    await state.clear()
    hidden_fields = set(await get_barber_hidden_fields(barber.id))

    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_barber_profile_fields_keyboard(hidden_fields)
        )
    except Exception:
        pass

    await callback.answer("Maydonni tanlang")


@router.callback_query(F.data.startswith("barber_profile_field_"))
async def choose_profile_field(callback: types.CallbackQuery, state: FSMContext):
    barber = await _get_barber_or_alert(callback)
    if not barber:
        return

    field_key = callback.data.removeprefix("barber_profile_field_")
    if field_key not in EDITABLE_FIELDS:
        await callback.answer("Maydon topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.set_state(BarberProfileState.waiting_for_field_value)
    await state.update_data(
        profile_message_id=callback.message.message_id,
        profile_field=field_key,
    )

    hidden_fields = set(await get_barber_hidden_fields(barber.id))
    await callback.message.answer(
        _build_field_prompt(barber, field_key, hidden_fields),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text == "/cancel", StateFilter(
    BarberProfileState.waiting_for_new_photo,
    BarberProfileState.waiting_for_field_value,
))
async def cancel_profile_edit(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    data = await state.get_data()
    profile_message_id = data.get("profile_message_id")

    await _show_profile_exact(
        bot=message.bot,
        chat_id=message.chat.id,
        barber=barber,
        message_id=profile_message_id,
    )
    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass


@router.message(BarberProfileState.waiting_for_new_photo, F.photo)
async def save_new_profile_photo(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    profile_message_id = data.get("profile_message_id")

    async with async_session() as session:
        await session.execute(delete(BarberPhotos).where(BarberPhotos.barber_id == barber.id))
        session.add(BarberPhotos(barber_id=barber.id, photo=photo_file_id))
        await session.commit()

    refreshed = await _refresh_barber(barber.id)
    await _show_profile_exact(
        bot=message.bot,
        chat_id=message.chat.id,
        barber=refreshed or barber,
        message_id=profile_message_id,
    )
    await state.clear()
    await message.answer("✅ Profil rasmi yangilandi.")


@router.message(BarberProfileState.waiting_for_new_photo)
async def expected_profile_photo(message: types.Message):
    await message.answer("❌ Iltimos, rasm yuboring yoki /cancel yuboring.")


@router.message(BarberProfileState.waiting_for_field_value)
async def save_profile_field(message: types.Message, state: FSMContext):
    barber = await _get_barber_or_message(message)
    if not barber:
        await state.clear()
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer("❌ Iltimos, matn yuboring yoki /cancel yuboring.")
        return

    data = await state.get_data()
    field_key = data.get("profile_field")
    profile_message_id = data.get("profile_message_id")

    if field_key not in EDITABLE_FIELDS:
        await state.clear()
        await message.answer("❌ Jarayon buzildi. Qayta urinib ko'ring.")
        return

    normalized = _normalize_token(raw_text)
    label = EDITABLE_FIELDS[field_key]["label"]

    if normalized in HIDE_COMMANDS:
        if field_key not in ALLOWED_HIDDEN_FIELDS:
            await message.answer("Bu maydon doim ko'rinadi. Yangi qiymat kiriting yoki /cancel yuboring.")
            return
        await set_barber_field_visibility(barber.id, field_key, True)
        refreshed = await _refresh_barber(barber.id)
        await _show_profile_exact(
            bot=message.bot,
            chat_id=message.chat.id,
            barber=refreshed or barber,
            message_id=profile_message_id,
        )
        await state.clear()
        await message.answer(f"🙈 {label} profil kartasidan yashirildi.")
        return

    if normalized in SHOW_COMMANDS:
        if field_key not in ALLOWED_HIDDEN_FIELDS:
            await message.answer("Bu maydon allaqachon doim ko'rinadi.")
            return
        await set_barber_field_visibility(barber.id, field_key, False)
        refreshed = await _refresh_barber(barber.id)
        await _show_profile_exact(
            bot=message.bot,
            chat_id=message.chat.id,
            barber=refreshed or barber,
            message_id=profile_message_id,
        )
        await state.clear()
        await message.answer(f"👁 {label} yana ko'rinadigan qilindi.")
        return

    refreshed, error_text = await _handle_field_update(barber, field_key, raw_text)
    if error_text:
        await message.answer(f"❌ {error_text}")
        return

    await _show_profile_exact(
        bot=message.bot,
        chat_id=message.chat.id,
        barber=refreshed or barber,
        message_id=profile_message_id,
    )
    await state.clear()
    await message.answer(f"✅ {label} yangilandi.")
