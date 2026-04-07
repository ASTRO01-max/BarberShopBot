from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sql.db_services import (
    DISCOUNT_SCOPE_ALL,
    DISCOUNT_SCOPE_SINGLE,
    bulk_set_service_discount,
    calculate_service_discount_expiry,
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


def _discount_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Barcha xizmatlarga",
                    callback_data=DISCOUNT_SCOPE_ALL_CB,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Alohida xizmatga",
                    callback_data=DISCOUNT_SCOPE_ONE_CB,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧽 Chegirmani bekor qilish",
                    callback_data=DISCOUNT_SERVICE_CANCEL_CB,
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
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga",
                    callback_data=DISCOUNT_SCOPE_BACK_CB,
                )
            ],
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
            [
                InlineKeyboardButton(
                    text="🛡 Hozircha qoldirish",
                    callback_data=DISCOUNT_CANCEL_BACK_CB,
                )
            ],
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
        [
            InlineKeyboardButton(
                text="🔙 Chegirma menyusi",
                callback_data=DISCOUNT_CANCEL_BACK_CB,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                    [
                        InlineKeyboardButton(
                            text="🔙 Orqaga",
                            callback_data=DISCOUNT_SCOPE_BACK_CB,
                        )
                    ]
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


def _single_service_discount_prompt(service) -> str:
    snapshot = get_service_price_snapshot(service)
    lines = [
        "Tanlangan xizmat uchun chegirma foizini yuboring.",
        "",
        f"💈 Xizmat: <b>{escape(service.name)}</b>",
        f"💵 Asl narx: <b>{format_price(snapshot.base_price)}</b> so'm",
    ]

    if snapshot.has_discount:
        percent_text = format_discount_percent(snapshot.discount_percent)
        lines.extend(
            [
                f"🏷 Joriy chegirma: <b>{percent_text}%</b>",
                f"💸 Amaldagi chegirmali narx: <b>{format_price(snapshot.current_price)}</b> so'm",
                "",
                "Yangi foiz yuborsangiz, mavjud chegirma yangilanadi.",
            ]
        )

    lines.append("Chegirma saqlangach, tugash sanasi va vaqti avtomatik belgilanadi.")
    lines.append("Qo'llab-quvvatlanadigan format: <code>10</code> yoki <code>12.5</code>")
    return with_cancel_hint("\n".join(lines))


def _all_services_discount_prompt() -> str:
    return with_cancel_hint(
        "Barcha xizmatlar uchun chegirma foizini yuboring.\n\n"
        "Chegirma saqlangach, tugash sanasi va vaqti avtomatik belgilanadi.\n"
        "Qo'llab-quvvatlanadigan format: <code>10</code> yoki <code>12.5</code>\n"
        "Chegirma xizmatlarning asl narxlari asosida hisoblanadi."
    )


def _build_cancel_all_warning_text(total_services: int) -> str:
    return (
        "⚠️ <b>Barcha xizmatlarda faol chegirma bor.</b>\n\n"
        f"🧾 Chegirmadagi xizmatlar soni: <b>{total_services}</b>\n"
        "Tasdiqlasangiz, barcha xizmatlardagi chegirma foizi va chegirmali narx yozuvlari birdaniga olib tashlanadi.\n"
        "Asl narxlar o'zgarmaydi.\n\n"
        "Davom etishni tasdiqlang."
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


def _validation_message(error: DiscountValidationError) -> str:
    return with_cancel_hint(f"❌ {escape(str(error))}")


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

    await state.set_state(AdminDiscountStates.waiting_for_all_services_percent)
    await state.update_data(
        panel_message_id=callback.message.message_id,
        selected_service_id=None,
        selected_service_index=0,
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

    await state.set_state(AdminDiscountStates.waiting_for_selected_service_percent)
    await state.update_data(
        panel_message_id=callback.message.message_id,
        selected_service_id=int(service.id),
        selected_service_index=index,
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


@router.message(
    Command("cancel"),
    StateFilter(
        AdminDiscountStates.waiting_for_all_services_percent,
        AdminDiscountStates.waiting_for_selected_service_percent,
    ),
)
async def cancel_discount_flow(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        await state.clear()
        return

    data = await state.get_data()
    panel_message_id = data.get("panel_message_id")
    selected_service_id = data.get("selected_service_id")
    selected_service_index = int(data.get("selected_service_index", 0))

    if selected_service_id:
        await _show_discount_service_page(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            index=selected_service_index,
            notice="❌ Chegirma qo'yish bekor qilindi.",
        )
    else:
        await _show_discount_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            notice="❌ Chegirma qo'yish bekor qilindi.",
        )

    await state.clear()


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
        await state.clear()
        await _show_discount_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=data.get("panel_message_id"),
            notice="⚠️ Xizmatlar topilmadi.",
        )
        return

    results = build_bulk_discount_results(
        ((int(service.id), int(service.price)) for service in services),
        percent,
    )
    end_at, end_time = calculate_service_discount_expiry()
    expiry_text = format_service_discount_expiry(end_at, end_time)
    updated_count = await bulk_set_service_discount(
        (int(service.id) for service in services),
        percent,
        applied_scope=DISCOUNT_SCOPE_ALL,
        end_at=end_at,
        end_time=end_time,
    )
    changed_count = sum(1 for item in results if item.old_price != item.new_price)
    percent_text = format_discount_percent(percent)

    notice = (
        "✅ <b>Barcha xizmatlarga chegirma qo'llandi.</b>\n\n"
        f"Jami xizmatlar: <b>{len(results)}</b>\n"
        f"Qo'llangan foiz: <b>{percent_text}%</b>\n"
        f"Yangilangan yozuvlar: <b>{updated_count}</b>\n"
        f"Narxi o'zgargan xizmatlar: <b>{changed_count}</b>\n"
        f"Avtomatik tugash: <b>{expiry_text}</b>\n\n"
        "Chegirma foizi va chegirmali narxlar alohida jadvalga saqlandi."
    )

    data = await state.get_data()
    await state.clear()
    shown_message_id = await _show_discount_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=data.get("panel_message_id"),
        notice=notice,
    )
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(panel_message_id=shown_message_id)


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
        await state.clear()
        await _show_discount_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            notice="⚠️ Jarayon buzildi. Qayta urinib ko'ring.",
        )
        return

    service = await get_service_by_id(int(service_id))
    if service is None:
        await state.clear()
        await _show_discount_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            notice="⚠️ Tanlangan xizmat topilmadi.",
        )
        return

    discount_result = calculate_discount_details(int(service.price), percent)
    end_at, end_time = calculate_service_discount_expiry()
    expiry_text = format_service_discount_expiry(end_at, end_time)
    updated_service = await set_service_discount(
        int(service.id),
        percent,
        applied_scope=DISCOUNT_SCOPE_SINGLE,
        end_at=end_at,
        end_time=end_time,
    )
    if updated_service is None:
        await state.clear()
        await _show_discount_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            notice="⚠️ Chegirmani saqlab bo'lmadi. Qayta urinib ko'ring.",
        )
        return

    percent_text = format_discount_percent(discount_result.discount_percent)
    notice = (
        "✅ <b>Chegirma muvaffaqiyatli qo'llandi.</b>\n\n"
        f"💈 Xizmat: <b>{escape(updated_service.name)}</b>\n"
        f"💵 Asl narx: <b>{format_price(discount_result.old_price)}</b> so'm\n"
        f"🏷 Chegirma: <b>{percent_text}%</b>\n"
        f"💸 Chegirmali narx: <b>{format_price(discount_result.new_price)}</b> so'm\n"
        f"Avtomatik tugash: <b>{expiry_text}</b>\n\n"
        "Chegirma foizi va chegirmali narx alohida jadvalga saqlandi."
    )

    await state.clear()
    shown_message_id, page_index, current_service_id = await _show_discount_service_page(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=panel_message_id,
        index=selected_service_index,
        notice=notice,
    )
    await state.set_state(AdminDiscountStates.selecting_discount_scope)
    await state.update_data(
        panel_message_id=shown_message_id,
        selected_service_index=page_index,
        selected_service_id=current_service_id,
    )
