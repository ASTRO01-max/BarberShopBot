# handlers/booking.py
import logging
import re
from datetime import date, datetime, time, timedelta

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from sqlalchemy import or_, select

from keyboards import booking_keyboards
from keyboards.main_buttons import get_dynamic_main_keyboard, phone_request_keyboard
from keyboards.main_menu import get_main_menu
from sql.db import async_session
from sql.db_barbers_expanded import get_barbers_by_service
from sql.db_order_utils import save_order
from sql.db_users_utils import get_user, save_user
from sql.models import BarberPhotos, Barbers, Order, Services
from superadmins.order_realtime_notify import notify_barber_realtime
from utils.emoji_map import SERVICE_EMOJIS
from utils.states import UserState
from utils.validators import parse_user_date

logger = logging.getLogger(__name__)
router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
BOOKING_FOR_ME_CB = "booking_for_me"
BOOKING_FOR_OTHER_CB = "booking_for_other"
NO_BARBER_FOR_SERVICE_TEXT = "Hozircha ushbu xizmat uchun barber mavjud emas"
TIME_BUTTONS_PER_ROW = 2
DEFAULT_EXISTING_ORDER_DURATION_MINUTES = 60
ISO_DATE_FORMAT = "%Y-%m-%d"
HM_TIME_FORMAT = "%H:%M"
DURATION_HOUR_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(soat|hour|hours|hr|hrs|h|час|ч)\b",
    re.IGNORECASE,
)
DURATION_MINUTE_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(daqiqa|minute|minutes|min|мин|m)\b",
    re.IGNORECASE,
)
TIME_TOKEN_PATTERN = re.compile(r"\d{1,2}:\d{2}")


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


def _parse_duration_minutes(raw_duration: str | int | float | None) -> int | None:
    if raw_duration is None:
        return None

    if isinstance(raw_duration, (int, float)):
        value = int(raw_duration)
        return value if value > 0 else None

    duration_text = str(raw_duration).strip().lower()
    if not duration_text:
        return None

    direct_time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", duration_text)
    if direct_time_match:
        hours = int(direct_time_match.group(1))
        minutes = int(direct_time_match.group(2))
        total_minutes = hours * 60 + minutes
        return total_minutes if total_minutes > 0 else None

    if duration_text.isdigit():
        value = int(duration_text)
        return value if value > 0 else None

    normalized_text = duration_text.replace(",", ".")
    total_minutes = 0.0

    for value, _ in DURATION_HOUR_PATTERN.findall(normalized_text):
        total_minutes += float(value) * 60
    for value, _ in DURATION_MINUTE_PATTERN.findall(normalized_text):
        total_minutes += float(value)

    if total_minutes > 0:
        return int(total_minutes)

    fallback_number = re.search(r"\d+(?:\.\d+)?", normalized_text)
    if fallback_number:
        guessed_minutes = int(float(fallback_number.group(0)))
        return guessed_minutes if guessed_minutes > 0 else None

    return None


def _parse_work_time_bounds(raw_work_time: str | None) -> tuple[time, time] | None:
    if not isinstance(raw_work_time, str):
        return None

    tokens = TIME_TOKEN_PATTERN.findall(raw_work_time)
    if len(tokens) < 2:
        return None

    try:
        start_time = datetime.strptime(tokens[0], HM_TIME_FORMAT).time()
        end_time = datetime.strptime(tokens[1], HM_TIME_FORMAT).time()
    except ValueError:
        return None

    if start_time >= end_time:
        return None
    return start_time, end_time


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, ISO_DATE_FORMAT).date()
    except (TypeError, ValueError):
        return None


def _normalize_time_value(raw_time: time | datetime | str | None) -> time | None:
    if raw_time is None:
        return None
    if isinstance(raw_time, time):
        return raw_time
    if isinstance(raw_time, datetime):
        return raw_time.time()
    if isinstance(raw_time, str):
        text = raw_time.strip()
        for fmt in (HM_TIME_FORMAT, "%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).time()
            except ValueError:
                continue
    return None


def _combine_local_datetime(target_date: date, target_time: time, tzinfo) -> datetime:
    naive_value = datetime.combine(target_date, target_time)
    return naive_value.replace(tzinfo=tzinfo) if tzinfo else naive_value


def _merge_busy_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


async def _calculate_available_slots(
    service_id: str,
    barber_id: str,
    date_str: str,
) -> list[str]:
    target_date = _parse_iso_date(date_str)
    if target_date is None:
        return []

    try:
        service_db_id = int(service_id)
        barber_db_id = int(barber_id)
    except (TypeError, ValueError):
        return []

    local_now = datetime.now().astimezone()
    tzinfo = local_now.tzinfo

    async with async_session() as session:
        service = await session.get(Services, service_db_id)
        barber = await session.get(Barbers, barber_db_id)
        if not service or not barber or barber.is_paused:
            return []

        work_bounds = _parse_work_time_bounds(barber.work_time)
        service_duration = _parse_duration_minutes(service.duration)
        if not work_bounds or not service_duration:
            return []

        orders_result = await session.execute(
            select(Order.time, Order.service_id).where(
                Order.barber_id == str(barber_id),
                Order.date == target_date,
            )
        )
        booked_rows = orders_result.all()

        booked_service_ids = {
            int(order_service_id)
            for _, order_service_id in booked_rows
            if str(order_service_id).isdigit()
        }

        duration_by_service_id: dict[str, int] = {}
        if booked_service_ids:
            durations_result = await session.execute(
                select(Services.id, Services.duration).where(Services.id.in_(booked_service_ids))
            )
            for booked_service_id, booked_duration in durations_result.all():
                parsed = _parse_duration_minutes(booked_duration)
                if parsed:
                    duration_by_service_id[str(booked_service_id)] = parsed

    start_time, end_time = work_bounds
    work_start = _combine_local_datetime(target_date, start_time, tzinfo)
    work_end = _combine_local_datetime(target_date, end_time, tzinfo)
    slot_duration = timedelta(minutes=service_duration)

    if work_start >= work_end or slot_duration <= timedelta(0):
        return []

    busy_intervals: list[tuple[datetime, datetime]] = []
    for booked_time_raw, booked_service_id_raw in booked_rows:
        booked_time = _normalize_time_value(booked_time_raw)
        if booked_time is None:
            continue

        booked_duration = duration_by_service_id.get(str(booked_service_id_raw))
        if booked_duration is None:
            booked_duration = service_duration or DEFAULT_EXISTING_ORDER_DURATION_MINUTES

        busy_start = _combine_local_datetime(target_date, booked_time, tzinfo)
        busy_end = busy_start + timedelta(minutes=booked_duration)
        busy_intervals.append((busy_start, busy_end))

    merged_busy = _merge_busy_intervals(busy_intervals)

    available_slots: list[str] = []
    current_start = work_start
    busy_index = 0

    while current_start + slot_duration <= work_end:
        current_end = current_start + slot_duration

        while busy_index < len(merged_busy) and merged_busy[busy_index][1] <= current_start:
            busy_index += 1

        has_overlap = (
            busy_index < len(merged_busy)
            and merged_busy[busy_index][0] < current_end
            and merged_busy[busy_index][1] > current_start
        )

        if current_start > local_now and not has_overlap:
            available_slots.append(current_start.strftime(HM_TIME_FORMAT))

        current_start += slot_duration

    return available_slots


async def _build_time_keyboard(
    service_id: str,
    barber_id: str,
    date_str: str,
) -> InlineKeyboardMarkup | None:
    available_slots = await _calculate_available_slots(service_id, barber_id, date_str)
    if not available_slots:
        return None

    inline_rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []

    for index, slot_time in enumerate(available_slots, start=1):
        current_row.append(
            InlineKeyboardButton(
                text=slot_time,
                callback_data=f"confirm_{service_id}_{barber_id}_{date_str}_{slot_time}",
            )
        )
        if index % TIME_BUTTONS_PER_ROW == 0:
            inline_rows.append(current_row)
            current_row = []

    if current_row:
        inline_rows.append(current_row)

    return InlineKeyboardMarkup(inline_keyboard=inline_rows)


def _booking_target_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Men uchun", callback_data=BOOKING_FOR_ME_CB)],
            [InlineKeyboardButton(text="Menga emas", callback_data=BOOKING_FOR_OTHER_CB)],
        ]
    )


def _service_nav_keyboard(index: int, total: int, service_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"booksrv_prev_{index}"),
                InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"booksrv_next_{index}"),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Xizmatni tanlash",
                    callback_data=f"booksrv_pick_{service_id}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")],
        ]
    )


def _barber_nav_keyboard(index: int, total: int, service_id: str, barber_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"bookbar_prev_{service_id}_{index}",
                ),
                InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"bookbar_next_{service_id}_{index}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Barberni tanlash",
                    callback_data=f"bookbar_pick_{service_id}_{barber_id}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")],
        ]
    )


def _barber_full_name(barber: Barbers) -> str:
    return " ".join(
        [part for part in [barber.barber_first_name, barber.barber_last_name] if part]
    ).strip() or f"Barber #{barber.id}"


async def _fetch_services():
    async with async_session() as session:
        result = await session.execute(select(Services).order_by(Services.id.asc()))
        return result.scalars().all()


async def _fetch_active_barbers_by_service(service_id: str):
    try:
        normalized_service_id = int(str(service_id))
    except (TypeError, ValueError):
        return []

    barber_ids = await get_barbers_by_service(normalized_service_id)
    if not barber_ids:
        return []

    async with async_session() as session:
        result = await session.execute(
            select(Barbers)
            .where(
                Barbers.id.in_(barber_ids),
                or_(Barbers.is_paused.is_(False), Barbers.is_paused.is_(None)),
            )
            .order_by(Barbers.id.asc())
        )
        return result.scalars().all()


async def _is_barber_available_for_service(service_id: str, barber_id: str) -> bool:
    barbers = await _fetch_active_barbers_by_service(service_id)
    return any(str(barber.id) == str(barber_id) for barber in barbers)


async def _fetch_latest_barber_photo(barber_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(BarberPhotos.photo)
            .where(BarberPhotos.barber_id == barber_id)
            .order_by(BarberPhotos.id.desc())
            .limit(1)
        )
        return result.scalar()


async def _resolve_service_id(raw_value: str | None) -> str | None:
    token = (raw_value or "").strip()
    if not token:
        return None

    async with async_session() as session:
        service = None
        if token.isdigit():
            service = await session.get(Services, int(token))

        if service is None:
            result = await session.execute(select(Services).where(Services.name == token))
            service = result.scalars().first()

    return str(service.id) if service else None


async def _resolve_service_name(service_id: str) -> str:
    async with async_session() as session:
        service = None
        if str(service_id).isdigit():
            service = await session.get(Services, int(service_id))

        if service is None:
            result = await session.execute(select(Services).where(Services.name == service_id))
            service = result.scalars().first()

    return service.name if service else str(service_id)


async def _resolve_barber_name(barber_id: str) -> str:
    async with async_session() as session:
        barber = None
        if str(barber_id).isdigit():
            barber = await session.get(Barbers, int(barber_id))
    return _barber_full_name(barber) if barber else str(barber_id)


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
    message: Message,
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
    await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")


async def _show_service_page_callback(callback: CallbackQuery, index: int = 0) -> bool:
    services = await _fetch_services()
    if not services:
        await _render_catalog_callback(
            callback,
            with_cancel_hint("⚠️ Hozircha xizmatlar mavjud emas."),
            booking_keyboards.back_button(),
        )
        return False

    index = index % len(services)
    service = services[index]
    emoji = SERVICE_EMOJIS.get(service.name, "🔹")
    caption = with_cancel_hint(
        f"💈 <b>Xizmatni tanlang</b>\n\n"
        f"{emoji} <b>{service.name}</b>\n"
        f"💵 <b>Narx:</b> {service.price} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {service.duration}\n\n"
        f"📌 <i>({index + 1} / {len(services)})</i>"
    )
    await _render_catalog_callback(
        callback,
        caption,
        _service_nav_keyboard(index, len(services), str(service.id)),
        getattr(service, "photo", None),
    )
    return True


async def _show_service_page_message(message: Message, index: int = 0) -> bool:
    services = await _fetch_services()
    if not services:
        await message.answer(with_cancel_hint("⚠️ Hozircha xizmatlar mavjud emas."))
        return False

    index = index % len(services)
    service = services[index]
    emoji = SERVICE_EMOJIS.get(service.name, "🔹")
    caption = with_cancel_hint(
        f"💈 <b>Xizmatni tanlang</b>\n\n"
        f"{emoji} <b>{service.name}</b>\n"
        f"💵 <b>Narx:</b> {service.price} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {service.duration}\n\n"
        f"📌 <i>({index + 1} / {len(services)})</i>"
    )
    await _send_catalog_message(
        message,
        caption,
        _service_nav_keyboard(index, len(services), str(service.id)),
        getattr(service, "photo", None),
    )
    return True


async def _show_barber_page_callback(callback: CallbackQuery, service_id: str, index: int = 0) -> bool:
    barbers = await _fetch_active_barbers_by_service(service_id)
    if not barbers:
        await _render_catalog_callback(
            callback,
            with_cancel_hint(f"⚠️ {NO_BARBER_FOR_SERVICE_TEXT}."),
            booking_keyboards.back_button(),
        )
        return False

    index = index % len(barbers)
    barber = barbers[index]
    lines = [
        "💈 <b>Barberni tanlang</b>\n",
        f"\n👨‍🎤 <b>{_barber_full_name(barber)}</b>\n",
    ]
    if barber.experience:
        lines.append(f"💼 <b>Tajriba:</b> {barber.experience}\n")
    if barber.work_days:
        lines.append(f"📅 <b>Ish kunlari:</b> {barber.work_days}\n")
    if barber.work_time:
        lines.append(f"⏰ <b>Ish vaqti:</b> {barber.work_time}\n")
    if barber.breakdown:
        lines.append(f"⏸️ <b>Tanaffus:</b> {barber.breakdown}\n")
    if barber.phone:
        lines.append(f"📞 <b>Aloqa:</b> <code>{barber.phone}</code>\n")
    lines.append(f"\n📌 <i>({index + 1} / {len(barbers)})</i>")

    caption = with_cancel_hint("".join(lines))
    photo = await _fetch_latest_barber_photo(barber.id)
    await _render_catalog_callback(
        callback,
        caption,
        _barber_nav_keyboard(index, len(barbers), service_id, str(barber.id)),
        photo,
    )
    return True


async def _show_barber_page_message(message: Message, service_id: str, index: int = 0) -> bool:
    barbers = await _fetch_active_barbers_by_service(service_id)
    if not barbers:
        await message.answer(with_cancel_hint(f"⚠️ {NO_BARBER_FOR_SERVICE_TEXT}."))
        return False

    index = index % len(barbers)
    barber = barbers[index]
    lines = [
        "💈 <b>Barberni tanlang</b>\n",
        f"\n👨‍🎤 <b>{_barber_full_name(barber)}</b>\n",
    ]
    if barber.experience:
        lines.append(f"💼 <b>Tajriba:</b> {barber.experience}\n")
    if barber.work_days:
        lines.append(f"📅 <b>Ish kunlari:</b> {barber.work_days}\n")
    if barber.work_time:
        lines.append(f"⏰ <b>Ish vaqti:</b> {barber.work_time}\n")
    if barber.breakdown:
        lines.append(f"⏸️ <b>Tanaffus:</b> {barber.breakdown}\n")
    if barber.phone:
        lines.append(f"📞 <b>Aloqa:</b> <code>{barber.phone}</code>\n")
    lines.append(f"\n📌 <i>({index + 1} / {len(barbers)})</i>")

    caption = with_cancel_hint("".join(lines))
    photo = await _fetch_latest_barber_photo(barber.id)
    await _send_catalog_message(
        message,
        caption,
        _barber_nav_keyboard(index, len(barbers), service_id, str(barber.id)),
        photo,
    )
    return True


async def _has_user_profile(user_id: int, state: FSMContext) -> bool:
    state_data = await state.get_data()
    if state_data.get("fullname") and state_data.get("phonenumber"):
        return True
    if state_data.get("is_for_other"):
        return False
    user = await get_user(user_id)
    return bool(user)


async def _ask_fullname(callback: CallbackQuery):
    text = with_cancel_hint(
        "Iltimos, to'liq ismingizni kiriting (masalan: Aliyev Valijon):"
    )
    if callback.message.photo:
        await callback.message.edit_caption(caption=text)
    else:
        await callback.message.edit_text(text)


async def _go_to_date_from_callback(
    callback: CallbackQuery,
    state: FSMContext,
    service_id: str,
    barber_id: str,
    answer_text: str,
):
    await state.update_data(service_id=service_id, barber_id=barber_id)
    if callback.message.photo:
        await callback.message.edit_caption(
            caption=with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
        )
    else:
        await callback.message.edit_text(
            with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
        )
    await state.set_state(UserState.waiting_for_date)
    await callback.answer(answer_text)


async def _go_to_date_from_message(
    message: Message,
    state: FSMContext,
    service_id: str,
    barber_id: str,
):
    await state.update_data(service_id=service_id, barber_id=barber_id)
    await message.answer(
        with_cancel_hint("📅 Sana tanlang:"),
        reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
    )
    await state.set_state(UserState.waiting_for_date)


async def _handle_service_selected(callback: CallbackQuery, state: FSMContext, service_id: str):
    await state.update_data(service_id=service_id)
    data = await state.get_data()
    barber_id = data.get("barber_id")

    if barber_id:
        if await _is_barber_available_for_service(service_id, str(barber_id)):
            await _go_to_date_from_callback(
                callback,
                state,
                service_id,
                str(barber_id),
                "Xizmat tanlandi ✅",
            )
            return

        await state.update_data(barber_id=None)

    shown = await _show_barber_page_callback(callback, service_id, index=0)
    await state.set_state(UserState.waiting_for_barber)
    if shown:
        await callback.answer("Xizmat tanlandi ✅")
    else:
        await callback.answer(NO_BARBER_FOR_SERVICE_TEXT, show_alert=True)


async def _handle_barber_selected(
    callback: CallbackQuery,
    state: FSMContext,
    service_id: str,
    barber_id: str,
):
    resolved_service_id = await _resolve_service_id(service_id)
    if not resolved_service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    if not await _is_barber_available_for_service(resolved_service_id, barber_id):
        shown = await _show_barber_page_callback(callback, resolved_service_id, index=0)
        await state.set_state(UserState.waiting_for_barber)
        if shown:
            await callback.answer("Tanlangan barber ushbu xizmatni ko'rsatmaydi", show_alert=True)
        else:
            await callback.answer(NO_BARBER_FOR_SERVICE_TEXT, show_alert=True)
        return

    await _go_to_date_from_callback(
        callback,
        state,
        resolved_service_id,
        barber_id,
        "Barber tanlandi ✅",
    )


@router.message(
    StateFilter(
        UserState.waiting_for_fullname,
        UserState.waiting_for_phonenumber,
        UserState.waiting_for_service,
        UserState.waiting_for_barber,
        UserState.waiting_for_date,
        UserState.waiting_for_time,
    ),
    F.text.startswith("/cancel"),
)
async def cancel_booking(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Navbat olish jarayoni bekor qilindi.\n\n🏠 Asosiy menyuga qaytdingiz.",
        reply_markup=get_main_menu(),
    )


async def start_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = with_cancel_hint("Kim uchun navbat olmoqchisiz?")
    markup = _booking_target_keyboard()
    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def _start_booking_for_me(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(is_for_other=False)
    user_id = callback.from_user.id
    user = await get_user(user_id)

    if not user:
        await _ask_fullname(callback)
        await state.set_state(UserState.waiting_for_fullname)
        await callback.answer("Ro'yxatdan o'tishni boshlaymiz ✅")
        return

    await state.set_state(UserState.waiting_for_service)
    shown = await _show_service_page_callback(callback, index=0)
    if shown:
        await callback.answer("Navbat olish boshlandi ✅")
    else:
        await callback.answer("Xizmatlar topilmadi", show_alert=True)


@router.callback_query(F.data == BOOKING_FOR_ME_CB)
async def booking_for_me_callback(callback: CallbackQuery, state: FSMContext):
    await _start_booking_for_me(callback, state)


@router.callback_query(F.data == BOOKING_FOR_OTHER_CB)
async def booking_for_other_callback(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_for_other=True)
    await _ask_fullname(callback)
    await state.set_state(UserState.waiting_for_fullname)
    await callback.answer("Boshqa shaxs uchun ma'lumot kiriting ✅")


async def start_booking_from_barber(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Noto'g'ri barber ma'lumoti", show_alert=True)
        return

    barber_id = parts[2]
    data = await state.get_data()
    current_state = await state.get_state()

    if current_state == UserState.waiting_for_barber.state and data.get("service_id"):
        await _handle_barber_selected(callback, state, str(data["service_id"]), barber_id)
        return

    await state.update_data(barber_id=barber_id)
    has_profile = await _has_user_profile(callback.from_user.id, state)
    if not has_profile:
        await _ask_fullname(callback)
        await state.set_state(UserState.waiting_for_fullname)
        await callback.answer("Barber tanlandi, ro'yxatdan o'tamiz ✅")
        return

    await state.set_state(UserState.waiting_for_service)
    shown = await _show_service_page_callback(callback, index=0)
    if shown:
        await callback.answer("Barber tanlandi, xizmatni tanlang ✅")
    else:
        await callback.answer("Xizmatlar topilmadi", show_alert=True)


async def start_booking_from_service(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Noto'g'ri xizmat ma'lumoti", show_alert=True)
        return

    service_id = await _resolve_service_id(parts[2])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    await state.update_data(service_id=service_id)
    has_profile = await _has_user_profile(callback.from_user.id, state)

    if not has_profile:
        await _ask_fullname(callback)
        await state.set_state(UserState.waiting_for_fullname)
        await callback.answer("Xizmat tanlandi, ro'yxatdan o'tamiz ✅")
        return

    await _handle_service_selected(callback, state, service_id)


async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip()

    if len(fullname.split()) < 2:
        await message.answer(
            with_cancel_hint(
                "❌ Iltimos, ism va familiyani to'liq kiriting (masalan: Aliyev Valijon)."
            )
        )
        return

    await state.update_data(fullname=fullname)
    await message.answer(
        with_cancel_hint("📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:"),
        reply_markup=phone_request_keyboard,
    )
    await state.set_state(UserState.waiting_for_phonenumber)


async def process_phonenumber(message: Message, state: FSMContext):
    raw_phone = None

    if message.contact and message.contact.phone_number:
        raw_phone = message.contact.phone_number
    elif message.text:
        raw_phone = message.text.strip()

    if not raw_phone:
        await message.answer(
            with_cancel_hint("❌ Iltimos, telefon raqamini yuboring (masalan: +998901234567).")
        )
        return

    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("998") and len(digits) == 12:
        phonenumber = f"+{digits}"
    elif len(digits) == 9:
        phonenumber = f"+998{digits}"
    else:
        phonenumber = None

    if not phonenumber or not phonenumber.startswith("+998") or len(phonenumber) != 13:
        await message.answer(
            with_cancel_hint(
                "❌ Iltimos, telefon raqamini to'g'ri kiriting (masalan: +998901234567)."
            )
        )
        return

    data = await state.get_data()
    fullname = data.get("fullname") or message.from_user.full_name or "Ism kiritilmagan"
    await state.update_data(fullname=fullname, phonenumber=phonenumber)

    await message.answer(
        "📱 Raqamingiz qabul qilindi ✅",
        reply_markup=await get_dynamic_main_keyboard(message.from_user.id),
    )

    data = await state.get_data()
    service_id = str(data["service_id"]) if data.get("service_id") is not None else None
    barber_id = str(data["barber_id"]) if data.get("barber_id") is not None else None

    if service_id and barber_id:
        if await _is_barber_available_for_service(service_id, barber_id):
            await _go_to_date_from_message(message, state, service_id, barber_id)
            return
        await state.update_data(barber_id=None)

    if service_id:
        await _show_barber_page_message(message, service_id, index=0)
        await state.set_state(UserState.waiting_for_barber)
        return

    await _show_service_page_message(message, index=0)
    await state.set_state(UserState.waiting_for_service)


async def booking_service_nav(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 3:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    action = parts[1]
    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Noto'g'ri sahifa", show_alert=True)
        return

    services = await _fetch_services()
    if not services:
        await callback.answer("Xizmatlar topilmadi", show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(services)
    else:
        index = (index - 1) % len(services)

    await _show_service_page_callback(callback, index)
    await state.set_state(UserState.waiting_for_service)
    await callback.answer()


async def booking_service_pick(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Noto'g'ri xizmat", show_alert=True)
        return

    service_id = await _resolve_service_id(parts[2])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    await _handle_service_selected(callback, state, service_id)


async def booking_barber_nav(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 3)
    if len(parts) != 4:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    action = parts[1]
    service_id = await _resolve_service_id(parts[2])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    try:
        index = int(parts[3])
    except ValueError:
        await callback.answer("Noto'g'ri sahifa", show_alert=True)
        return

    barbers = await _fetch_active_barbers_by_service(service_id)
    if not barbers:
        await callback.answer(NO_BARBER_FOR_SERVICE_TEXT, show_alert=True)
        return

    if action == "next":
        index = (index + 1) % len(barbers)
    else:
        index = (index - 1) % len(barbers)

    await _show_barber_page_callback(callback, service_id, index)
    await state.set_state(UserState.waiting_for_barber)
    await callback.answer()


async def booking_barber_pick(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 3)
    if len(parts) != 4:
        await callback.answer("Noto'g'ri barber", show_alert=True)
        return

    service_id = parts[2]
    barber_id = parts[3]
    await _handle_barber_selected(callback, state, service_id, barber_id)


async def book_step1(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 1)
    if len(parts) < 2:
        await callback.answer("Noto'g'ri xizmat", show_alert=True)
        return

    service_id = await _resolve_service_id(parts[1])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    await _handle_service_selected(callback, state, service_id)


async def book_step2(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) != 3:
        await callback.answer("Noto'g'ri barber", show_alert=True)
        return

    service_id = await _resolve_service_id(parts[1])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    barber_id = parts[2]
    await _handle_barber_selected(callback, state, service_id, barber_id)


async def book_step3(callback: CallbackQuery, state: FSMContext):
    _, service_id, barber_id, date = callback.data.split("_")
    await state.update_data(date=date)

    keyboard = await _build_time_keyboard(service_id, barber_id, date)

    if keyboard is None:
        back_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Orqaga",
                        callback_data=f"back_date_{service_id}_{barber_id}",
                    )
                ]
            ]
        )

        if callback.message.photo:
            await callback.message.edit_caption(
                caption=with_cancel_hint("❌ Kechirasiz, bu kunga barcha vaqtlar band."),
                reply_markup=back_markup,
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("❌ Kechirasiz, bu kunga barcha vaqtlar band."),
                reply_markup=back_markup,
            )
    else:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=with_cancel_hint("⏰ Vaqt tanlang:"),
                reply_markup=keyboard,
            )
        else:
            await callback.message.edit_text(
                with_cancel_hint("⏰ Vaqt tanlang:"),
                reply_markup=keyboard,
            )

    await state.set_state(
        UserState.waiting_for_date if keyboard is None else UserState.waiting_for_time
    )
    await callback.answer("Sana qabul qilindi ✅")


@router.message(UserState.waiting_for_date)
async def book_step3_message(message: Message, state: FSMContext):
    date = parse_user_date(message.text.strip())

    if not date:
        await message.answer(
            with_cancel_hint("❌ Kechirasiz, biz faqat joriy oy ichidagi sanalarni qabul qilamiz.")
        )
        return

    await state.update_data(date=date)

    data = await state.get_data()
    keyboard = await _build_time_keyboard(
        data["service_id"],
        data["barber_id"],
        date,
    )

    if keyboard is None:
        await message.answer(with_cancel_hint("❌ Bu kunda bo'sh vaqt yo'q."))
        return

    await message.answer(with_cancel_hint("⏰ Vaqtni tanlang:"), reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_time)


async def back_to_date(callback: CallbackQuery, state: FSMContext):
    _, _, service_id, barber_id = callback.data.split("_")

    if callback.message.photo:
        await callback.message.edit_caption(
            caption=with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
        )
    else:
        await callback.message.edit_text(
            with_cancel_hint("📅 Sana tanlang:"),
            reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
        )

    await state.set_state(UserState.waiting_for_date)
    await callback.answer("🔙 Orqaga qaytildi")


@router.callback_query(F.data.startswith("confirm_"))
async def confirm(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    _, service_id, barber_id, date_str, time_str = data.split("_", 4)
    user_id = callback.from_user.id

    markup = callback.message.reply_markup
    if markup and markup.inline_keyboard:
        new_keyboard = [
            [btn for btn in row if btn.callback_data != data]
            for row in markup.inline_keyboard
            if any(btn.callback_data != data for btn in row)
        ]
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard)
        )

    available_slots = await _calculate_available_slots(service_id, barber_id, date_str)
    if time_str not in available_slots:
        await callback.answer(
            "⛔ Ushbu vaqt endi mavjud emas.\nBoshqa vaqt tanlang.",
            show_alert=True,
        )
        return

    user_data = await state.get_data()
    is_for_other = bool(user_data.get("is_for_other"))
    fullname = user_data.get("fullname")
    phone = user_data.get("phonenumber")

    if (not fullname or not phone) and not is_for_other:
        user = await get_user(user_id)
        if user:
            fullname = fullname or user.fullname
            phone = phone or user.phone

    fullname = fullname or "Noma'lum"
    phone = phone or "Noma'lum"

    if not is_for_other and fullname != "Noma'lum" and phone != "Noma'lum":
        saved_user = await save_user(
            {
                "tg_id": user_id,
                "fullname": fullname,
                "phone": phone,
            }
        )
        if saved_user:
            fullname = saved_user.fullname or fullname
            phone = saved_user.phone or phone

    service_name = await _resolve_service_name(service_id)
    barber_name = await _resolve_barber_name(barber_id)

    order = {
        "user_id": user_id,
        "fullname": fullname,
        "phonenumber": phone,
        "service_id": service_id,
        "barber_id": barber_id,
        "barber_id_name": barber_name,
        "date": date_str,
        "time": time_str,
    }

    created = await save_order(order)
    try:
        await notify_barber_realtime(callback.bot, created.id, int(barber_id))
    except Exception:
        logger.exception("notify_barber_realtime failed")

    text = (
        "✅ <b>Buyurtmangiz muvaffaqiyatli saqlandi!</b>\n\n"
        f"👤 <b>Ism:</b> {fullname}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"💈 <b>Xizmat:</b> {service_name}\n"
        f"👨‍💼 <b>Usta:</b> {barber_name}\n"
        f"📅 <b>Sana:</b> {date_str}\n"
        f"🕔 <b>Vaqt:</b> {time_str}"
    )

    if callback.message.photo:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, parse_mode="HTML")

    await state.clear()
    await callback.answer("Vaqt tanlandi ✅")
    await callback.message.answer(
        "📱 Menyu yangilandi:",
        reply_markup=await get_dynamic_main_keyboard(user_id),
    )
    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu(),
    )
