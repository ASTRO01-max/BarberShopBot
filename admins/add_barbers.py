# admins/add_barbers.py
from datetime import date
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, select

from sql.db import async_session
from sql.models import BarberExpanded, BarberPhotos, Barbers, OrdinaryUser
from utils.states import AdminStates
from .admin_buttons import (
    BARBER_ADD_CB,
    BARBER_ADD_TEXT,
    BARBER_DEL_CB,
    BARBER_DEL_TEXT,
    BARBER_MENU_TEXT,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
BARBER_NAV_PREFIX = "admbar"
BARBER_DELETE_PICK_PREFIX = "barber:delete:pick"
BARBER_DELETE_CONFIRM_PREFIX = "barber:delete:confirm"
BARBER_DELETE_CANCEL_PREFIX = "barber:delete:cancel"
BARBER_PAGE_SIZE = 1


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


def _parse_time_range(text: str):
    if "-" not in text:
        return None
    parts = [p.strip() for p in text.split("-")]
    if len(parts) != 2:
        return None
    start, end = parts
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
            return None
        if (sh * 60 + sm) >= (eh * 60 + em):
            return None
    except Exception:
        return None
    return start, end


def _format_time_range(value, empty: str = "yo'q") -> str:
    if not value:
        return empty

    if isinstance(value, str):
        return value.strip() if value.strip() else empty

    if isinstance(value, dict):
        start = value.get("from")
        end = value.get("to")
        if start and end:
            return f"{start}-{end}"

    return empty


def _barber_display_name(barber: Barbers) -> str:
    return (
        " ".join(
            part.strip()
            for part in [barber.barber_first_name or "", barber.barber_last_name or ""]
            if part and part.strip()
        ).strip()
        or "Noma'lum barber"
    )


def _barber_nav_keyboard(index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{BARBER_NAV_PREFIX}_prev_{index}",
                ),
                InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"{BARBER_NAV_PREFIX}_next_{index}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BARBER_ADD_TEXT,
                    callback_data=BARBER_ADD_CB,
                ),
                InlineKeyboardButton(
                    text=BARBER_DEL_TEXT,
                    callback_data=f"{BARBER_DELETE_PICK_PREFIX}:{index}",
                ),
            ],
        ]
    )


def _barber_delete_confirmation_keyboard(
    barber_id: int,
    index: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"{BARBER_DELETE_CONFIRM_PREFIX}:{barber_id}:{index}",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=f"{BARBER_DELETE_CANCEL_PREFIX}:{index}",
                ),
            ]
        ]
    )


async def _count_barbers() -> int:
    async with async_session() as session:
        total = await session.scalar(select(func.count(Barbers.id)))
    return int(total or 0)


async def _fetch_barber_page(index: int, total: int | None = None):
    if total is None:
        total = await _count_barbers()
    if total <= 0:
        return 0, 0, None

    normalized_index = index % total
    offset = normalized_index * BARBER_PAGE_SIZE

    async with async_session() as session:
        barber = (
            await session.execute(
                select(Barbers)
                .order_by(Barbers.id.asc())
                .limit(BARBER_PAGE_SIZE)
                .offset(offset)
            )
        ).scalar_one_or_none()

    return total, normalized_index, barber


def _render_barber_summary(barber: Barbers) -> str:
    full_name = escape(_barber_display_name(barber))
    experience = escape(barber.experience or "-")
    work_days = escape(barber.work_days or "-")
    work_time = escape(_format_time_range(barber.work_time, "-"))
    breakdown = escape(_format_time_range(barber.breakdown, "yo'q"))
    phone = escape(barber.phone or "-")

    return (
        f"👨‍💼 <b>{full_name}</b>\n"
        f"💼 Tajriba: {experience}\n"
        f"📅 Ish kunlari: {work_days}\n"
        f"🕒 Ish vaqti: {work_time}\n"
        f"⏸️ Tanaffus: {breakdown}\n"
        f"📞 Aloqa: <code>{phone}</code>"
    )


def _render_barber_page_text(total: int, index: int, barber: Barbers | None) -> str:
    if total <= 0 or barber is None:
        return (
            "💈 <b>Barberlar ro'yxati</b>\n\n"
            "⚠️ <i>Hozircha barberlar mavjud emas.</i>\n\n"
            "📌 <i>(0 / 0)</i>"
        )

    return (
        "💈 <b>Barberlar ro'yxati</b>\n\n"
        f"{_render_barber_summary(barber)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


def _render_barber_delete_confirmation_text(total: int, index: int, barber: Barbers) -> str:
    return (
        "🗑 <b>Barberni o'chirish</b>\n\n"
        "Quyidagi barberni o'chirishni tasdiqlaysizmi?\n\n"
        f"{_render_barber_summary(barber)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _edit_or_send_barber_message(
    callback: types.CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if not callback.message:
        return

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def _show_barber_page_message(
    message: types.Message,
    index: int = 0,
    total: int | None = None,
) -> None:
    total, index, barber = await _fetch_barber_page(index, total=total)
    await message.answer(
        _render_barber_page_text(total, index, barber),
        parse_mode="HTML",
        reply_markup=_barber_nav_keyboard(index),
    )


async def _show_barber_page_callback(
    callback: types.CallbackQuery,
    index: int = 0,
    total: int | None = None,
    notice: str | None = None,
) -> None:
    total, index, barber = await _fetch_barber_page(index, total=total)
    text = _render_barber_page_text(total, index, barber)
    if notice:
        text = f"{notice}\n\n{text}"

    await _edit_or_send_barber_message(
        callback,
        text=text,
        reply_markup=_barber_nav_keyboard(index),
    )


async def _start_add_barber(message: types.Message | None, state: FSMContext) -> None:
    if message is None:
        return

    await state.clear()
    await state.set_state(AdminStates.adding_barber_fullname)
    await message.answer(
        with_cancel_hint(
            "<b>Yangi barber qo'shish</b>\n\n"
            "Iltimos barberning <b>to'liq ismini</b> kiriting.\n"
            "Namuna: <i>Abdulloh Karimov</i>"
        ),
        parse_mode="HTML",
    )


@router.message(
    StateFilter(
        AdminStates.adding_barber_fullname,
        AdminStates.adding_barber_phone,
        AdminStates.adding_barber_experience,
        AdminStates.adding_barber_work_days,
        AdminStates.adding_barber_work_time,
        AdminStates.adding_barber_breakdown,
        AdminStates.adding_photo_choice,
        AdminStates.adding_barber_photo,
    ),
    Command("cancel"),
)
async def cancel_add_barber(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")
    await _show_barber_page_message(message, index=0)


@router.callback_query(F.data.startswith(f"{BARBER_NAV_PREFIX}_"))
async def barber_pagination_nav(callback: types.CallbackQuery):
    parts = (callback.data or "").split("_")
    if len(parts) != 3:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    action = parts[1]
    if action not in {"prev", "next"}:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Noto'g'ri sahifa", show_alert=True)
        return

    total = await _count_barbers()
    if total > 0:
        if action == "next":
            index = (index + 1) % total
        else:
            index = (index - 1) % total
    else:
        index = 0

    await _show_barber_page_callback(callback, index=index, total=total)
    await callback.answer()


@router.message(F.text == BARBER_MENU_TEXT)
async def show_barber_actions(message: types.Message, state: FSMContext):
    await state.clear()
    await _show_barber_page_message(message, index=0)


@router.callback_query(F.data == BARBER_ADD_CB)
async def add_barber_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_add_barber(callback.message, state)


@router.message(F.text == BARBER_ADD_TEXT)
async def add_barber_start(message: types.Message, state: FSMContext):
    await _start_add_barber(message, state)


@router.callback_query(F.data == BARBER_DEL_CB)
async def open_barber_page_for_legacy_delete(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_barber_page_callback(callback, index=0)
    await callback.answer(
        "Kerakli barberni ochib, shu sahifadan o'chirishni tasdiqlang.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith(f"{BARBER_DELETE_PICK_PREFIX}:"))
async def ask_barber_delete_confirmation(callback: types.CallbackQuery, state: FSMContext):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await state.clear()
    total, index, barber = await _fetch_barber_page(index)
    if barber is None:
        await callback.answer("O'chirish uchun barber topilmadi.", show_alert=True)
        await _show_barber_page_callback(callback, index=0, total=0)
        return

    await _edit_or_send_barber_message(
        callback,
        text=_render_barber_delete_confirmation_text(total, index, barber),
        reply_markup=_barber_delete_confirmation_keyboard(barber.id, index),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BARBER_DELETE_CANCEL_PREFIX}:"))
async def cancel_barber_delete(callback: types.CallbackQuery):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await _show_barber_page_callback(callback, index=index)
    await callback.answer("O'chirish bekor qilindi.")


@router.callback_query(F.data.startswith(f"{BARBER_DELETE_CONFIRM_PREFIX}:"))
async def confirm_barber_delete(callback: types.CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    try:
        barber_id = int(parts[3])
        index = int(parts[4])
    except ValueError:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    async with async_session() as session:
        barber = await session.get(Barbers, barber_id)
        if barber is None:
            await callback.answer("Barber topilmadi.", show_alert=True)
            await _show_barber_page_callback(callback, index=index)
            return

        deleted_name = _barber_display_name(barber)
        await session.execute(delete(BarberPhotos).where(BarberPhotos.barber_id == barber_id))
        await session.execute(delete(BarberExpanded).where(BarberExpanded.barber_id == barber_id))
        await session.delete(barber)
        await session.commit()

    remaining_total = await _count_barbers()
    next_index = 0 if remaining_total <= 0 else min(index, remaining_total - 1)

    await _show_barber_page_callback(
        callback,
        index=next_index,
        total=remaining_total,
        notice=f"✅ <b>{escape(deleted_name)}</b> barber o'chirildi.",
    )
    await callback.answer("Barber o'chirildi.", show_alert=True)


@router.message(StateFilter(AdminStates.adding_barber_fullname))
async def add_barber_fullname(message: types.Message, state: FSMContext):
    fullname = (message.text or "").strip()

    if len(fullname.split()) < 2:
        await message.answer(
            with_cancel_hint("❌ Iltimos, to'liq ism kiriting (Ism Familiya).")
        )
        return

    first_name, last_name = fullname.split(" ", 1)

    async with async_session() as session:
        existing = await session.execute(
            select(Barbers).where(
                Barbers.barber_first_name.ilike(first_name),
                Barbers.barber_last_name.ilike(last_name),
            )
        )
        if existing.scalar_one_or_none():
            await message.answer(
                with_cancel_hint("⚠️ Bu barber allaqachon ro'yxatda bor.")
            )
            return

        user_query = await session.execute(
            select(OrdinaryUser).where(
                OrdinaryUser.first_name.ilike(first_name),
                OrdinaryUser.last_name.ilike(last_name),
            )
        )
        user = user_query.scalar_one_or_none()

        if not user:
            fallback = await session.execute(
                select(OrdinaryUser).where(OrdinaryUser.first_name.ilike(first_name))
            )
            user = fallback.scalar_one_or_none()

        tg_id = user.tg_id if user else None
        tg_username = user.username if user else None

    await state.update_data(
        first_name=first_name,
        last_name=last_name,
        tg_id=tg_id,
        tg_username=tg_username,
    )

    await state.set_state(AdminStates.adding_barber_phone)
    await message.answer(
        with_cancel_hint(
            "📞 Endi barberning telefon raqamini kiriting.\n\n"
            f"🔎 <b>Telegramdan topildi:</b> <code>{tg_id if tg_id else 'Topilmadi'}</code>"
        ),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.adding_barber_phone))
async def add_barber_phone(message: types.Message, state: FSMContext):
    phone = (message.text or "").strip()

    if not phone.startswith("+998") or len(phone) != 13 or not phone[1:].isdigit():
        await message.answer(
            with_cancel_hint(
                "❌ Telefon raqam noto'g'ri.\n"
                "Namuna: <b>+998901234567</b>"
            ),
            parse_mode="HTML",
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(AdminStates.adding_barber_experience)

    await message.answer(
        with_cancel_hint(
            "💼 Barberning ish tajribasini kiriting.\n"
            "Masalan: <b>3 yil</b>"
        ),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.adding_barber_experience))
async def add_barber_experience(message: types.Message, state: FSMContext):
    experience = (message.text or "").strip()

    if len(experience) < 2:
        await message.answer(with_cancel_hint("❌ Tajriba juda qisqa. Qayta kiriting."))
        return

    await state.update_data(experience=experience)
    await state.set_state(AdminStates.adding_barber_work_days)

    await message.answer(
        with_cancel_hint(
            "📅 Barberning ish kunlarini kiriting.\n"
            "Masalan: <b>Dushanba-Juma</b>"
        ),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.adding_barber_work_days))
async def add_barber_work_days(message: types.Message, state: FSMContext):
    work_days = (message.text or "").strip()

    if len(work_days) < 3:
        await message.answer(with_cancel_hint("❌ Ish kunlari noto'g'ri."))
        return

    await state.update_data(work_days=work_days)
    await state.set_state(AdminStates.adding_barber_work_time)

    await message.answer(
        with_cancel_hint(
            "🕒 Barberning ish vaqti qaysi vaqtdan qaysi vaqtgacha?\n"
            "Format: <code>09:00-18:00</code>"
        ),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.adding_barber_work_time))
async def add_barber_work_time(message: types.Message, state: FSMContext):
    work_time_text = (message.text or "").strip()
    parsed = _parse_time_range(work_time_text)
    if not parsed:
        await message.answer(
            with_cancel_hint(
                "❌ Noto'g'ri format.\n"
                "To'g'ri format: <code>09:00-18:00</code>"
            ),
            parse_mode="HTML",
        )
        return

    start, end = parsed
    await state.update_data(work_time=f"{start}-{end}")
    await state.set_state(AdminStates.adding_barber_breakdown)

    await message.answer(
        with_cancel_hint(
            "⏸️ Barber tanaffus vaqtini kiriting.\n"
            "Format: <code>13:00-14:00</code>\n"
            "Agar tanaffus bo'lmasa: <code>yo'q</code>"
        ),
        parse_mode="HTML",
    )


@router.message(StateFilter(AdminStates.adding_barber_breakdown))
async def add_barber_breakdown(message: types.Message, state: FSMContext):
    raw_text = (message.text or "").strip()
    breakdown_text = raw_text.lower()

    if breakdown_text in {"yo'q", "yoq"}:
        breakdown = None
    else:
        parsed = _parse_time_range(raw_text)
        if not parsed:
            await message.answer(
                with_cancel_hint(
                    "Noto'g'ri format.\n"
                    "To'g'ri format: <code>13:00-14:00</code>\n"
                    "Agar tanaffus bo'lmasa: <code>yo'q</code>"
                ),
                parse_mode="HTML",
            )
            return
        start, end = parsed
        breakdown = f"{start}-{end}"

    await state.update_data(breakdown=breakdown)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📸 Rasm qo'shaman", callback_data="add_photo_yes"),
                InlineKeyboardButton(text="➡️ Rasm kerak emas", callback_data="add_photo_no"),
            ]
        ]
    )

    await state.set_state(AdminStates.adding_photo_choice)
    await message.answer(
        with_cancel_hint("Barber uchun rasm qo'shasizmi?"),
        reply_markup=markup,
    )


@router.callback_query(F.data == "add_photo_yes", StateFilter(AdminStates.adding_photo_choice))
async def ask_for_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AdminStates.adding_barber_photo)
    if call.message:
        await call.message.answer(with_cancel_hint("📸 Iltimos, barberning rasmini yuboring."))


@router.callback_query(F.data == "add_photo_no", StateFilter(AdminStates.adding_photo_choice))
async def save_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        barber = Barbers(
            barber_first_name=data["first_name"],
            barber_last_name=data["last_name"],
            tg_id=data["tg_id"],
            tg_username=data["tg_username"],
            phone=data["phone"],
            experience=data["experience"],
            work_days=data["work_days"],
            work_time=data.get("work_time"),
            breakdown=data.get("breakdown"),
            is_paused_date=date.today(),
        )
        session.add(barber)
        await session.commit()

    work_time = escape(_format_time_range(data.get("work_time")))
    breakdown = escape(_format_time_range(data.get("breakdown")))
    full_name = escape(f"{data['first_name']} {data['last_name']}".strip())
    phone = escape(data["phone"])
    experience = escape(data["experience"])
    work_days = escape(data["work_days"])

    if call.message:
        await call.message.answer(
            "✅ <b>Barber muvaffaqiyatli qo'shildi!</b>\n\n"
            f"👨‍🎤 <b>{full_name}</b>\n"
            f"📞 {phone}\n"
            f"💼 {experience}\n"
            f"📅 {work_days}\n"
            f"🕒 Ish vaqti: <b>{work_time}</b>\n"
            f"⏸️ Tanaffus: <b>{breakdown}</b>\n"
            "📸 Rasm: <i>Yo'q</i>",
            parse_mode="HTML",
        )

    await state.clear()
    await call.answer()


@router.message(StateFilter(AdminStates.adding_barber_photo), F.photo)
async def add_barber_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id

    data = await state.get_data()
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    phone = data.get("phone")
    experience = data.get("experience")
    work_days = data.get("work_days")
    work_time = data.get("work_time")
    breakdown = data.get("breakdown")
    tg_id = data.get("tg_id")
    tg_username = data.get("tg_username")

    if not all([first_name, last_name, phone, experience, work_days, work_time]):
        await message.answer(
            with_cancel_hint("❌ Ma'lumotlar yetarli emas. Jarayon buzildi. Qayta boshlang.")
        )
        await state.clear()
        return

    async with async_session() as session:
        new_barber = Barbers(
            barber_first_name=first_name,
            barber_last_name=last_name,
            tg_id=tg_id,
            tg_username=tg_username,
            phone=phone,
            experience=experience,
            work_days=work_days,
            work_time=work_time,
            breakdown=breakdown,
            is_paused_date=date.today(),
        )
        session.add(new_barber)
        await session.flush()
        session.add(
            BarberPhotos(
                barber_id=new_barber.id,
                photo=photo_file_id,
            )
        )
        await session.commit()

    work_time_text = escape(_format_time_range(work_time))
    breakdown_text = escape(_format_time_range(breakdown))
    full_name = escape(f"{first_name} {last_name}".strip())
    phone_text = escape(phone)
    experience_text = escape(experience)
    work_days_text = escape(work_days)

    await message.answer(
        "✅ <b>Barber rasm bilan saqlandi!</b>\n\n"
        f"👨‍🎤 <b>{full_name}</b>\n"
        f"📞 {phone_text}\n"
        f"💼 {experience_text}\n"
        f"📅 {work_days_text}\n"
        f"🕒 Ish vaqti: <b>{work_time_text}</b>\n"
        f"⏸️ Tanaffus: <b>{breakdown_text}</b>\n"
        "📸 Rasm: <i>mavjud</i>",
        parse_mode="HTML",
    )

    await state.clear()


@router.message(StateFilter(AdminStates.adding_barber_photo))
async def expected_photo(message: types.Message):
    await message.answer(
        with_cancel_hint("❌ Iltimos, rasm yuboring yoki rasm tanlash tugmalaridan foydalaning.")
    )
