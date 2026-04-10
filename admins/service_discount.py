from datetime import date, datetime, time, timedelta
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sql.db_services import (
    DISCOUNT_SCOPE_ALL,
    DISCOUNT_SCOPE_SINGLE,
    SERVICE_DISCOUNT_TIMEZONE,
    bulk_set_service_discount,
    clear_all_service_discounts,
    clear_service_discount,
    format_service_discount_expiry,
    get_service_by_id,
    has_global_discount_on_all_services,
    list_discounted_services_ordered,
    list_services_ordered,
    set_service_discount,
)
from utils.discounts import (
    DiscountValidationError,
    build_bulk_discount_results,
    calculate_discount_details,
    format_discount_percent,
    normalize_discount_percent,
)
from utils.service_pricing import get_service_price_snapshot
from utils.states import AdminDiscountStates
from utils.validators import parse_future_date, parse_user_time
from .admin_buttons import ADMIN_DISCOUNT_MENU_CB, ADMIN_MAIN_MENU_BACK_CB
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

DISCOUNT_MENU_TITLE = "<b>🏷 Chegirma qo'yish</b>\n\nChegirma turini tanlang."
DISCOUNT_SCOPE_ALL_CB = "admin_discount_scope_all"
DISCOUNT_SCOPE_ONE_CB = "admin_discount_scope_one"
DISCOUNT_SCOPE_BACK_CB = "admin_discount_scope_back"
DISCOUNT_SERVICE_NAV_PREFIX = "admin_discount_service_nav"
DISCOUNT_SERVICE_PICK_PREFIX = "admin_discount_service_pick"
DISCOUNT_SERVICE_CANCEL_CB = "admin_discount_cancel_menu"
DISCOUNT_SERVICE_TITLE = "<b>🏷 Chegirma qo'yish</b>"

DISCOUNT_CANCEL_TITLE = "<b>🧽 Chegirmani bekor qilish</b>"
DISCOUNT_CANCEL_BACK_CB = "admin_discount_cancel_back"
DISCOUNT_CANCEL_ALL_CONFIRM_CB = "admin_discount_cancel_all_confirm"
DISCOUNT_CANCEL_NAV_PREFIX = "admin_discount_cancel_nav"
DISCOUNT_CANCEL_PICK_PREFIX = "admin_discount_cancel_pick"

DISCOUNT_CONFIRM_APPLY_CB = "admin_discount_confirm_apply"
DISCOUNT_CONFIRM_REJECT_CB = "admin_discount_confirm_reject"
DISCOUNT_END_DATE_PREFIX = "admin_discount_end_date"
DISCOUNT_END_TIME_PREFIX = "admin_discount_end_time"
DISCOUNT_END_TIME_BACK_CB = "admin_discount_end_time_back"

DISCOUNT_DATE_FORMAT = "%Y-%m-%d"
DISCOUNT_TIME_FORMAT = "%H:%M"
DISCOUNT_TIME_BUTTONS_PER_ROW = 2
DISCOUNT_DATE_BUTTON_COUNT = 7
DISCOUNT_TIME_STEP_MINUTES = 60

PENDING_SCOPE_KEY = "pending_discount_scope"
PENDING_PERCENT_KEY = "pending_discount_percent"
PENDING_END_DATE_KEY = "pending_discount_end_date"

UZ_WEEKDAYS = (
    "Dushanba",
    "Seshanba",
    "Chorshanba",
    "Payshanba",
    "Juma",
    "Shanba",
    "Yakshanba",
)
UZ_MONTHS = (
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
)


def _discount_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Barcha xizmatlarga", callback_data=DISCOUNT_SCOPE_ALL_CB)],
            [InlineKeyboardButton(text="🎯 Alohida xizmatga", callback_data=DISCOUNT_SCOPE_ONE_CB)],
            [InlineKeyboardButton(text="🧽 Chegirmani bekor qilish", callback_data=DISCOUNT_SERVICE_CANCEL_CB)],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=ADMIN_MAIN_MENU_BACK_CB)],
        ]
    )


def _discount_service_keyboard(index: int, service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{DISCOUNT_SERVICE_NAV_PREFIX}:prev:{index}",
                ),
                InlineKeyboardButton(
                    text="Keyingi ➡️",
                    callback_data=f"{DISCOUNT_SERVICE_NAV_PREFIX}:next:{index}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Tanlash",
                    callback_data=f"{DISCOUNT_SERVICE_PICK_PREFIX}:{service_id}:{index}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=DISCOUNT_SCOPE_BACK_CB)],
        ]
    )


def _discount_cancel_all_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚨 Ha, barcha chegirmalarni olib tashlash",
                    callback_data=DISCOUNT_CANCEL_ALL_CONFIRM_CB,
                )
            ],
            [InlineKeyboardButton(text="🛡 Hozircha qoldirish", callback_data=DISCOUNT_CANCEL_BACK_CB)],
        ]
    )


def _discount_cancel_service_keyboard(
    index: int,
    service_id: int,
    *,
    total: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if total > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{DISCOUNT_CANCEL_NAV_PREFIX}:prev:{index}",
                ),
                InlineKeyboardButton(
                    text="Keyingi ➡️",
                    callback_data=f"{DISCOUNT_CANCEL_NAV_PREFIX}:next:{index}",
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🧽 Shu xizmatdagi chegirmani yechish",
                callback_data=f"{DISCOUNT_CANCEL_PICK_PREFIX}:{service_id}:{index}",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🔙 Chegirma menyusi", callback_data=DISCOUNT_CANCEL_BACK_CB)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _discount_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=DISCOUNT_CONFIRM_APPLY_CB)],
            [
                InlineKeyboardButton(
                    text="❌ Tasdiqlanmaslik",
                    callback_data=DISCOUNT_CONFIRM_REJECT_CB,
                )
            ],
        ]
    )


def _format_discount_date_label(target_date: date) -> str:
    weekday = UZ_WEEKDAYS[target_date.weekday()]
    month = UZ_MONTHS[target_date.month - 1]
    return f"{target_date.day:02d} {month} • {weekday}"


def _format_discount_date_value(value: str | date) -> str:
    target_date = (
        datetime.strptime(value, DISCOUNT_DATE_FORMAT).date()
        if isinstance(value, str)
        else value
    )
    return f"{target_date.strftime('%d.%m.%Y')} ({UZ_WEEKDAYS[target_date.weekday()]})"


def _discount_date_keyboard() -> InlineKeyboardMarkup:
    local_today = _get_discount_now().date()
    rows = []
    for offset in range(DISCOUNT_DATE_BUTTON_COUNT):
        target_date = local_today + timedelta(days=offset)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📅 {_format_discount_date_label(target_date)}",
                    callback_data=(
                        f"{DISCOUNT_END_DATE_PREFIX}:{target_date.strftime(DISCOUNT_DATE_FORMAT)}"
                    ),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_time_button_values(target_date: date) -> list[str]:
    local_now = _get_discount_now()
    current = datetime.combine(
        target_date,
        time(hour=0, minute=0),
        tzinfo=SERVICE_DISCOUNT_TIMEZONE,
    )
    end_of_day = current + timedelta(days=1)
    values: list[str] = []
    while current < end_of_day:
        if current > local_now:
            values.append(current.strftime(DISCOUNT_TIME_FORMAT))
        current += timedelta(minutes=DISCOUNT_TIME_STEP_MINUTES)
    return values


def _discount_time_keyboard(target_date: date) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for index, value in enumerate(_build_time_button_values(target_date), start=1):
        current_row.append(
            InlineKeyboardButton(
                text=value,
                callback_data=f"{DISCOUNT_END_TIME_PREFIX}:{value}",
            )
        )
        if index % DISCOUNT_TIME_BUTTONS_PER_ROW == 0:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Sanani qayta tanlash",
                callback_data=DISCOUNT_END_TIME_BACK_CB,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_cancel_all_warning_text(total_services: int) -> str:
    return (
        "⚠️ <b>Barcha xizmatlarda faol chegirma bor.</b>\n\n"
        f"🧾 Chegirmadagi xizmatlar soni: <b>{total_services}</b>\n"
        "Tasdiqlasangiz, barcha xizmatlardagi chegirma foizi va chegirmali narx yozuvlari birdaniga olib tashlanadi.\n"
        "Asl narxlar o'zgarmaydi.\n\n"
        "Davom etishni tasdiqlang."
    )


def _single_service_discount_prompt(service) -> str:
    snapshot = get_service_price_snapshot(service)
    lines = [
        "🏷 <b>Tanlangan xizmat uchun chegirma foizini yuboring.</b>",
        "",
        f"💈 Xizmat: <b>{escape(service.name)}</b>",
        f"💵 Asl narx: <b>{format_price(snapshot.base_price)}</b> so'm",
    ]
    if snapshot.has_discount:
        percent_text = format_discount_percent(snapshot.discount_percent)
        lines.extend(
            [
                f"📌 Joriy chegirma: <b>{percent_text}%</b>",
                f"💸 Amaldagi chegirmali narx: <b>{format_price(snapshot.current_price)}</b> so'm",
                "",
                "Yangi foiz yuborsangiz, mavjud chegirma yangilanadi.",
            ]
        )
    lines.extend(
        [
            "",
            "Tasdiqlashdan keyin tugash sana va vaqtini alohida tanlaysiz.",
            "Qo'llab-quvvatlanadigan format: <code>10</code> yoki <code>12.5</code>",
        ]
    )
    return with_cancel_hint("\n".join(lines))


def _all_services_discount_prompt() -> str:
    return with_cancel_hint(
        "📦 <b>Barcha xizmatlar uchun chegirma foizini yuboring.</b>\n\n"
        "Tasdiqlashdan keyin tugash sana va vaqtini alohida tanlaysiz.\n"
        "Qo'llab-quvvatlanadigan format: <code>10</code> yoki <code>12.5</code>\n"
        "Chegirma xizmatlarning asl narxlari asosida hisoblanadi."
    )


def _build_single_discount_confirmation(service, discount_result) -> str:
    percent_text = format_discount_percent(discount_result.discount_percent)
    snapshot = get_service_price_snapshot(service)
    lines = [
        "🧾 <b>Chegirma ma'lumotlarini tasdiqlang</b>",
        "",
        f"💈 Xizmat: <b>{escape(service.name)}</b>",
        f"💵 Asl narx: <b>{format_price(discount_result.old_price)}</b> so'm",
        f"🏷 Chegirma: <b>{percent_text}%</b>",
        f"💸 Yangi narx: <b>{format_price(discount_result.new_price)}</b> so'm",
    ]
    if snapshot.has_discount:
        current_percent = format_discount_percent(snapshot.discount_percent)
        lines.extend(
            [
                f"📌 Joriy chegirma: <b>{current_percent}%</b>",
                f"📍 Joriy chegirmali narx: <b>{format_price(snapshot.current_price)}</b> so'm",
            ]
        )
    lines.extend(["", "Tasdiqlasangiz, keyingi bosqichda tugash sana va vaqtini tanlaysiz."])
    return "\n".join(lines)


def _build_all_discount_confirmation(results, percent) -> str:
    percent_text = format_discount_percent(percent)
    changed_count = sum(1 for item in results if item.old_price != item.new_price)
    return (
        "🧾 <b>Barcha xizmatlar uchun chegirma ma'lumotlarini tasdiqlang</b>\n\n"
        f"📦 Xizmatlar soni: <b>{len(results)}</b>\n"
        f"🏷 Chegirma: <b>{percent_text}%</b>\n"
        f"📉 Narxi o'zgaradigan xizmatlar: <b>{changed_count}</b>\n\n"
        "Tasdiqlasangiz, keyingi bosqichda tugash sana va vaqtini tanlaysiz."
    )


def _build_end_date_prompt() -> str:
    return with_cancel_hint(
        "📅 <b>Chegirma tugash sanasini tanlang</b>\n\n"
        "Avval pastdagi tugmalardan birini tanlang.\n"
        "Yoki sanani qo'lda yuboring: <code>2026-04-15</code>, <code>15.04.2026</code>, <code>15 aprel</code>."
    )


def _build_end_time_prompt(target_date: str, *, has_quick_buttons: bool) -> str:
    lines = [
        "⏰ <b>Chegirma tugash vaqtini tanlang</b>",
        "",
        f"📅 Tanlangan sana: <b>{_format_discount_date_value(target_date)}</b>",
    ]
    if has_quick_buttons:
        lines.append("Avval tugmalardan birini bosing.")
    else:
        lines.append(
            "⚠️ Standart vaqt tugmalari qolmadi. Vaqtni qo'lda kiriting yoki sanani qayta tanlang."
        )
    lines.append("Yoki vaqtni qo'lda yuboring: <code>18:30</code>.")
    return with_cancel_hint("\n".join(lines))


def _build_single_discount_success(updated_service, discount_result, expiry_text: str) -> str:
    percent_text = format_discount_percent(discount_result.discount_percent)
    return (
        "✅ <b>Chegirma muvaffaqiyatli tasdiqlandi.</b>\n\n"
        f"💈 Xizmat: <b>{escape(updated_service.name)}</b>\n"
        f"💵 Asl narx: <b>{format_price(discount_result.old_price)}</b> so'm\n"
        f"🏷 Chegirma: <b>{percent_text}%</b>\n"
        f"💸 Chegirmali narx: <b>{format_price(discount_result.new_price)}</b> so'm\n"
        f"📅 Tugash muddati: <b>{expiry_text}</b>\n\n"
        "🛡 Ushbu chegirma ko'rsatilgan muddatgacha faol bo'ladi."
    )


def _build_all_discount_success(*, results, updated_count: int, percent, expiry_text: str) -> str:
    percent_text = format_discount_percent(percent)
    changed_count = sum(1 for item in results if item.old_price != item.new_price)
    return (
        "✅ <b>Barcha xizmatlar uchun chegirma muvaffaqiyatli tasdiqlandi.</b>\n\n"
        f"📦 Jami xizmatlar: <b>{len(results)}</b>\n"
        f"🏷 Qo'llangan foiz: <b>{percent_text}%</b>\n"
        f"🛠 Yangilangan yozuvlar: <b>{updated_count}</b>\n"
        f"📉 Narxi o'zgargan xizmatlar: <b>{changed_count}</b>\n"
        f"📅 Tugash muddati: <b>{expiry_text}</b>\n\n"
        "🛡 Chegirma ko'rsatilgan muddatgacha faol bo'ladi."
    )


def _parse_discount_service_nav(data: str) -> tuple[str, int] | None:
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


def _parse_discount_service_pick(data: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 3:
        return None
    try:
        service_id = int(parts[1])
        index = int(parts[2])
    except ValueError:
        return None
    return service_id, index


def _parse_end_date_callback(data: str) -> str | None:
    parts = data.split(":", 1)
    if len(parts) != 2 or parts[0] != DISCOUNT_END_DATE_PREFIX:
        return None
    try:
        return datetime.strptime(parts[1], DISCOUNT_DATE_FORMAT).strftime(DISCOUNT_DATE_FORMAT)
    except ValueError:
        return None


def _parse_end_time_callback(data: str) -> str | None:
    parts = data.split(":", 1)
    if len(parts) != 2 or parts[0] != DISCOUNT_END_TIME_PREFIX:
        return None
    try:
        parsed_time = datetime.strptime(parts[1], DISCOUNT_TIME_FORMAT).time()
    except ValueError:
        return None
    return parsed_time.strftime(DISCOUNT_TIME_FORMAT)


def _validation_message(error: DiscountValidationError) -> str:
    return with_cancel_hint(f"❌ {escape(str(error))}")


def _get_discount_now() -> datetime:
    return datetime.now(SERVICE_DISCOUNT_TIMEZONE).replace(second=0, microsecond=0)


def _build_expiry_datetime(end_date_text: str, end_time_text: str) -> datetime:
    end_date = datetime.strptime(end_date_text, DISCOUNT_DATE_FORMAT).date()
    end_time_value = datetime.strptime(end_time_text, DISCOUNT_TIME_FORMAT).time()
    return datetime.combine(end_date, end_time_value, tzinfo=SERVICE_DISCOUNT_TIMEZONE)


async def _ensure_discount_callback_state(
    callback: types.CallbackQuery,
    state: FSMContext,
    *allowed_states: State,
) -> bool:
    current_state = await state.get_state()
    allowed_values = {allowed_state.state for allowed_state in allowed_states}
    if current_state not in allowed_values:
        await callback.answer()
        return False
    return True


async def _show_discount_menu(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    text = notice or DISCOUNT_MENU_TITLE
    return await show_service_card(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        service=None,
        text=text,
        reply_markup=_discount_menu_keyboard(),
    )


async def _show_discount_service_page(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    index: int = 0,
    notice: str | None = None,
) -> tuple[int, int, int | None]:
    services = await list_services_ordered()
    if not services:
        text = render_empty_services_text(
            title=DISCOUNT_SERVICE_TITLE,
            description="⚠️ Chegirma qo'yish uchun xizmatlar topilmadi.",
        )
        shown_message_id = await show_service_card(
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            service=None,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Orqaga", callback_data=DISCOUNT_SCOPE_BACK_CB)]
                ]
            ),
        )
        return shown_message_id, 0, None

    normalized_index = index % len(services)
    service = services[normalized_index]
    text = render_service_text(
        service,
        title=DISCOUNT_SERVICE_TITLE,
        index=normalized_index,
        total=len(services),
        extra_lines=(
            "Tanlangan xizmatga chegirma qo'yish uchun <b>✅ Tanlash</b> tugmasini bosing.",
        ),
    )
    if notice:
        text = f"{notice}\n\n{text}"

    shown_message_id = await show_service_card(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        service=service,
        text=text,
        reply_markup=_discount_service_keyboard(normalized_index, int(service.id)),
    )
    return shown_message_id, normalized_index, int(service.id)


async def _show_discount_cancel_service_page(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    index: int = 0,
    notice: str | None = None,
) -> tuple[int, int, int | None]:
    discounted_services = await list_discounted_services_ordered()
    if not discounted_services:
        shown_message_id = await _show_discount_menu(
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            notice="ℹ️ Bekor qilinadigan faol chegirma topilmadi.",
        )
        return shown_message_id, 0, None

    normalized_index = index % len(discounted_services)
    service = discounted_services[normalized_index]
    text = render_service_text(
        service,
        title=DISCOUNT_CANCEL_TITLE,
        index=normalized_index,
        total=len(discounted_services),
        extra_lines=(
            f"🧾 Faol chegirma qo'yilgan xizmatlar: <b>{len(discounted_services)}</b>",
            "Pastdagi tugma aynan shu kartadagi xizmat chegirmasini olib tashlaydi.",
        ),
    )
    if notice:
        text = f"{notice}\n\n{text}"

    shown_message_id = await show_service_card(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        service=service,
        text=text,
        reply_markup=_discount_cancel_service_keyboard(
            normalized_index,
            int(service.id),
            total=len(discounted_services),
        ),
    )
    return shown_message_id, normalized_index, int(service.id)


async def _restore_discount_panel(
    *,
    bot,
    chat_id: int,
    panel_message_id: int | None,
    selected_service_id: int | None,
    selected_service_index: int,
    notice: str | None = None,
) -> dict:
    if selected_service_id:
        shown_message_id, page_index, current_service_id = await _show_discount_service_page(
            bot=bot,
            chat_id=chat_id,
            message_id=panel_message_id,
            index=selected_service_index,
            notice=notice,
        )
        return {
            "panel_message_id": shown_message_id,
            "selected_service_index": page_index,
            "selected_service_id": current_service_id,
        }

    shown_message_id = await _show_discount_menu(
        bot=bot,
        chat_id=chat_id,
        message_id=panel_message_id,
        notice=notice,
    )
    return {
        "panel_message_id": shown_message_id,
        "selected_service_index": 0,
        "selected_service_id": None,
    }


async def _send_end_time_prompt(message: types.Message, end_date_text: str) -> None:
    target_date = datetime.strptime(end_date_text, DISCOUNT_DATE_FORMAT).date()
    keyboard = _discount_time_keyboard(target_date)
    has_quick_buttons = any(
        button.callback_data and button.callback_data.startswith(f"{DISCOUNT_END_TIME_PREFIX}:")
        for row in keyboard.inline_keyboard
        for button in row
    )
    await message.answer(
        _build_end_time_prompt(end_date_text, has_quick_buttons=has_quick_buttons),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _prompt_for_percent_again(
    message: types.Message,
    state: FSMContext,
    *,
    notice: str,
) -> bool:
    data = await state.get_data()
    scope = data.get(PENDING_SCOPE_KEY)
    if scope == DISCOUNT_SCOPE_ALL:
        await state.update_data(
            pending_discount_percent=None,
            pending_discount_end_date=None,
        )
        await state.set_state(AdminDiscountStates.waiting_for_all_services_percent)
        await message.answer(
            f"{notice}\n\n{_all_services_discount_prompt()}",
            parse_mode="HTML",
        )
        return True

    service_id = data.get("selected_service_id")
    if not service_id:
        return False

    service = await get_service_by_id(int(service_id))
    if service is None:
        return False

    await state.update_data(
        pending_discount_percent=None,
        pending_discount_end_date=None,
    )
    await state.set_state(AdminDiscountStates.waiting_for_selected_service_percent)
    await message.answer(
        f"{notice}\n\n{_single_service_discount_prompt(service)}",
        parse_mode="HTML",
    )
    return True


async def _finish_discount_flow(
    message: types.Message,
    state: FSMContext,
    *,
    end_time_text: str,
) -> None:
    data = await state.get_data()
    raw_percent = data.get(PENDING_PERCENT_KEY)
    end_date_text = data.get(PENDING_END_DATE_KEY)
    scope = data.get(PENDING_SCOPE_KEY)
    panel_message_id = data.get("panel_message_id")
    selected_service_id = data.get("selected_service_id")
    selected_service_index = int(data.get("selected_service_index", 0))

    if not raw_percent or not end_date_text or scope not in {DISCOUNT_SCOPE_ALL, DISCOUNT_SCOPE_SINGLE}:
        restored = await _restore_discount_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            panel_message_id=panel_message_id,
            selected_service_id=selected_service_id,
            selected_service_index=selected_service_index,
            notice="⚠️ Jarayon buzildi. Chegirmani qaytadan kiriting.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(**restored)
        return

    try:
        percent = normalize_discount_percent(raw_percent)
    except DiscountValidationError as exc:
        await message.answer(_validation_message(exc), parse_mode="HTML")
        return

    try:
        end_at_local = _build_expiry_datetime(end_date_text, end_time_text)
    except ValueError:
        await message.answer(
            with_cancel_hint(
                "❌ Vaqt formati noto'g'ri. <code>18:30</code> ko'rinishida yuboring."
            ),
            parse_mode="HTML",
        )
        return

    if end_at_local <= _get_discount_now():
        await message.answer(
            with_cancel_hint(
                "❌ Tugash vaqti hozirgi vaqtdan keyin bo'lishi kerak. Iltimos, boshqa vaqt kiriting."
            ),
            parse_mode="HTML",
        )
        return

    end_at = end_at_local.date()
    end_time_value = end_at_local.time().replace(second=0, microsecond=0, tzinfo=None)
    expiry_text = format_service_discount_expiry(end_at, end_time_value)

    if scope == DISCOUNT_SCOPE_ALL:
        services = await list_services_ordered()
        if not services:
            restored = await _restore_discount_panel(
                bot=message.bot,
                chat_id=message.chat.id,
                panel_message_id=panel_message_id,
                selected_service_id=None,
                selected_service_index=0,
                notice="⚠️ Xizmatlar topilmadi.",
            )
            await state.clear()
            await state.set_state(AdminDiscountStates.selecting_discount_scope)
            await state.update_data(**restored)
            return

        results = build_bulk_discount_results(
            ((int(service.id), int(service.price)) for service in services),
            percent,
        )
        updated_count = await bulk_set_service_discount(
            (int(service.id) for service in services),
            percent,
            applied_scope=DISCOUNT_SCOPE_ALL,
            end_at=end_at,
            end_time=end_time_value,
        )
        success_text = _build_all_discount_success(
            results=results,
            updated_count=updated_count,
            percent=percent,
            expiry_text=expiry_text,
        )
    else:
        if not selected_service_id:
            restored = await _restore_discount_panel(
                bot=message.bot,
                chat_id=message.chat.id,
                panel_message_id=panel_message_id,
                selected_service_id=None,
                selected_service_index=0,
                notice="⚠️ Jarayon buzildi. Qayta urinib ko'ring.",
            )
            await state.clear()
            await state.set_state(AdminDiscountStates.selecting_discount_scope)
            await state.update_data(**restored)
            return

        service = await get_service_by_id(int(selected_service_id))
        if service is None:
            restored = await _restore_discount_panel(
                bot=message.bot,
                chat_id=message.chat.id,
                panel_message_id=panel_message_id,
                selected_service_id=None,
                selected_service_index=0,
                notice="⚠️ Tanlangan xizmat topilmadi.",
            )
            await state.clear()
            await state.set_state(AdminDiscountStates.selecting_discount_scope)
            await state.update_data(**restored)
            return

        discount_result = calculate_discount_details(int(service.price), percent)
        updated_service = await set_service_discount(
            int(service.id),
            percent,
            applied_scope=DISCOUNT_SCOPE_SINGLE,
            end_at=end_at,
            end_time=end_time_value,
        )
        if updated_service is None:
            restored = await _restore_discount_panel(
                bot=message.bot,
                chat_id=message.chat.id,
                panel_message_id=panel_message_id,
                selected_service_id=selected_service_id,
                selected_service_index=selected_service_index,
                notice="⚠️ Chegirmani saqlab bo'lmadi. Qayta urinib ko'ring.",
            )
            await state.clear()
            await state.set_state(AdminDiscountStates.selecting_discount_scope)
            await state.update_data(**restored)
            return

        success_text = _build_single_discount_success(
            updated_service,
            discount_result,
            expiry_text,
        )

    await message.answer(success_text, parse_mode="HTML")
    restored = await _restore_discount_panel(
        bot=message.bot,
        chat_id=message.chat.id,
        panel_message_id=panel_message_id,
        selected_service_id=(
            selected_service_id if scope == DISCOUNT_SCOPE_SINGLE else None
        ),
        selected_service_index=(
            selected_service_index if scope == DISCOUNT_SCOPE_SINGLE else 0
        ),
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(**restored)


@router.callback_query(F.data == ADMIN_MAIN_MENU_BACK_CB)
async def back_to_admin_main_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    await show_admin_main_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await callback.answer()


@router.callback_query(F.data == ADMIN_DISCOUNT_MENU_CB)
async def open_discount_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    shown_message_id = await _show_discount_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(panel_message_id=shown_message_id)
    await callback.answer()


@router.callback_query(F.data == DISCOUNT_SCOPE_BACK_CB)
@router.callback_query(F.data == DISCOUNT_CANCEL_BACK_CB)
async def back_to_discount_scope(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    shown_message_id = await _show_discount_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(panel_message_id=shown_message_id)
    await callback.answer()


@router.callback_query(F.data == DISCOUNT_SCOPE_ONE_CB)
async def open_single_service_discount(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    shown_message_id, page_index, service_id = await _show_discount_service_page(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=0,
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=service_id,
    )
    await callback.answer()


@router.callback_query(F.data == DISCOUNT_SCOPE_ALL_CB)
async def ask_discount_for_all_services(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    await state.set_state(AdminDiscountStates.waiting_for_all_services_percent)
    await state.update_data(
        panel_message_id=callback.message.message_id,
        selected_service_id=None,
        selected_service_index=0,
        pending_discount_scope=DISCOUNT_SCOPE_ALL,
        pending_discount_percent=None,
        pending_discount_end_date=None,
    )
    await callback.message.answer(
        _all_services_discount_prompt(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == DISCOUNT_SERVICE_CANCEL_CB)
async def open_discount_cancel_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    discounted_services = await list_discounted_services_ordered()
    if not discounted_services:
        shown_message_id = await _show_discount_menu(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice="ℹ️ Bekor qilinadigan faol chegirma topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        await callback.answer("Faol chegirma topilmadi.", show_alert=True)
        return

    if await has_global_discount_on_all_services():
        shown_message_id = await show_service_card(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            service=None,
            text=_build_cancel_all_warning_text(len(discounted_services)),
            reply_markup=_discount_cancel_all_keyboard(),
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        await callback.answer()
        return

    shown_message_id, page_index, service_id = await _show_discount_cancel_service_page(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=0,
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=service_id,
    )
    await callback.answer()


@router.callback_query(F.data == DISCOUNT_CANCEL_ALL_CONFIRM_CB)
async def confirm_cancel_all_discounts(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    removed_count = await clear_all_service_discounts()
    notice = (
        "✅ <b>Barcha chegirmalar bekor qilindi.</b>\n\n"
        f"Olib tashlangan yozuvlar: <b>{removed_count}</b>\n"
        "Asl xizmat narxlari saqlab qolindi."
    )
    shown_message_id = await _show_discount_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        notice=notice,
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(panel_message_id=shown_message_id)
    await callback.answer("Barcha chegirmalar bekor qilindi.")


@router.callback_query(F.data.startswith(f"{DISCOUNT_SERVICE_NAV_PREFIX}:"))
async def navigate_discount_services(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_discount_service_nav(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    action, index = parsed
    services = await list_services_ordered()
    if not services:
        shown_message_id = await _show_discount_menu(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice="⚠️ Xizmatlar topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        await callback.answer("Xizmatlar topilmadi.", show_alert=True)
        return

    index = (index + 1) % len(services) if action == "next" else (index - 1) % len(services)
    shown_message_id, page_index, service_id = await _show_discount_service_page(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=index,
    )
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=service_id,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{DISCOUNT_CANCEL_NAV_PREFIX}:"))
async def navigate_discount_cancel_services(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_discount_service_nav(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    action, index = parsed
    discounted_services = await list_discounted_services_ordered()
    if not discounted_services:
        shown_message_id = await _show_discount_menu(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice="ℹ️ Bekor qilinadigan faol chegirma topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        await callback.answer("Faol chegirma topilmadi.", show_alert=True)
        return

    index = (
        (index + 1) % len(discounted_services)
        if action == "next"
        else (index - 1) % len(discounted_services)
    )
    shown_message_id, page_index, service_id = await _show_discount_cancel_service_page(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=index,
    )
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=service_id,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{DISCOUNT_SERVICE_PICK_PREFIX}:"))
async def ask_single_service_discount_percent(
    callback: types.CallbackQuery,
    state: FSMContext,
) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_discount_service_pick(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    service = await get_service_by_id(service_id)
    if service is None:
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        await _show_discount_service_page(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            index=index,
            notice="⚠️ Tanlangan xizmat topilmadi.",
        )
        return

    await state.clear()
    await state.set_state(AdminDiscountStates.waiting_for_selected_service_percent)
    await state.update_data(
        panel_message_id=callback.message.message_id,
        selected_service_id=int(service.id),
        selected_service_index=index,
        pending_discount_scope=DISCOUNT_SCOPE_SINGLE,
        pending_discount_percent=None,
        pending_discount_end_date=None,
    )
    await callback.message.answer(
        _single_service_discount_prompt(service),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{DISCOUNT_CANCEL_PICK_PREFIX}:"))
async def cancel_single_service_discount(
    callback: types.CallbackQuery,
    state: FSMContext,
) -> None:
    if not await ensure_admin_callback(callback):
        return

    parsed = _parse_discount_service_pick(callback.data or "")
    if parsed is None:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    service_id, index = parsed
    service = await get_service_by_id(service_id)
    if service is None:
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        shown_message_id = await _show_discount_menu(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice="⚠️ Tanlangan xizmat topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        return

    removed = await clear_service_discount(int(service_id))
    if not removed:
        await callback.answer("Bu xizmatda faol chegirma topilmadi.", show_alert=True)
        return

    remaining_discounted_services = await list_discounted_services_ordered()
    if not remaining_discounted_services:
        shown_message_id = await _show_discount_menu(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            notice=(
                "✅ <b>Chegirma bekor qilindi.</b>\n\n"
                f"💈 Xizmat: <b>{escape(service.name)}</b>\n"
                "Faol chegirmalar qolmadi."
            ),
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(panel_message_id=shown_message_id)
        await callback.answer("Chegirma bekor qilindi.")
        return

    next_index = min(index, len(remaining_discounted_services) - 1)
    shown_message_id, page_index, current_service_id = await _show_discount_cancel_service_page(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        index=next_index,
        notice=(
            "✅ <b>Chegirma olib tashlandi.</b>\n\n"
            f"💈 Xizmat: <b>{escape(service.name)}</b>\n"
            "Qolgan chegirmalarni ham shu bo'limdan boshqarishingiz mumkin."
        ),
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=current_service_id,
    )
    await callback.answer("Chegirma bekor qilindi.")


@router.callback_query(F.data == DISCOUNT_CONFIRM_APPLY_CB)
async def confirm_discount_preview(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return
    if not await _ensure_discount_callback_state(
        callback,
        state,
        AdminDiscountStates.waiting_for_discount_confirmation,
    ):
        return

    await state.set_state(AdminDiscountStates.waiting_for_discount_end_date)
    await callback.message.answer(
        _build_end_date_prompt(),
        parse_mode="HTML",
        reply_markup=_discount_date_keyboard(),
    )
    await callback.answer("Chegirma tasdiqlandi. Endi tugash sanasini tanlang.")


@router.callback_query(F.data == DISCOUNT_CONFIRM_REJECT_CB)
async def reject_discount_preview(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return
    if not await _ensure_discount_callback_state(
        callback,
        state,
        AdminDiscountStates.waiting_for_discount_confirmation,
    ):
        return

    repeated = await _prompt_for_percent_again(
        callback.message,
        state,
        notice="❌ Chegirma tasdiqlanmadi. Yangi foiz yuboring.",
    )
    if not repeated:
        data = await state.get_data()
        restored = await _restore_discount_panel(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            panel_message_id=data.get("panel_message_id"),
            selected_service_id=data.get("selected_service_id"),
            selected_service_index=int(data.get("selected_service_index", 0)),
            notice="⚠️ Tanlangan xizmat topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(**restored)
    await callback.answer("Chegirma tasdiqlanmadi.")


@router.callback_query(F.data.startswith(f"{DISCOUNT_END_DATE_PREFIX}:"))
async def choose_discount_end_date(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return
    if not await _ensure_discount_callback_state(
        callback,
        state,
        AdminDiscountStates.waiting_for_discount_end_date,
    ):
        return

    date_text = _parse_end_date_callback(callback.data or "")
    if date_text is None:
        await callback.answer("Noto'g'ri sana.", show_alert=True)
        return

    await state.update_data(pending_discount_end_date=date_text)
    await state.set_state(AdminDiscountStates.waiting_for_discount_end_time)
    await _send_end_time_prompt(callback.message, date_text)
    await callback.answer("Sana qabul qilindi.")


@router.callback_query(F.data == DISCOUNT_END_TIME_BACK_CB)
async def back_to_discount_end_date(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return
    if not await _ensure_discount_callback_state(
        callback,
        state,
        AdminDiscountStates.waiting_for_discount_end_time,
    ):
        return

    await state.update_data(pending_discount_end_date=None)
    await state.set_state(AdminDiscountStates.waiting_for_discount_end_date)
    await callback.message.answer(
        _build_end_date_prompt(),
        parse_mode="HTML",
        reply_markup=_discount_date_keyboard(),
    )
    await callback.answer("Sana tanlashga qaytildi.")


@router.callback_query(F.data.startswith(f"{DISCOUNT_END_TIME_PREFIX}:"))
async def choose_discount_end_time(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return
    if not await _ensure_discount_callback_state(
        callback,
        state,
        AdminDiscountStates.waiting_for_discount_end_time,
    ):
        return

    time_text = _parse_end_time_callback(callback.data or "")
    if time_text is None:
        await callback.answer("Noto'g'ri vaqt.", show_alert=True)
        return

    await _finish_discount_flow(
        callback.message,
        state,
        end_time_text=time_text,
    )
    await callback.answer("Vaqt qabul qilindi.")


@router.message(
    Command("cancel"),
    StateFilter(
        AdminDiscountStates.waiting_for_all_services_percent,
        AdminDiscountStates.waiting_for_selected_service_percent,
        AdminDiscountStates.waiting_for_discount_confirmation,
        AdminDiscountStates.waiting_for_discount_end_date,
        AdminDiscountStates.waiting_for_discount_end_time,
    ),
)
async def cancel_discount_flow(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    data = await state.get_data()
    restored = await _restore_discount_panel(
        bot=message.bot,
        chat_id=message.chat.id,
        panel_message_id=data.get("panel_message_id"),
        selected_service_id=data.get("selected_service_id"),
        selected_service_index=int(data.get("selected_service_index", 0)),
        notice="❌ Chegirma qo'yish bekor qilindi.",
    )
    await state.clear()
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(**restored)


@router.message(StateFilter(AdminDiscountStates.waiting_for_all_services_percent))
async def apply_discount_to_all_services(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    raw_value = (message.text or "").strip()
    try:
        percent = normalize_discount_percent(raw_value)
    except DiscountValidationError as exc:
        await message.answer(_validation_message(exc), parse_mode="HTML")
        return

    services = await list_services_ordered()
    if not services:
        data = await state.get_data()
        restored = await _restore_discount_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            panel_message_id=data.get("panel_message_id"),
            selected_service_id=None,
            selected_service_index=0,
            notice="⚠️ Xizmatlar topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(**restored)
        return

    results = build_bulk_discount_results(
        ((int(service.id), int(service.price)) for service in services),
        percent,
    )
    await state.update_data(
        pending_discount_scope=DISCOUNT_SCOPE_ALL,
        pending_discount_percent=str(percent),
        pending_discount_end_date=None,
    )
    await state.set_state(AdminDiscountStates.waiting_for_discount_confirmation)
    await message.answer(
        _build_all_discount_confirmation(results, percent),
        parse_mode="HTML",
        reply_markup=_discount_confirmation_keyboard(),
    )


@router.message(StateFilter(AdminDiscountStates.waiting_for_selected_service_percent))
async def apply_discount_to_selected_service(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    raw_value = (message.text or "").strip()
    try:
        percent = normalize_discount_percent(raw_value)
    except DiscountValidationError as exc:
        await message.answer(_validation_message(exc), parse_mode="HTML")
        return

    data = await state.get_data()
    service_id = data.get("selected_service_id")
    panel_message_id = data.get("panel_message_id")
    selected_service_index = int(data.get("selected_service_index", 0))

    if not service_id:
        restored = await _restore_discount_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            panel_message_id=panel_message_id,
            selected_service_id=None,
            selected_service_index=selected_service_index,
            notice="⚠️ Jarayon buzildi. Qayta urinib ko'ring.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(**restored)
        return

    service = await get_service_by_id(int(service_id))
    if service is None:
        restored = await _restore_discount_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            panel_message_id=panel_message_id,
            selected_service_id=None,
            selected_service_index=selected_service_index,
            notice="⚠️ Tanlangan xizmat topilmadi.",
        )
        await state.clear()
        await state.set_state(AdminDiscountStates.selecting_discount_scope)
        await state.update_data(**restored)
        return

    discount_result = calculate_discount_details(int(service.price), percent)
    await state.update_data(
        pending_discount_scope=DISCOUNT_SCOPE_SINGLE,
        pending_discount_percent=str(percent),
        pending_discount_end_date=None,
    )
    await state.set_state(AdminDiscountStates.waiting_for_discount_confirmation)
    await message.answer(
        _build_single_discount_confirmation(service, discount_result),
        parse_mode="HTML",
        reply_markup=_discount_confirmation_keyboard(),
    )


@router.message(StateFilter(AdminDiscountStates.waiting_for_discount_end_date))
async def receive_discount_end_date(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    date_text = parse_future_date((message.text or "").strip())
    if not date_text:
        await message.answer(
            with_cancel_hint(
                "❌ Sana noto'g'ri. Masalan: <code>2026-04-15</code>, <code>15.04.2026</code> yoki <code>15 aprel</code>."
            ),
            parse_mode="HTML",
        )
        return

    await state.update_data(pending_discount_end_date=date_text)
    await state.set_state(AdminDiscountStates.waiting_for_discount_end_time)
    await _send_end_time_prompt(message, date_text)


@router.message(StateFilter(AdminDiscountStates.waiting_for_discount_end_time))
async def receive_discount_end_time(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    time_text = parse_user_time((message.text or "").strip())
    if not time_text:
        await message.answer(
            with_cancel_hint(
                "❌ Vaqt noto'g'ri. Masalan: <code>18:30</code> ko'rinishida yuboring."
            ),
            parse_mode="HTML",
        )
        return

    await _finish_discount_flow(
        message,
        state,
        end_time_text=time_text,
    )
