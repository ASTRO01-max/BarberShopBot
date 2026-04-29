# handlers/booking.py
import logging
import re
from datetime import date, datetime, time, timedelta
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
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
from handlers.barber_cards import barber_full_name, get_barber_card_content
from sql.db import async_session
from sql.db_services import list_services_ordered
from sql.db_barbers_expanded import get_barbers_by_service
from sql.db_temporary_orders import (
    delete_temporary_order,
    finalize_temporary_order,
    get_temporary_order,
    is_temporary_order_complete,
    upsert_temporary_order,
)
from sql.db_users_utils import get_user, save_user
from sql.models import Barbers, OrdinaryUser, Services, Order
from superadmins.order_realtime_notify import notify_barber_realtime
from utils.emoji_map import SERVICE_EMOJIS
from utils.service_pricing import build_service_price_lines
from utils.states import UserState
from utils.validators import parse_user_date


logger = logging.getLogger(__name__)
router = Router()

CANCEL_HINT = "\n\n↩️ Bekor qilish uchun /cancel yuboring."
BOOKING_CANCELLED_TEXT = "🚫 Navbat olish jarayoni bekor qilindi.\n\n🏠 Asosiy menyuga qaytdingiz."
BOOKING_FOR_ME_CB = "booking_for_me"
BOOKING_FOR_OTHER_CB = "booking_for_other"
BOOKING_RESUME_CONTINUE_CB = "booking_resume_continue"
BOOKING_RESUME_RESTART_CB = "booking_resume_restart"
NO_BARBER_FOR_SERVICE_TEXT = "🛑 Hozircha ushbu xizmat uchun barber mavjud emas"
SELECTED_BARBER_UNAVAILABLE_TEXT = "❌ Tanlangan barber ushbu xizmatni bajarmaydi."
LOCKED_BARBER_STATE_KEY = "selected_barber_locked"
PENDING_BOOKING_ENTRY_KEY = "pending_booking_entry"
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
    return f"<b>{text}</b>{CANCEL_HINT}"


def _state_value(state: State | str | None) -> str | None:
    if state is None:
        return None
    if isinstance(state, State):
        return state.state
    return str(state)


def _booking_resume_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Davom ettirish", callback_data=BOOKING_RESUME_CONTINUE_CB)],
            [InlineKeyboardButton(text="Qaytadan boshlash", callback_data=BOOKING_RESUME_RESTART_CB)],
        ]
    )


def _build_entry_context(
    kind: str,
    *,
    service_id: str | None = None,
    barber_id: str | None = None,
) -> dict[str, str]:
    payload = {"kind": kind}
    if service_id is not None:
        payload["service_id"] = str(service_id)
    if barber_id is not None:
        payload["barber_id"] = str(barber_id)
    return payload


def _build_ordinary_fullname(ordinary_user: OrdinaryUser | None) -> str | None:
    if ordinary_user is None:
        return None

    first_name = (ordinary_user.first_name or "").strip()
    last_name = (ordinary_user.last_name or "").strip()
    if not first_name or not last_name:
        return None
    return f"{first_name} {last_name}"


async def _get_self_booking_seed(user_id: int) -> dict[str, str | None]:
    seed: dict[str, str | None] = {"fullname": None, "phonenumber": None}
    user = await get_user(user_id)
    if user:
        seed["fullname"] = (user.fullname or "").strip() or None
        seed["phonenumber"] = (user.phone or "").strip() or None

    if seed["fullname"]:
        return seed

    async with async_session() as session:
        result = await session.execute(select(OrdinaryUser).where(OrdinaryUser.tg_id == user_id))
        ordinary_user = result.scalars().first()

    seed["fullname"] = _build_ordinary_fullname(ordinary_user)
    return seed


def _resolve_initial_self_state(seed: dict[str, str | None]) -> State:
    if seed.get("fullname") and seed.get("phonenumber"):
        return UserState.waiting_for_service
    if seed.get("fullname"):
        return UserState.waiting_for_phonenumber
    return UserState.waiting_for_fullname


async def _persist_booking_state(
    user_id: int,
    state: FSMContext,
    *,
    next_state: State | None = None,
    **updates,
):
    if updates:
        await state.update_data(**updates)
    if next_state is not None:
        await state.set_state(next_state)

    data = await state.get_data()
    current_state = _state_value(next_state) or await state.get_state()
    await upsert_temporary_order(
        {
            "user_id": user_id,
            "current_state": current_state,
            "is_for_other": bool(data.get("is_for_other")),
            "selected_barber_locked": bool(data.get(LOCKED_BARBER_STATE_KEY)),
            "fullname": data.get("fullname"),
            "phonenumber": data.get("phonenumber"),
            "service_id": str(data["service_id"]) if data.get("service_id") is not None else None,
            "barber_id": str(data["barber_id"]) if data.get("barber_id") is not None else None,
            "date": data.get("date"),
            "time": data.get("time"),
        }
    )


async def _delete_temporary_order_safely(user_id: int):
    try:
        await delete_temporary_order(user_id)
    except Exception:
        logger.exception("Failed to delete temporary booking for user_id=%s", user_id)


async def _ask_phonenumber_from_callback(callback: CallbackQuery):
    await callback.message.answer(
        with_cancel_hint("📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:"),
        reply_markup=phone_request_keyboard,
    )


async def _show_booking_target_prompt(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(UserState.waiting_for_booking_target)
    text = with_cancel_hint("Kim uchun navbat olmoqchisiz?")
    markup = _booking_target_keyboard()
    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


async def _prompt_resume_booking(
    callback: CallbackQuery,
    state: FSMContext,
    entry_context: dict[str, str],
):
    await state.clear()
    await state.update_data(**{PENDING_BOOKING_ENTRY_KEY: entry_context})
    await state.set_state(UserState.waiting_for_resume_booking)
    text = with_cancel_hint(
        "Sizda yakunlanmagan navbat olish jarayoni mavjud.\n\nDavom ettirishni xohlaysizmi?"
    )
    keyboard = _booking_resume_keyboard()
    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _maybe_prompt_resume_booking(
    callback: CallbackQuery,
    state: FSMContext,
    entry_context: dict[str, str],
) -> bool:
    temp_order = await get_temporary_order(callback.from_user.id)
    if temp_order is None:
        return False

    await _prompt_resume_booking(callback, state, entry_context)
    await callback.answer("Yakunlanmagan booking topildi ✅")
    return True


def _booking_state_from_value(state_value: str | None) -> State | None:
    state_map = {
        UserState.waiting_for_fullname.state: UserState.waiting_for_fullname,
        UserState.waiting_for_phonenumber.state: UserState.waiting_for_phonenumber,
        UserState.waiting_for_service.state: UserState.waiting_for_service,
        UserState.waiting_for_barber.state: UserState.waiting_for_barber,
        UserState.waiting_for_date.state: UserState.waiting_for_date,
        UserState.waiting_for_time.state: UserState.waiting_for_time,
    }
    return state_map.get(state_value)


async def _infer_resume_state(user_id: int, temp_order) -> State:
    stored_state = _booking_state_from_value(getattr(temp_order, "current_state", None))
    if stored_state is not None:
        return stored_state

    if temp_order.date and temp_order.barber_id and temp_order.service_id:
        return UserState.waiting_for_time
    if temp_order.barber_id and temp_order.service_id:
        return UserState.waiting_for_date
    if temp_order.service_id:
        return UserState.waiting_for_barber
    if temp_order.phonenumber:
        return UserState.waiting_for_service
    if temp_order.fullname:
        return UserState.waiting_for_phonenumber
    if temp_order.is_for_other:
        return UserState.waiting_for_fullname

    return _resolve_initial_self_state(await _get_self_booking_seed(user_id))


async def _ensure_callback_state(
    callback: CallbackQuery,
    state: FSMContext,
    *allowed_states: State,
) -> bool:
    current_state = await state.get_state()
    allowed_state_values = {allowed_state.state for allowed_state in allowed_states}
    if current_state not in allowed_state_values:
        await callback.answer()
        return False
    return True


async def _finish_booking_cancel(message: Message, state: FSMContext):
    await _delete_temporary_order_safely(message.from_user.id)
    await state.clear()
    await message.answer(
        BOOKING_CANCELLED_TEXT,
        reply_markup=get_main_menu(),
    )


async def _show_locked_barber_unavailable_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    await _delete_temporary_order_safely(callback.from_user.id)
    await state.clear()
    await _render_catalog_callback(
        callback,
        SELECTED_BARBER_UNAVAILABLE_TEXT,
        booking_keyboards.back_button(),
    )
    await callback.answer()


async def _show_locked_barber_unavailable_message(
    message: Message,
    state: FSMContext,
):
    await _delete_temporary_order_safely(message.from_user.id)
    await state.clear()
    await message.answer(
        SELECTED_BARBER_UNAVAILABLE_TEXT,
        reply_markup=booking_keyboards.back_button(),
    )


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


def _date_to_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().strftime(ISO_DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(ISO_DATE_FORMAT)
    return str(value)


def _time_to_hm(value: time | datetime | str | None) -> str | None:
    normalized = _normalize_time_value(value)
    if normalized is None:
        return None
    return normalized.strftime(HM_TIME_FORMAT)


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


async def _fetch_services():
    return await list_services_ordered()


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
    return barber_full_name(barber) if barber else str(barber_id)


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
    price_lines = "\n".join(build_service_price_lines(service))
    caption = with_cancel_hint(
        f"💈 <b>Xizmatni tanlang</b>\n\n"
        f"{emoji} <b>{service.name}</b>\n"
        f"{price_lines}\n"
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
    price_lines = "\n".join(build_service_price_lines(service))
    caption = with_cancel_hint(
        f"💈 <b>Xizmatni tanlang</b>\n\n"
        f"{emoji} <b>{service.name}</b>\n"
        f"{price_lines}\n"
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
    caption, photo = await get_barber_card_content(
        barber,
        title="💈 <b>Barberni tanlang</b>",
        position=(index + 1, len(barbers)),
    )
    await _render_catalog_callback(
        callback,
        with_cancel_hint(caption),
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
    caption, photo = await get_barber_card_content(
        barber,
        title="💈 <b>Barberni tanlang</b>",
        position=(index + 1, len(barbers)),
    )
    await _send_catalog_message(
        message,
        with_cancel_hint(caption),
        _barber_nav_keyboard(index, len(barbers), service_id, str(barber.id)),
        photo,
    )
    return True


async def _edit_callback_message_text(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
):
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


async def _start_self_booking_flow(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    service_id: str | None = None,
    barber_id: str | None = None,
    locked_barber: bool = False,
) -> State:
    user_id = callback.from_user.id
    seed = await _get_self_booking_seed(user_id)
    initial_state = _resolve_initial_self_state(seed)

    await state.clear()
    await _persist_booking_state(
        user_id,
        state,
        next_state=initial_state,
        is_for_other=False,
        fullname=seed.get("fullname"),
        phonenumber=seed.get("phonenumber"),
        service_id=service_id,
        barber_id=barber_id,
        date=None,
        time=None,
        **{LOCKED_BARBER_STATE_KEY: locked_barber},
    )
    return initial_state


async def _start_booking_for_other(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _persist_booking_state(
        callback.from_user.id,
        state,
        next_state=UserState.waiting_for_fullname,
        is_for_other=True,
        fullname=None,
        phonenumber=None,
        service_id=None,
        barber_id=None,
        date=None,
        time=None,
        **{LOCKED_BARBER_STATE_KEY: False},
    )
    await _ask_fullname(callback)
    await callback.answer("Boshqa shaxs uchun ma'lumot kiriting ✅")


async def _start_booking_from_service_id(
    callback: CallbackQuery,
    state: FSMContext,
    service_id: str,
):
    initial_state = await _start_self_booking_flow(
        callback,
        state,
        service_id=service_id,
    )

    if initial_state == UserState.waiting_for_fullname:
        await _ask_fullname(callback)
        await callback.answer("Xizmat tanlandi, ro'yxatdan o'tamiz ✅")
        return

    if initial_state == UserState.waiting_for_phonenumber:
        await _ask_phonenumber_from_callback(callback)
        await callback.answer("Xizmat tanlandi, telefon raqamini kiriting ✅")
        return

    await _handle_service_selected(callback, state, service_id)


async def _start_booking_from_barber_id(
    callback: CallbackQuery,
    state: FSMContext,
    barber_id: str,
):
    initial_state = await _start_self_booking_flow(
        callback,
        state,
        barber_id=barber_id,
        locked_barber=True,
    )

    if initial_state == UserState.waiting_for_fullname:
        await _ask_fullname(callback)
        await callback.answer("Barber tanlandi, ro'yxatdan o'tamiz ✅")
        return

    if initial_state == UserState.waiting_for_phonenumber:
        await _ask_phonenumber_from_callback(callback)
        await callback.answer("Barber tanlandi, telefon raqamini kiriting ✅")
        return

    shown = await _show_service_page_callback(callback, index=0)
    if shown:
        await callback.answer("Barber tanlandi, xizmatni tanlang ✅")
    else:
        await callback.answer("Xizmatlar topilmadi", show_alert=True)


async def _restart_booking_from_entry_context(
    callback: CallbackQuery,
    state: FSMContext,
    entry_context: dict[str, str] | None,
):
    context = entry_context or _build_entry_context("root")
    kind = context.get("kind")

    if kind == "service" and context.get("service_id"):
        await _start_booking_from_service_id(callback, state, context["service_id"])
        return

    if kind == "barber" and context.get("barber_id"):
        await _start_booking_from_barber_id(callback, state, context["barber_id"])
        return

    await _show_booking_target_prompt(callback, state)
    await callback.answer()


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
    await _persist_booking_state(
        callback.from_user.id,
        state,
        next_state=UserState.waiting_for_date,
        service_id=service_id,
        barber_id=barber_id,
        date=None,
        time=None,
    )
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
    await callback.answer(answer_text)


async def _go_to_date_from_message(
    message: Message,
    state: FSMContext,
    service_id: str,
    barber_id: str,
):
    await _persist_booking_state(
        message.from_user.id,
        state,
        next_state=UserState.waiting_for_date,
        service_id=service_id,
        barber_id=barber_id,
        date=None,
        time=None,
    )
    await message.answer(
        with_cancel_hint("📅 Sana tanlang:"),
        reply_markup=await booking_keyboards.date_keyboard(service_id, barber_id),
    )


async def _show_time_selection_callback(
    callback: CallbackQuery,
    state: FSMContext,
    service_id: str,
    barber_id: str,
    date_str: str,
    *,
    answer_text: str,
):
    await _persist_booking_state(
        callback.from_user.id,
        state,
        service_id=service_id,
        barber_id=barber_id,
        date=date_str,
        time=None,
    )
    keyboard = await _build_time_keyboard(service_id, barber_id, date_str)

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
        await _edit_callback_message_text(
            callback,
            with_cancel_hint("❌ Kechirasiz, bu kunga barcha vaqtlar band."),
            back_markup,
        )
        await _persist_booking_state(
            callback.from_user.id,
            state,
            next_state=UserState.waiting_for_date,
            service_id=service_id,
            barber_id=barber_id,
            date=date_str,
            time=None,
        )
    else:
        await _edit_callback_message_text(
            callback,
            with_cancel_hint("⏰ Vaqt tanlang:"),
            keyboard,
        )
        await _persist_booking_state(
            callback.from_user.id,
            state,
            next_state=UserState.waiting_for_time,
            service_id=service_id,
            barber_id=barber_id,
            date=date_str,
            time=None,
        )

    await callback.answer(answer_text)


async def _show_time_selection_message(
    message: Message,
    state: FSMContext,
    service_id: str,
    barber_id: str,
    date_str: str,
):
    await _persist_booking_state(
        message.from_user.id,
        state,
        service_id=service_id,
        barber_id=barber_id,
        date=date_str,
        time=None,
    )
    keyboard = await _build_time_keyboard(service_id, barber_id, date_str)

    if keyboard is None:
        await _persist_booking_state(
            message.from_user.id,
            state,
            next_state=UserState.waiting_for_date,
            service_id=service_id,
            barber_id=barber_id,
            date=date_str,
            time=None,
        )
        await message.answer(with_cancel_hint("❌ Bu kunda bo'sh vaqt yo'q."))
        return

    await _persist_booking_state(
        message.from_user.id,
        state,
        next_state=UserState.waiting_for_time,
        service_id=service_id,
        barber_id=barber_id,
        date=date_str,
        time=None,
    )
    await message.answer(with_cancel_hint("⏰ Vaqtni tanlang:"), reply_markup=keyboard)


async def _render_booking_success(
    callback: CallbackQuery,
    *,
    fullname: str,
    phone: str,
    service_name: str,
    barber_name: str,
    date_str: str,
    time_str: str,
):
    text = (
        "✅ <b>Buyurtmangiz muvaffaqiyatli saqlandi!</b>\n\n"
        f"👤 <b>Ism:</b> {fullname}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"💈 <b>Xizmat:</b> {service_name}\n"
        f"👨‍💼 <b>Usta:</b> {barber_name}\n"
        f"📅 <b>Sana:</b> {date_str}\n"
        f"🕔 <b>Vaqt:</b> {time_str}"
    )
    await _edit_callback_message_text(callback, text)


async def _restore_temporary_order_to_state(
    temp_order,
    state: FSMContext,
    entry_context: dict[str, str] | None = None,
):
    payload = {
        "is_for_other": bool(temp_order.is_for_other),
        "fullname": temp_order.fullname,
        "phonenumber": temp_order.phonenumber,
        "service_id": temp_order.service_id,
        "barber_id": temp_order.barber_id,
        "date": _date_to_iso(temp_order.date),
        "time": _time_to_hm(temp_order.time),
        LOCKED_BARBER_STATE_KEY: bool(temp_order.selected_barber_locked),
    }
    if entry_context is not None:
        payload[PENDING_BOOKING_ENTRY_KEY] = entry_context

    await state.clear()
    await state.update_data(**payload)


async def _complete_booking_from_temporary_order(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    answer_text: str,
) -> bool:
    user_id = callback.from_user.id
    temp_order = await get_temporary_order(user_id)
    if temp_order is None:
        await callback.answer("Yakunlanmagan booking topilmadi", show_alert=True)
        return False

    date_str = _date_to_iso(temp_order.date)
    time_str = _time_to_hm(temp_order.time)
    if not (
        temp_order.service_id
        and temp_order.barber_id
        and date_str
        and time_str
        and temp_order.fullname
        and temp_order.phonenumber
    ):
        return False

    available_slots = await _calculate_available_slots(temp_order.service_id, temp_order.barber_id, date_str)
    if time_str not in available_slots:
        keyboard = await _build_time_keyboard(temp_order.service_id, temp_order.barber_id, date_str)
        if keyboard is None:
            await _persist_booking_state(
                user_id,
                state,
                next_state=UserState.waiting_for_date,
                is_for_other=bool(temp_order.is_for_other),
                fullname=temp_order.fullname,
                phonenumber=temp_order.phonenumber,
                service_id=temp_order.service_id,
                barber_id=temp_order.barber_id,
                date=date_str,
                time=None,
                **{LOCKED_BARBER_STATE_KEY: bool(temp_order.selected_barber_locked)},
            )
            await _edit_callback_message_text(
                callback,
                with_cancel_hint("⛔ Tanlangan vaqt endi mavjud emas.\n\nIltimos, boshqa sana tanlang:"),
                await booking_keyboards.date_keyboard(temp_order.service_id, temp_order.barber_id),
            )
        else:
            await _persist_booking_state(
                user_id,
                state,
                next_state=UserState.waiting_for_time,
                is_for_other=bool(temp_order.is_for_other),
                fullname=temp_order.fullname,
                phonenumber=temp_order.phonenumber,
                service_id=temp_order.service_id,
                barber_id=temp_order.barber_id,
                date=date_str,
                time=None,
                **{LOCKED_BARBER_STATE_KEY: bool(temp_order.selected_barber_locked)},
            )
            await _edit_callback_message_text(
                callback,
                with_cancel_hint("⛔ Tanlangan vaqt endi mavjud emas.\n\nIltimos, boshqa vaqt tanlang:"),
                keyboard,
            )
        await callback.answer("Avval tanlangan vaqt band bo'lib qolgan", show_alert=True)
        return False

    should_send_menu_updated = False
    existing_user = None
    if not temp_order.is_for_other:
        existing_user = await get_user(user_id)

    if not temp_order.is_for_other:
        saved_user = await save_user(
            {
                "tg_id": user_id,
                "fullname": temp_order.fullname,
                "phone": temp_order.phonenumber,
            }
        )
        if saved_user:
            should_send_menu_updated = existing_user is None

    created = await finalize_temporary_order(user_id)
    try:
        await notify_barber_realtime(callback.bot, created.id, int(created.barber_id))
    except Exception:
        logger.exception("notify_barber_realtime failed")

    await _render_booking_success(
        callback,
        fullname=created.fullname,
        phone=created.phonenumber,
        service_name=created.service_name,
        barber_name=created.barber_id_name,
        date_str=_date_to_iso(created.date) or date_str,
        time_str=_time_to_hm(created.time) or time_str,
    )

    await state.clear()
    await callback.answer(answer_text)
    if should_send_menu_updated:
        await callback.message.answer(
            "📱 Menyu yangilandi:",
            reply_markup=await get_dynamic_main_keyboard(user_id),
        )
    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu(),
    )
    return True


async def _resume_booking_from_temporary_order(callback: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    entry_context = state_data.get(PENDING_BOOKING_ENTRY_KEY)
    temp_order = await get_temporary_order(callback.from_user.id)
    if temp_order is None:
        await _restart_booking_from_entry_context(callback, state, entry_context)
        return

    await _restore_temporary_order_to_state(temp_order, state, entry_context)

    if is_temporary_order_complete(temp_order):
        await _complete_booking_from_temporary_order(
            callback,
            state,
            answer_text="Booking muvaffaqiyatli yakunlandi ✅",
        )
        return

    resume_state = await _infer_resume_state(callback.from_user.id, temp_order)
    user_id = callback.from_user.id

    if resume_state == UserState.waiting_for_fullname:
        await _persist_booking_state(user_id, state, next_state=resume_state)
        await _ask_fullname(callback)
        await callback.answer("Booking davom ettirildi ✅")
        return

    if resume_state == UserState.waiting_for_phonenumber:
        await _persist_booking_state(user_id, state, next_state=resume_state)
        await _ask_phonenumber_from_callback(callback)
        await callback.answer("Booking davom ettirildi ✅")
        return

    if resume_state == UserState.waiting_for_service:
        await _persist_booking_state(user_id, state, next_state=resume_state)
        shown = await _show_service_page_callback(callback, index=0)
        if shown:
            await callback.answer("Booking davom ettirildi ✅")
        else:
            await callback.answer("Xizmatlar topilmadi", show_alert=True)
        return

    if resume_state == UserState.waiting_for_barber:
        if not temp_order.service_id:
            await _persist_booking_state(user_id, state, next_state=UserState.waiting_for_service)
            shown = await _show_service_page_callback(callback, index=0)
            if shown:
                await callback.answer("Booking davom ettirildi ✅")
            else:
                await callback.answer("Xizmatlar topilmadi", show_alert=True)
            return

        await _persist_booking_state(
            user_id,
            state,
            next_state=resume_state,
            service_id=temp_order.service_id,
        )
        shown = await _show_barber_page_callback(callback, temp_order.service_id, index=0)
        if shown:
            await callback.answer("Booking davom ettirildi ✅")
        else:
            await callback.answer(NO_BARBER_FOR_SERVICE_TEXT, show_alert=True)
        return

    if resume_state == UserState.waiting_for_date:
        if not temp_order.service_id or not temp_order.barber_id:
            await _persist_booking_state(user_id, state, next_state=UserState.waiting_for_service)
            shown = await _show_service_page_callback(callback, index=0)
            if shown:
                await callback.answer("Booking davom ettirildi ✅")
            else:
                await callback.answer("Xizmatlar topilmadi", show_alert=True)
            return

        await _go_to_date_from_callback(
            callback,
            state,
            temp_order.service_id,
            temp_order.barber_id,
            "Booking davom ettirildi ✅",
        )
        return

    if not temp_order.service_id or not temp_order.barber_id:
        await _persist_booking_state(user_id, state, next_state=UserState.waiting_for_service)
        shown = await _show_service_page_callback(callback, index=0)
        if shown:
            await callback.answer("Booking davom ettirildi ✅")
        else:
            await callback.answer("Xizmatlar topilmadi", show_alert=True)
        return

    date_str = _date_to_iso(temp_order.date)
    if not date_str:
        await _go_to_date_from_callback(
            callback,
            state,
            temp_order.service_id,
            temp_order.barber_id,
            "Booking davom ettirildi ✅",
        )
        return

    await _show_time_selection_callback(
        callback,
        state,
        temp_order.service_id,
        temp_order.barber_id,
        date_str,
        answer_text="Booking davom ettirildi ✅",
    )


async def _handle_service_selected(callback: CallbackQuery, state: FSMContext, service_id: str):
    await _persist_booking_state(
        callback.from_user.id,
        state,
        service_id=service_id,
        date=None,
        time=None,
    )
    data = await state.get_data()
    barber_id = str(data["barber_id"]) if data.get("barber_id") is not None else None
    locked_barber = bool(data.get(LOCKED_BARBER_STATE_KEY))

    if barber_id:
        if await _is_barber_available_for_service(service_id, barber_id):
            await _go_to_date_from_callback(
                callback,
                state,
                service_id,
                barber_id,
                "Xizmat tanlandi ✅",
            )
            return

        if locked_barber:
            await _show_locked_barber_unavailable_callback(callback, state)
            return

        await _persist_booking_state(
            callback.from_user.id,
            state,
            next_state=UserState.waiting_for_barber,
            barber_id=None,
            date=None,
            time=None,
        )
        shown = await _show_barber_page_callback(callback, service_id, index=0)
        if shown:
            await callback.answer(SELECTED_BARBER_UNAVAILABLE_TEXT, show_alert=True)
        else:
            await callback.answer(NO_BARBER_FOR_SERVICE_TEXT, show_alert=True)
        return

    await _persist_booking_state(
        callback.from_user.id,
        state,
        next_state=UserState.waiting_for_barber,
        barber_id=barber_id,
        date=None,
        time=None,
    )
    shown = await _show_barber_page_callback(callback, service_id, index=0)
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
        await _persist_booking_state(
            callback.from_user.id,
            state,
            next_state=UserState.waiting_for_barber,
            barber_id=None,
            date=None,
            time=None,
        )
        shown = await _show_barber_page_callback(callback, resolved_service_id, index=0)
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
        UserState.waiting_for_resume_booking,
        UserState.waiting_for_booking_target,
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
    await _finish_booking_cancel(message, state)


async def cancel_booking_universal(message: types.Message, state: FSMContext):
    await _finish_booking_cancel(message, state)


async def start_booking(callback: CallbackQuery, state: FSMContext):
    if await _maybe_prompt_resume_booking(callback, state, _build_entry_context("root")):
        return

    await _show_booking_target_prompt(callback, state)
    await callback.answer()


async def _start_booking_for_me(callback: CallbackQuery, state: FSMContext):
    initial_state = await _start_self_booking_flow(callback, state)
    if initial_state == UserState.waiting_for_fullname:
        await _ask_fullname(callback)
        await callback.answer("Ro'yxatdan o'tishni boshlaymiz ✅")
        return

    if initial_state == UserState.waiting_for_phonenumber:
        await _ask_phonenumber_from_callback(callback)
        await callback.answer("Telefon raqamingizni kiriting ✅")
        return

    shown = await _show_service_page_callback(callback, index=0)
    if shown:
        await callback.answer("Navbat olish boshlandi ✅")
    else:
        await callback.answer("Xizmatlar topilmadi", show_alert=True)


@router.callback_query(F.data == BOOKING_FOR_ME_CB)
async def booking_for_me_callback(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(
        callback,
        state,
        UserState.waiting_for_booking_target,
    ):
        return
    await _start_booking_for_me(callback, state)


@router.callback_query(F.data == BOOKING_FOR_OTHER_CB)
async def booking_for_other_callback(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(
        callback,
        state,
        UserState.waiting_for_booking_target,
    ):
        return
    await _start_booking_for_other(callback, state)


@router.callback_query(F.data == BOOKING_RESUME_CONTINUE_CB)
async def booking_resume_continue_callback(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(
        callback,
        state,
        UserState.waiting_for_resume_booking,
    ):
        return
    await _resume_booking_from_temporary_order(callback, state)


@router.callback_query(F.data == BOOKING_RESUME_RESTART_CB)
async def booking_resume_restart_callback(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(
        callback,
        state,
        UserState.waiting_for_resume_booking,
    ):
        return

    entry_context = (await state.get_data()).get(PENDING_BOOKING_ENTRY_KEY)
    await _delete_temporary_order_safely(callback.from_user.id)
    await _restart_booking_from_entry_context(callback, state, entry_context)


async def start_booking_from_barber(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Noto'g'ri barber ma'lumoti", show_alert=True)
        return

    barber_id = parts[2].strip()
    if not barber_id.isdigit():
        await callback.answer("Noto'g'ri barber ma'lumoti", show_alert=True)
        return

    data = await state.get_data()
    current_state = await state.get_state()

    if current_state == UserState.waiting_for_barber.state and data.get("service_id"):
        await _handle_barber_selected(callback, state, str(data["service_id"]), barber_id)
        return

    if await _maybe_prompt_resume_booking(
        callback,
        state,
        _build_entry_context("barber", barber_id=barber_id),
    ):
        return

    await _start_booking_from_barber_id(callback, state, barber_id)


async def start_booking_from_service(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Noto'g'ri xizmat ma'lumoti", show_alert=True)
        return

    service_id = await _resolve_service_id(parts[2])
    if not service_id:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    if await _maybe_prompt_resume_booking(
        callback,
        state,
        _build_entry_context("service", service_id=service_id),
    ):
        return

    await _start_booking_from_service_id(callback, state, service_id)


async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip()

    if len(fullname.split()) < 2:
        await message.answer(
            with_cancel_hint(
                "❌ Iltimos, ism va familiyani to'liq kiriting (masalan: Aliyev Valijon)."
            )
        )
        return

    await _persist_booking_state(
        message.from_user.id,
        state,
        next_state=UserState.waiting_for_phonenumber,
        fullname=fullname,
    )
    await message.answer(
        with_cancel_hint("📱 Iltimos, telefon raqamingizni kiriting yoki tugma orqali yuboring:"),
        reply_markup=phone_request_keyboard,
    )


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
    await _persist_booking_state(
        message.from_user.id,
        state,
        fullname=fullname,
        phonenumber=phonenumber,
    )

    await message.answer(
        "📱 Raqamingiz qabul qilindi ✅",
        reply_markup=await get_dynamic_main_keyboard(message.from_user.id),
    )

    data = await state.get_data()
    service_id = str(data["service_id"]) if data.get("service_id") is not None else None
    barber_id = str(data["barber_id"]) if data.get("barber_id") is not None else None
    locked_barber = bool(data.get(LOCKED_BARBER_STATE_KEY))

    if service_id and barber_id:
        if await _is_barber_available_for_service(service_id, barber_id):
            await _go_to_date_from_message(message, state, service_id, barber_id)
            return

        if locked_barber:
            await _show_locked_barber_unavailable_message(message, state)
            return

        await _persist_booking_state(
            message.from_user.id,
            state,
            barber_id=None,
            date=None,
            time=None,
        )
        await message.answer(
            with_cancel_hint(
                f"{SELECTED_BARBER_UNAVAILABLE_TEXT}\n\nIltimos, boshqa barber tanlang."
            )
        )

    if service_id:
        await _persist_booking_state(
            message.from_user.id,
            state,
            next_state=UserState.waiting_for_barber,
            service_id=service_id,
            barber_id=None,
            date=None,
            time=None,
        )
        await _show_barber_page_message(message, service_id, index=0)
        return

    await _persist_booking_state(
        message.from_user.id,
        state,
        next_state=UserState.waiting_for_service,
        date=None,
        time=None,
    )
    await _show_service_page_message(message, index=0)


async def booking_service_nav(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_service):
        return

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
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_service):
        return

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
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_barber):
        return

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
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_barber):
        return

    parts = callback.data.split("_", 3)
    if len(parts) != 4:
        await callback.answer("Noto'g'ri barber", show_alert=True)
        return

    service_id = parts[2]
    barber_id = parts[3]
    await _handle_barber_selected(callback, state, service_id, barber_id)


async def book_step1(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_service):
        return

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
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_barber):
        return

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
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_date):
        return

    _, service_id, barber_id, date = callback.data.split("_")
    await _show_time_selection_callback(
        callback,
        state,
        service_id,
        barber_id,
        date,
        answer_text="Sana qabul qilindi ✅",
    )


@router.message(UserState.waiting_for_date)
async def book_step3_message(message: Message, state: FSMContext):
    date = parse_user_date(message.text.strip())

    if not date:
        await message.answer(
            with_cancel_hint("❌ Kechirasiz, biz faqat joriy oy ichidagi sanalarni qabul qilamiz.")
        )
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    barber_id = data.get("barber_id")
    if not service_id or not barber_id:
        await _persist_booking_state(
            message.from_user.id,
            state,
            next_state=UserState.waiting_for_service,
            date=None,
            time=None,
        )
        await _show_service_page_message(message, index=0)
        return

    await _show_time_selection_message(message, state, str(service_id), str(barber_id), date)


async def back_to_date(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(
        callback,
        state,
        UserState.waiting_for_date,
        UserState.waiting_for_time,
    ):
        return

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

    await _persist_booking_state(
        callback.from_user.id,
        state,
        next_state=UserState.waiting_for_date,
        service_id=service_id,
        barber_id=barber_id,
        date=None,
        time=None,
    )
    await callback.answer("🔙 Orqaga qaytildi")


@router.callback_query(F.data.startswith("confirm_"))
async def confirm(callback: types.CallbackQuery, state: FSMContext):
    if not await _ensure_callback_state(callback, state, UserState.waiting_for_time):
        return

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

    if not is_for_other:
        existing_user = await get_user(user_id)
        if existing_user:
            fullname = fullname or existing_user.fullname
            phone = phone or existing_user.phone

    fullname = fullname or "Noma'lum"
    phone = phone or "Noma'lum"

    await _persist_booking_state(
        user_id,
        state,
        next_state=UserState.waiting_for_time,
        is_for_other=is_for_other,
        fullname=fullname,
        phonenumber=phone,
        service_id=service_id,
        barber_id=barber_id,
        date=date_str,
        time=time_str,
        **{LOCKED_BARBER_STATE_KEY: bool(user_data.get(LOCKED_BARBER_STATE_KEY))},
    )

    await _complete_booking_from_temporary_order(
        callback,
        state,
        answer_text="Vaqt tanlandi ✅",
    )
