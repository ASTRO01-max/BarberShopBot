from datetime import datetime

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


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: str | None) -> str:
    text = (value or "").strip()
    return text if text else "—"


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


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


def _extra_info_block(info_row: Info | None) -> str:
    if not info_row:
        return ""

    lines: list[str] = []
    address = _safe_text(getattr(info_row, "address_text", None))
    work_time = _safe_text(getattr(info_row, "work_time_text", None))

    if address != "—":
        lines.append(f"📍 Manzil: {address}")
    if work_time != "—":
        lines.append(f"🕒 Ish vaqti: {work_time}")

    if not lines:
        return ""
    return "\n\n" + "\n".join(lines)


def _render_text(
    total: int,
    page: int,
    item: InfoExpanded | None,
    base_info: Info | None,
) -> str:
    if total <= 0 or item is None:
        return (
            "ℹ️ Info (0/0)\n\n"
            "📭 Hozircha ma'lumot yo'q.\n"
            "➕ Yangi info qo'shish uchun pastdagi tugmadan foydalaning."
            + _extra_info_block(base_info)
        )

    return (
        f"ℹ️ Info ({page + 1}/{total})\n\n"
        f"📞 Telefon: {_safe_text(item.phone_number)}\n"
        f"💸 Chegirma: {_safe_text(item.discount)}\n"
        f"📅 Yaratilgan: {_fmt_dt(item.created_at)}\n"
        f"♻️ Yangilangan: {_fmt_dt(item.updated_at)}"
        + _extra_info_block(base_info)
    )


def _build_keyboard(total: int, page: int, target_id: int | None) -> types.InlineKeyboardMarkup:
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

    if total <= 0 or not target_id:
        rows.append(
            [types.InlineKeyboardButton(text="➕ ℹ️ Info kiritish", callback_data=INFO_ADD_CB)]
        )
    else:
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


async def _fetch_page_bundle(page: int) -> tuple[int, int, InfoExpanded | None, Info | None]:
    async with async_session() as session:
        total = int(await session.scalar(select(func.count(InfoExpanded.id))) or 0)
        base_info = await session.get(Info, 1)

        if total <= 0:
            return 0, 0, None, base_info

        normalized = page % total
        result = await session.execute(
            select(InfoExpanded)
            .order_by(InfoExpanded.id.asc())
            .offset(normalized)
            .limit(1)
        )
        item = result.scalars().first()

        if item is None:
            normalized = 0
            result = await session.execute(
                select(InfoExpanded).order_by(InfoExpanded.id.asc()).limit(1)
            )
            item = result.scalars().first()

        return total, normalized, item, base_info


async def _fetch_by_id(target_id: int) -> InfoExpanded | None:
    async with async_session() as session:
        return await session.get(InfoExpanded, target_id)


async def _resolve_page_by_id(target_id: int) -> int:
    if target_id <= 0:
        return 0

    async with async_session() as session:
        total = int(await session.scalar(select(func.count(InfoExpanded.id))) or 0)
        if total <= 0:
            return 0

        index = int(
            await session.scalar(
                select(func.count(InfoExpanded.id)).where(InfoExpanded.id < target_id)
            )
            or 0
        )
        return min(max(index, 0), total - 1)


async def _state_page(state: FSMContext, default: int = 0) -> int:
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
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


async def _show_page_message(message: types.Message, state: FSMContext, page: int = 0) -> None:
    total, normalized, item, base_info = await _fetch_page_bundle(page)
    await state.update_data(**{STATE_PAGE_KEY: normalized})
    text = _render_text(total, normalized, item, base_info)
    kb = _build_keyboard(total, normalized, item.id if item else None)
    await message.answer(text, reply_markup=kb)


async def _show_page_callback(callback: types.CallbackQuery, state: FSMContext, page: int = 0) -> None:
    total, normalized, item, base_info = await _fetch_page_bundle(page)
    await state.update_data(**{STATE_PAGE_KEY: normalized})
    text = _render_text(total, normalized, item, base_info)
    kb = _build_keyboard(total, normalized, item.id if item else None)
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

    # Info bo'limiga kirganda avvalgi FSM jarayonlarini yopamiz.
    await state.clear()
    await _show_page_message(message, state, page=0)


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

    total, normalized, _, _ = await _fetch_page_bundle(current_page)
    if total <= 0:
        target_page = 0
    elif action == "next":
        target_page = (normalized + 1) % total
    else:
        target_page = (normalized - 1) % total

    # Sahifa o'zgarsa eski form-state bekor qilinadi.
    old_page = await _state_page(state, default=0)
    if old_page != target_page:
        await _clear_info_form_state(state, page=target_page)

    await _show_page_callback(callback, state, page=target_page)
    await callback.answer()


@router.callback_query(F.data == INFO_ADD_CB)
async def info_add_start(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    total, _, _, _ = await _fetch_page_bundle(await _state_page(state, default=0))
    if total > 0:
        await callback.answer("Info mavjud. Tahrirlashdan foydalaning.", show_alert=True)
        await _show_page_callback(callback, state, page=await _state_page(state, default=0))
        return

    await state.set_state(InfoFSM.adding)
    await state.update_data(
        **{
            STATE_PAGE_KEY: 0,
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

    selected_page: int
    target_id: int

    parsed_page, parsed_target_id = _parse_target_callback(callback.data or "", INFO_EDIT_CB)
    if parsed_target_id:
        target = await _fetch_by_id(parsed_target_id)
        if not target:
            await _clear_info_form_state(state, page=0)
            await _show_page_callback(callback, state, page=0)
            await callback.answer("Tanlangan info topilmadi.", show_alert=True)
            return
        target_id = target.id
        selected_page = await _resolve_page_by_id(target_id)
    else:
        selected_page = await _state_page(state, default=0)
        total, selected_page, target, _ = await _fetch_page_bundle(selected_page)
        if total <= 0 or not target:
            await _clear_info_form_state(state, page=0)
            await _show_page_callback(callback, state, page=0)
            await callback.answer("Tahrirlash uchun ma'lumot yo'q.", show_alert=True)
            return
        target_id = target.id

    await _clear_info_form_state(state, page=selected_page)

    current = await _fetch_by_id(target_id)
    if not current:
        await _show_page_callback(callback, state, page=0)
        await callback.answer("Tanlangan info topilmadi.", show_alert=True)
        return

    await state.set_state(InfoFSM.editing)
    await state.update_data(
        **{
            STATE_PAGE_KEY: selected_page,
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

    selected_page, target_id = _parse_target_callback(callback.data or "", INFO_DELETE_CB)

    if not target_id:
        selected_page = await _state_page(state, default=0)
        total, selected_page, item, _ = await _fetch_page_bundle(selected_page)
        if total <= 0 or not item:
            await _clear_info_form_state(state, page=0)
            await _show_page_callback(callback, state, page=0)
            await callback.answer("O'chirish uchun ma'lumot yo'q.", show_alert=True)
            return
        target_id = item.id

    selected_page = _to_int(selected_page, 0)

    async with async_session() as session:
        try:
            obj = await session.get(InfoExpanded, target_id)
            if not obj:
                await callback.answer("Tanlangan info topilmadi.", show_alert=True)
                await _clear_info_form_state(state, page=0)
                await _show_page_callback(callback, state, page=0)
                return

            await session.delete(obj)
            await session.commit()

            total_after = int(await session.scalar(select(func.count(InfoExpanded.id))) or 0)
        except SQLAlchemyError:
            await session.rollback()
            await callback.answer("O'chirishda xatolik yuz berdi.", show_alert=True)
            return

    if total_after <= 0:
        target_page = 0
    else:
        target_page = min(max(selected_page, 0), total_after - 1)

    await _clear_info_form_state(state, page=target_page)
    await _show_page_callback(callback, state, page=target_page)
    await callback.answer("✅ Info o'chirildi.")


@router.message(StateFilter(InfoFSM.adding, InfoFSM.editing), Command("cancel"))
async def cancel_info_form(message: types.Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    page = await _state_page(state, default=0)
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

    page = _to_int(data.get(STATE_PAGE_KEY), 0)
    target_id = _to_int(data.get(STATE_TARGET_KEY), 0)
    step = data.get(STATE_STEP_KEY)

    if step not in {STEP_PHONE, STEP_DISCOUNT}:
        # Noto'g'ri state bo'lsa, crash qilmasdan reset qilamiz.
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
                # Add faqat bo'sh holatda ruxsat etiladi.
                total = int(await session.scalar(select(func.count(InfoExpanded.id))) or 0)
                if total > 0:
                    await state.clear()
                    await message.answer("⚠️ Info mavjud. Yangi qo'shish o'rniga tahrirlashdan foydalaning.")
                    await _show_page_message(message, state, page=0)
                    return

                new_item = InfoExpanded(phone_number=phone_value, discount=text)
                session.add(new_item)
                await session.commit()

                new_id = _to_int(getattr(new_item, "id", 0), 0)
            except SQLAlchemyError:
                await session.rollback()
                await message.answer("❌ Saqlashda xatolik yuz berdi.")
                return

        target_page = await _resolve_page_by_id(new_id)
        await state.clear()
        await message.answer("✅ Info saqlandi.")
        await _show_page_message(message, state, page=target_page)
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
                    await _show_page_message(message, state, page=0)
                    return

                row.phone_number = phone_value
                row.discount = text
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                await message.answer("❌ Yangilashda xatolik yuz berdi.")
                return

        fresh_page = await _resolve_page_by_id(target_id)
        await state.clear()
        await message.answer("✅ Info yangilandi.")
        await _show_page_message(message, state, page=fresh_page)
        return

    await state.clear()
    await message.answer("⚠️ Noma'lum holat. Jarayon bekor qilindi.")
    await _show_page_message(message, state, page=0)
