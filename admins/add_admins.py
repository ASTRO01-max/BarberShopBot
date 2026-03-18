# admins/add_admins.py
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func, or_, select

from sql.db import async_session
from sql.models import Admins, OrdinaryUser
from .admin_buttons import (
    ADMIN_ADD_CB,
    ADMIN_ADD_TEXT,
    ADMIN_CANCEL_CB,
    ADMIN_DEL_CB,
    ADMIN_DEL_TEXT,
    ADMIN_MENU_TEXT,
    get_admin_cancel_kb,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
ADMIN_NAV_PREFIX = "admadmin"
ADMIN_DELETE_PICK_PREFIX = "admin:delete:pick"
ADMIN_DELETE_CONFIRM_PREFIX = "admin:delete:confirm"
ADMIN_DELETE_CANCEL_PREFIX = "admin:delete:cancel"
ADMIN_PAGE_SIZE = 1


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


class AdminManageState(StatesGroup):
    adding_lookup = State()
    adding_phone = State()


def _normalize_username(username: str | None) -> str:
    username_text = (username or "").strip()
    if username_text and not username_text.startswith("@"):
        username_text = f"@{username_text}"
    return username_text


def _admin_display_name(admin: Admins) -> str:
    username_text = _normalize_username(admin.username)
    return (admin.admin_fullname or "").strip() or username_text or str(admin.tg_id)


def _admin_nav_keyboard(index: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{ADMIN_NAV_PREFIX}_prev_{index}",
                ),
                types.InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"{ADMIN_NAV_PREFIX}_next_{index}",
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text=ADMIN_ADD_TEXT,
                    callback_data=ADMIN_ADD_CB,
                ),
                types.InlineKeyboardButton(
                    text=ADMIN_DEL_TEXT,
                    callback_data=f"{ADMIN_DELETE_PICK_PREFIX}:{index}",
                ),
            ],
        ]
    )


def _admin_delete_confirmation_keyboard(
    admin_id: int,
    index: int,
) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"{ADMIN_DELETE_CONFIRM_PREFIX}:{admin_id}:{index}",
                ),
                types.InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=f"{ADMIN_DELETE_CANCEL_PREFIX}:{index}",
                ),
            ]
        ]
    )


async def _count_admins() -> int:
    async with async_session() as session:
        total = await session.scalar(select(func.count(Admins.id)))
    return int(total or 0)


async def _fetch_admin_page(index: int, total: int | None = None):
    if total is None:
        total = await _count_admins()
    if total <= 0:
        return 0, 0, None

    normalized_index = index % total
    offset = normalized_index * ADMIN_PAGE_SIZE

    async with async_session() as session:
        admin = (
            await session.execute(
                select(Admins)
                .order_by(Admins.id.asc())
                .limit(ADMIN_PAGE_SIZE)
                .offset(offset)
            )
        ).scalar_one_or_none()

    return total, normalized_index, admin


def _render_admin_summary(admin: Admins) -> str:
    display_name = escape(_admin_display_name(admin))
    username_text = escape(_normalize_username(admin.username) or "-")
    phone_text = escape(admin.phone or "-")
    tg_id_text = escape(str(admin.tg_id or "-"))

    return (
        f"🧩 <b>{display_name}</b>\n"
        f"├ Username: {username_text}\n"
        f"├ Telefon: <code>{phone_text}</code>\n"
        f"└ TG ID: <code>{tg_id_text}</code>"
    )


def _render_admin_page_text(total: int, index: int, admin: Admins | None) -> str:
    if total <= 0 or admin is None:
        return (
            "👔 <b>Adminlar ro'yxati</b>\n\n"
            "⚠️ <i>Hozircha adminlar mavjud emas.</i>\n\n"
            "📌 <i>(0 / 0)</i>"
        )

    return (
        "👔 <b>Adminlar ro'yxati</b>\n\n"
        f"{_render_admin_summary(admin)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


def _render_admin_delete_confirmation_text(total: int, index: int, admin: Admins) -> str:
    return (
        "🗑 <b>Adminni o'chirish</b>\n\n"
        "Quyidagi adminni o'chirishni tasdiqlaysizmi?\n\n"
        f"{_render_admin_summary(admin)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _edit_or_send_admin_message(
    callback: types.CallbackQuery,
    text: str,
    reply_markup: types.InlineKeyboardMarkup,
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


async def _show_admin_page_message(
    message: types.Message,
    index: int = 0,
    total: int | None = None,
) -> None:
    total, index, admin = await _fetch_admin_page(index, total=total)
    await message.answer(
        _render_admin_page_text(total, index, admin),
        parse_mode="HTML",
        reply_markup=_admin_nav_keyboard(index),
    )


async def _show_admin_page_callback(
    callback: types.CallbackQuery,
    index: int = 0,
    total: int | None = None,
    notice: str | None = None,
) -> None:
    total, index, admin = await _fetch_admin_page(index, total=total)
    text = _render_admin_page_text(total, index, admin)
    if notice:
        text = f"{notice}\n\n{text}"

    await _edit_or_send_admin_message(
        callback,
        text=text,
        reply_markup=_admin_nav_keyboard(index),
    )


async def _start_add_admin(message: types.Message | None, state: FSMContext) -> None:
    if message is None:
        return

    await state.clear()
    await state.set_state(AdminManageState.adding_lookup)
    await message.answer(
        with_cancel_hint("Adminning to'liq ismini yoki @username ni kiriting:"),
        reply_markup=get_admin_cancel_kb(),
    )


@router.callback_query(F.data.startswith(f"{ADMIN_NAV_PREFIX}_"))
async def admin_pagination_nav(callback: types.CallbackQuery):
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

    total = await _count_admins()
    if total > 0:
        if action == "next":
            index = (index + 1) % total
        else:
            index = (index - 1) % total
    else:
        index = 0

    await _show_admin_page_callback(callback, index=index, total=total)
    await callback.answer()


@router.message(F.text == ADMIN_MENU_TEXT)
async def show_admin_actions(message: types.Message, state: FSMContext):
    await state.clear()
    await _show_admin_page_message(message, index=0)


@router.callback_query(F.data == ADMIN_ADD_CB)
async def start_add_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_add_admin(callback.message, state)


@router.message(F.text == ADMIN_ADD_TEXT)
async def start_add_admin_message(message: types.Message, state: FSMContext):
    await _start_add_admin(message, state)


@router.callback_query(F.data == ADMIN_DEL_CB)
async def open_admin_page_for_legacy_delete(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_admin_page_callback(callback, index=0)
    await callback.answer(
        "Kerakli adminni ochib, shu sahifadan o'chirishni tasdiqlang.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith(f"{ADMIN_DELETE_PICK_PREFIX}:"))
async def ask_admin_delete_confirmation(callback: types.CallbackQuery, state: FSMContext):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await state.clear()
    total, index, admin = await _fetch_admin_page(index)
    if admin is None:
        await callback.answer("O'chirish uchun admin topilmadi.", show_alert=True)
        await _show_admin_page_callback(callback, index=0, total=0)
        return

    await _edit_or_send_admin_message(
        callback,
        text=_render_admin_delete_confirmation_text(total, index, admin),
        reply_markup=_admin_delete_confirmation_keyboard(admin.id, index),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{ADMIN_DELETE_CANCEL_PREFIX}:"))
async def cancel_admin_delete(callback: types.CallbackQuery):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await _show_admin_page_callback(callback, index=index)
    await callback.answer("O'chirish bekor qilindi.")


@router.callback_query(F.data.startswith(f"{ADMIN_DELETE_CONFIRM_PREFIX}:"))
async def confirm_admin_delete(callback: types.CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    try:
        admin_id = int(parts[3])
        index = int(parts[4])
    except ValueError:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    async with async_session() as session:
        admin = await session.get(Admins, admin_id)
        if admin is None:
            await callback.answer("Admin topilmadi.", show_alert=True)
            await _show_admin_page_callback(callback, index=index)
            return

        deleted_name = _admin_display_name(admin)
        await session.delete(admin)
        await session.commit()

    remaining_total = await _count_admins()
    next_index = 0 if remaining_total <= 0 else min(index, remaining_total - 1)

    await _show_admin_page_callback(
        callback,
        index=next_index,
        total=remaining_total,
        notice=f"✅ <b>{escape(deleted_name)}</b> admin o'chirildi.",
    )
    await callback.answer("Admin o'chirildi.", show_alert=True)


@router.message(
    StateFilter(AdminManageState.adding_lookup, AdminManageState.adding_phone),
    Command("cancel"),
)
async def cancel_add_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")
    await _show_admin_page_message(message, index=0)


@router.callback_query(F.data == ADMIN_CANCEL_CB)
async def admin_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ Jarayon bekor qilindi.")
        await _show_admin_page_message(callback.message, index=0)
    await callback.answer()


@router.message(StateFilter(AdminManageState.adding_lookup))
async def add_admin_lookup(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            with_cancel_hint("Iltimos, to'liq ism yoki @username kiriting."),
            reply_markup=get_admin_cancel_kb(),
        )
        return

    async with async_session() as session:
        user = None
        if text.startswith("@"):
            username = text[1:].strip()
            if username:
                res = await session.execute(
                    select(OrdinaryUser).where(
                        or_(
                            OrdinaryUser.username.ilike(username),
                            OrdinaryUser.username.ilike(f"@{username}"),
                        )
                    )
                )
                user = res.scalars().first()
        elif " " in text:
            parts = [p for p in text.split() if p]
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = " ".join(parts[1:])
                res = await session.execute(
                    select(OrdinaryUser).where(
                        OrdinaryUser.first_name.ilike(first_name.strip()),
                        OrdinaryUser.last_name.ilike(last_name.strip()),
                    )
                )
                user = res.scalars().first()
                if not user:
                    res = await session.execute(
                        select(OrdinaryUser).where(
                            OrdinaryUser.last_name.ilike(first_name.strip()),
                            OrdinaryUser.first_name.ilike(last_name.strip()),
                        )
                    )
                    user = res.scalars().first()
        else:
            res = await session.execute(
                select(OrdinaryUser).where(OrdinaryUser.username.ilike(text))
            )
            user = res.scalars().first()
            if not user:
                res = await session.execute(
                    select(OrdinaryUser).where(OrdinaryUser.first_name.ilike(text))
                )
                user = res.scalars().first()
            if not user:
                res = await session.execute(
                    select(OrdinaryUser).where(OrdinaryUser.last_name.ilike(text))
                )
                user = res.scalars().first()

        if not user:
            await message.answer(
                with_cancel_hint("Oddiy foydalanuvchi topilmadi. Qayta kiriting:"),
                reply_markup=get_admin_cancel_kb(),
            )
            return

        existing = await session.execute(select(Admins).where(Admins.tg_id == user.tg_id))
        if existing.scalars().first():
            await message.answer(
                with_cancel_hint("Admin allaqachon mavjud."),
                reply_markup=get_admin_cancel_kb(),
            )
            return

        fullname = None
        if user.first_name or user.last_name:
            fullname = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not fullname and user.username:
            fullname = _normalize_username(user.username)

        await state.update_data(
            tg_id=user.tg_id,
            admin_fullname=fullname,
            username=user.username,
        )

    await state.set_state(AdminManageState.adding_phone)
    await message.answer(
        with_cancel_hint("Adminning telefon raqamini kiriting:"),
        reply_markup=get_admin_cancel_kb(),
    )


@router.message(StateFilter(AdminManageState.adding_phone))
async def add_admin_phone(message: types.Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(
            with_cancel_hint("Telefon raqamini kiriting:"),
            reply_markup=get_admin_cancel_kb(),
        )
        return

    data = await state.get_data()
    tg_id = data.get("tg_id")
    admin_fullname = data.get("admin_fullname")
    username = data.get("username")

    if not tg_id:
        await state.clear()
        await message.answer("Ma'lumotlar topilmadi. Qayta boshlang.")
        return

    async with async_session() as session:
        existing = await session.execute(select(Admins).where(Admins.tg_id == tg_id))
        if existing.scalars().first():
            await state.clear()
            await message.answer("Admin allaqachon mavjud.")
            return

        new_admin = Admins(
            tg_id=tg_id,
            admin_fullname=admin_fullname,
            phone=phone,
            username=username,
        )
        session.add(new_admin)
        await session.commit()

    await state.clear()
    display_name = escape((admin_fullname or "").strip() or _normalize_username(username) or str(tg_id))
    username_text = escape(_normalize_username(username) or "-")
    phone_text = escape(phone)
    tg_id_text = escape(str(tg_id))

    await message.answer(
        "✅ <b>Admin muvaffaqiyatli qo'shildi!</b>\n\n"
        f"🧩 <b>{display_name}</b>\n"
        f"├ Username: {username_text}\n"
        f"├ Telefon: <code>{phone_text}</code>\n"
        f"└ TG ID: <code>{tg_id_text}</code>",
        parse_mode="HTML",
    )
