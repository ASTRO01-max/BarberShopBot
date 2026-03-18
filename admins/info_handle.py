# admins/info_hande.py
from dataclasses import dataclass
from datetime import datetime
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import Admins, Info, InfoExpanded
from .admin_buttons import INFO_ADD_CB, INFO_DELETE_CB, INFO_EDIT_CB, INFO_MENU_TEXT

router = Router()

# Pagination callback format:
# info:nav:prev:{current_page}
# info:nav:next:{current_page}
INFO_NAV_PREFIX = "info:nav"
INFO_NAV_NOOP_CB = f"{INFO_NAV_PREFIX}:noop"
PAGE_TABLE_INFO = "info"
PAGE_TABLE_EXPANDED = "info_expanded"

# FSM data keys
STATE_PAGE_KEY = "info_page"
STATE_TARGET_KEY = "info_target_id"
STATE_STEP_KEY = "info_step"
STATE_PHONE_KEY = "info_phone"

# FSM steps
STEP_PHONE = "phone"
STEP_DISCOUNT = "discount"

CANCEL_HINT = "\n\nBekor qilish uchun: /cancel"


class InfoFSM(StatesGroup):
    adding = State()
    editing = State()


@dataclass(frozen=True, slots=True)
class InfoFieldSpec:
    table: str
    field: str
    label: str
    formatter: str = "text"


@dataclass(slots=True)
class InfoPageBundle:
    total: int
    page: int
    spec: InfoFieldSpec
    value: str
    target_id: int | None


INFO_FIELD_SPECS = [
    InfoFieldSpec(PAGE_TABLE_INFO, "telegram", "✈️ Telegram"),
    InfoFieldSpec(PAGE_TABLE_INFO, "instagram", "📷 Instagram"),
    InfoFieldSpec(PAGE_TABLE_INFO, "website", "🔗 Website"),
    InfoFieldSpec(PAGE_TABLE_INFO, "region", "🏙 Hudud"),
    InfoFieldSpec(PAGE_TABLE_INFO, "district", "🏘 Tuman"),
    InfoFieldSpec(PAGE_TABLE_INFO, "street", "🛣 Ko'cha"),
    InfoFieldSpec(PAGE_TABLE_INFO, "address_text", "📍 Manzil"),
    InfoFieldSpec(PAGE_TABLE_INFO, "latitude", "🧭 Latitude"),
    InfoFieldSpec(PAGE_TABLE_INFO, "longitude", "🧭 Longitude"),
    InfoFieldSpec(PAGE_TABLE_INFO, "work_time_text", "🕒 Ish vaqti"),
]

EXPANDED_FIELD_SPECS = [
    InfoFieldSpec(PAGE_TABLE_EXPANDED, "phone_number", "📞 Telefon"),
    InfoFieldSpec(PAGE_TABLE_EXPANDED, "discount", "💸 Chegirma"),
    InfoFieldSpec(PAGE_TABLE_EXPANDED, "created_at", "📅 Yaratilgan", "datetime"),
    InfoFieldSpec(PAGE_TABLE_EXPANDED, "updated_at", "♻️ Yangilangan", "datetime"),
]

PAGE_SPECS = INFO_FIELD_SPECS + EXPANDED_FIELD_SPECS
PAGE_INDEX_BY_KEY = {(spec.table, spec.field): index for index, spec in enumerate(PAGE_SPECS)}
TOTAL_PAGES = len(PAGE_SPECS)
DEFAULT_PAGE = 0
DEFAULT_EXPANDED_PAGE = PAGE_INDEX_BY_KEY[(PAGE_TABLE_EXPANDED, "phone_number")]


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return text if text else "—"


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def _normalize_page(page: int) -> int:
    return page % TOTAL_PAGES if TOTAL_PAGES else 0


def _normalize_expanded_page(page: int) -> int:
    normalized = _normalize_page(page)
    spec = PAGE_SPECS[normalized]
    return normalized if spec.table == PAGE_TABLE_EXPANDED else DEFAULT_EXPANDED_PAGE


def _parse_nav_callback(data: str) -> tuple[str | None, int]:
    parts = (data or "").split(":")
    if len(parts) != 4:
        return None, 0
    if parts[0] != "info" or parts[1] != "nav":
        return None, 0
    action = parts[2]
    if action not in {"prev", "next"}:
        return None, 0
    return action, _to_int(parts[3], 0)


def _parse_target_callback(data: str, prefix: str) -> tuple[int | None, int | None]:
    # Supports callback format: {prefix}:{page}:{target_id}
    marker = f"{prefix}:"
    if not (data or "").startswith(marker):
        return None, None

    payload = data[len(marker) :]
    parts = payload.split(":")
    if len(parts) != 2:
        return None, None

    page = _to_int(parts[0], 0)
    target_id = _to_int(parts[1], 0)
    if target_id <= 0:
        return None, None
    return page, target_id


def _format_field_value(spec: InfoFieldSpec, obj: Info | InfoExpanded | None) -> str:
    raw_value = getattr(obj, spec.field, None) if obj else None
    if spec.formatter == "datetime":
        return _fmt_dt(raw_value)
    return _safe_text(raw_value)


def _render_value_html(value: str) -> str:
    safe_value = escape(value).replace("\n", "<br>")
    return f"<blockquote>{safe_value}</blockquote>"


def _render_text(bundle: InfoPageBundle) -> str:
    return (
        f"<b>{escape(bundle.spec.label)}</b>\n\n"
        f"{_render_value_html(bundle.value)}\n"
        f"<code>{bundle.page + 1}/{bundle.total}</code>"
    )


def _build_keyboard(
    total: int,
    page: int,
    spec: InfoFieldSpec,
    target_id: int | None,
) -> types.InlineKeyboardMarkup:
    nav_row = [
        types.InlineKeyboardButton(
            text="⬅️ Oldingi",
            callback_data=f"{INFO_NAV_PREFIX}:prev:{page}",
        ),
        types.InlineKeyboardButton(
            text=f"📄 {page + 1}/{total}" if total > 0 else "📄 0/0",
            callback_data=INFO_NAV_NOOP_CB,
        ),
        types.InlineKeyboardButton(
            text="➡️ Keyingi",
            callback_data=f"{INFO_NAV_PREFIX}:next:{page}",
        ),
    ]

    rows = [nav_row]

    if spec.table == PAGE_TABLE_EXPANDED and not target_id:
        rows.append(
            [types.InlineKeyboardButton(text="➕ ℹ️ Info kiritish", callback_data=INFO_ADD_CB)]
        )
    elif spec.table == PAGE_TABLE_EXPANDED and target_id:
        rows.append(
            [
                types.InlineKeyboardButton(
                    text="✏️ Info tahrirlash",
                    callback_data=f"{INFO_EDIT_CB}:{page}:{target_id}",
                ),
                types.InlineKeyboardButton(
                    text="❌ Info o'chirish",
                    callback_data=f"{INFO_DELETE_CB}:{page}:{target_id}",
                ),
            ]
        )

    return types.InlineKeyboardMarkup(inline_keyboard=rows)


async def _is_admin(tg_id: int) -> bool:
    async with async_session() as session:
        admin_id = await session.scalar(select(Admins.id).where(Admins.tg_id == tg_id).limit(1))
    return admin_id is not None


async def _fetch_page_bundle(page: int) -> InfoPageBundle:
    async with async_session() as session:
        base_info = await session.get(Info, 1)
        result = await session.execute(
            select(InfoExpanded).order_by(InfoExpanded.id.asc()).limit(1)
        )
        expanded_item = result.scalars().first()

    normalized = _normalize_page(page)
    spec = PAGE_SPECS[normalized]
    source_obj = base_info if spec.table == PAGE_TABLE_INFO else expanded_item
    return InfoPageBundle(
        total=TOTAL_PAGES,
        page=normalized,
        spec=spec,
        value=_format_field_value(spec, source_obj),
        target_id=getattr(expanded_item, "id", None),
    )


async def _fetch_by_id(target_id: int) -> InfoExpanded | None:
    async with async_session() as session:
        return await session.get(InfoExpanded, target_id)


async def _state_page(state: FSMContext, default: int = DEFAULT_PAGE) -> int:
    data = await state.get_data()
    return _to_int(data.get(STATE_PAGE_KEY), default)


async def _safe_edit_or_answer(
    message: types.Message | None,
    text: str,
    reply_markup: types.InlineKeyboardMarkup,
) -> None:
    if not message:
        return

    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def _show_page_message(message: types.Message, state: FSMContext, page: int = DEFAULT_PAGE) -> None:
    bundle = await _fetch_page_bundle(page)
    await state.update_data(**{STATE_PAGE_KEY: bundle.page})
    text = _render_text(bundle)
    kb = _build_keyboard(bundle.total, bundle.page, bundle.spec, bundle.target_id)
    await message.answer(
        text,
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def _show_page_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    page: int = DEFAULT_PAGE,
) -> None:
    bundle = await _fetch_page_bundle(page)
    await state.update_data(**{STATE_PAGE_KEY: bundle.page})
    text = _render_text(bundle)
    kb = _build_keyboard(bundle.total, bundle.page, bundle.spec, bundle.target_id)
    await _safe_edit_or_answer(callback.message, text, kb)


async def _clear_info_form_state(state: FSMContext, page: int | None = None) -> None:
    current_state = await state.get_state()
    if current_state in {InfoFSM.adding.state, InfoFSM.editing.state}:
        await state.clear()
        if page is not None:
            await state.update_data(**{STATE_PAGE_KEY: page})


async def open_info_panel(message: types.Message, state: FSMContext) -> None:
    if not await _is_admin(message.from_user.id):
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    await state.clear()
    await _show_page_message(message, state, page=DEFAULT_PAGE)


@router.message(F.text == INFO_MENU_TEXT)
async def open_info_menu_message(message: types.Message, state: FSMContext):
    await open_info_panel(message, state)


@router.callback_query(F.data == INFO_NAV_NOOP_CB)
async def info_nav_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith(f"{INFO_NAV_PREFIX}:"))
async def info_navigate(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    action, current_page = _parse_nav_callback(callback.data or "")
    if action is None:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    bundle = await _fetch_page_bundle(current_page)
    if action == "next":
        target_page = (bundle.page + 1) % bundle.total
    else:
        target_page = (bundle.page - 1) % bundle.total

    old_page = await _state_page(state, default=DEFAULT_PAGE)
    if old_page != target_page:
        await _clear_info_form_state(state, page=target_page)

    await _show_page_callback(callback, state, page=target_page)
    await callback.answer()


@router.callback_query(F.data == INFO_ADD_CB)
async def info_add_start(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    current_page = _normalize_expanded_page(
        await _state_page(state, default=DEFAULT_EXPANDED_PAGE)
    )
    bundle = await _fetch_page_bundle(current_page)
    if bundle.target_id:
        await callback.answer("Info mavjud. Tahrirlashdan foydalaning.", show_alert=True)
        await _show_page_callback(callback, state, page=current_page)
        return

    await state.set_state(InfoFSM.adding)
    await state.update_data(
        **{
            STATE_PAGE_KEY: current_page,
            STATE_TARGET_KEY: None,
            STATE_STEP_KEY: STEP_PHONE,
            STATE_PHONE_KEY: "",
        }
    )

    if callback.message:
        await callback.message.answer("📞 Telefon raqamini kiriting." + CANCEL_HINT)
    await callback.answer()


@router.callback_query(F.data == INFO_EDIT_CB)
@router.callback_query(F.data.startswith(f"{INFO_EDIT_CB}:"))
async def info_edit_start(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    parsed_page, parsed_target_id = _parse_target_callback(callback.data or "", INFO_EDIT_CB)
    current_page = _normalize_expanded_page(
        parsed_page if parsed_page is not None else await _state_page(state, default=DEFAULT_EXPANDED_PAGE)
    )

    if parsed_target_id:
        current = await _fetch_by_id(parsed_target_id)
        if not current:
            await _clear_info_form_state(state, page=current_page)
            await _show_page_callback(callback, state, page=current_page)
            await callback.answer("Tanlangan info topilmadi.", show_alert=True)
            return
        target_id = current.id
    else:
        bundle = await _fetch_page_bundle(current_page)
        if not bundle.target_id:
            await _clear_info_form_state(state, page=current_page)
            await _show_page_callback(callback, state, page=current_page)
            await callback.answer("Tahrirlash uchun ma'lumot yo'q.", show_alert=True)
            return
        current = await _fetch_by_id(bundle.target_id)
        if not current:
            await _clear_info_form_state(state, page=current_page)
            await _show_page_callback(callback, state, page=current_page)
            await callback.answer("Tanlangan info topilmadi.", show_alert=True)
            return
        target_id = current.id

    await _clear_info_form_state(state, page=current_page)

    await state.set_state(InfoFSM.editing)
    await state.update_data(
        **{
            STATE_PAGE_KEY: current_page,
            STATE_TARGET_KEY: target_id,
            STATE_STEP_KEY: STEP_PHONE,
            STATE_PHONE_KEY: "",
        }
    )

    if callback.message:
        await callback.message.answer(
            f"✏️ Telefon raqamini kiriting.\nJoriy: {_safe_text(current.phone_number)}{CANCEL_HINT}"
        )
    await callback.answer()


@router.callback_query(F.data == INFO_DELETE_CB)
@router.callback_query(F.data.startswith(f"{INFO_DELETE_CB}:"))
async def info_delete(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    parsed_page, target_id = _parse_target_callback(callback.data or "", INFO_DELETE_CB)
    current_page = _normalize_expanded_page(
        parsed_page if parsed_page is not None else await _state_page(state, default=DEFAULT_EXPANDED_PAGE)
    )

    if not target_id:
        bundle = await _fetch_page_bundle(current_page)
        if not bundle.target_id:
            await _clear_info_form_state(state, page=current_page)
            await _show_page_callback(callback, state, page=current_page)
            await callback.answer("O'chirish uchun ma'lumot yo'q.", show_alert=True)
            return
        target_id = bundle.target_id

    async with async_session() as session:
        try:
            obj = await session.get(InfoExpanded, target_id)
            if not obj:
                await callback.answer("Tanlangan info topilmadi.", show_alert=True)
                await _clear_info_form_state(state, page=current_page)
                await _show_page_callback(callback, state, page=current_page)
                return

            await session.delete(obj)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            await callback.answer("O'chirishda xatolik yuz berdi.", show_alert=True)
            return

    await _clear_info_form_state(state, page=current_page)
    await _show_page_callback(callback, state, page=current_page)
    await callback.answer("✅ Info o'chirildi.")


@router.message(StateFilter(InfoFSM.adding, InfoFSM.editing), Command("cancel"))
async def cancel_info_form(message: types.Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    page = await _state_page(state, default=DEFAULT_PAGE)
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")
    await _show_page_message(message, state, page=page)


@router.message(StateFilter(InfoFSM.adding, InfoFSM.editing))
async def process_info_form(message: types.Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ Matn yuboring." + CANCEL_HINT)
        return

    current_state = await state.get_state()
    data = await state.get_data()

    page = _normalize_expanded_page(_to_int(data.get(STATE_PAGE_KEY), DEFAULT_EXPANDED_PAGE))
    target_id = _to_int(data.get(STATE_TARGET_KEY), 0)
    step = data.get(STATE_STEP_KEY)

    if step not in {STEP_PHONE, STEP_DISCOUNT}:
        await state.clear()
        await message.answer("⚠️ Jarayon qayta tiklandi.")
        await _show_page_message(message, state, page=page)
        return

    if step == STEP_PHONE:
        if len(text) > 30:
            await message.answer("⚠️ Telefon raqami 30 belgidan oshmasligi kerak." + CANCEL_HINT)
            return

        await state.update_data(**{STATE_PHONE_KEY: text, STATE_STEP_KEY: STEP_DISCOUNT})
        await message.answer("💸 Chegirma matnini kiriting." + CANCEL_HINT)
        return

    phone_value = _safe_text(data.get(STATE_PHONE_KEY))
    if phone_value == "—":
        await state.update_data(**{STATE_STEP_KEY: STEP_PHONE})
        await message.answer("⚠️ Telefon raqamini qayta kiriting." + CANCEL_HINT)
        return

    if len(text) > 255:
        await message.answer("⚠️ Chegirma matni 255 belgidan oshmasligi kerak." + CANCEL_HINT)
        return

    if current_state == InfoFSM.adding.state:
        async with async_session() as session:
            try:
                total = int(await session.scalar(select(func.count(InfoExpanded.id))) or 0)
                if total > 0:
                    await state.clear()
                    await message.answer("⚠️ Info mavjud. Yangi qo'shish o'rniga tahrirlashdan foydalaning.")
                    await _show_page_message(message, state, page=page)
                    return

                new_item = InfoExpanded(phone_number=phone_value, discount=text)
                session.add(new_item)
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                await message.answer("❌ Saqlashda xatolik yuz berdi.")
                return

        await state.clear()
        await message.answer("✅ Info saqlandi.")
        await _show_page_message(message, state, page=page)
        return

    if current_state == InfoFSM.editing.state:
        if target_id <= 0:
            await state.clear()
            await message.answer("⚠️ Tahrirlash uchun tanlangan info topilmadi.")
            await _show_page_message(message, state, page=page)
            return

        async with async_session() as session:
            try:
                row = await session.get(InfoExpanded, target_id)
                if not row:
                    await state.clear()
                    await message.answer("⚠️ Tanlangan info topilmadi.")
                    await _show_page_message(message, state, page=page)
                    return

                row.phone_number = phone_value
                row.discount = text
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                await message.answer("❌ Yangilashda xatolik yuz berdi.")
                return

        await state.clear()
        await message.answer("✅ Info yangilandi.")
        await _show_page_message(message, state, page=page)
        return

    await state.clear()
    await message.answer("⚠️ Noma'lum holat. Jarayon bekor qilindi.")
    await _show_page_message(message, state, page=page)
