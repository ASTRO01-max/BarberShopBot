# admins/add_admins.py
from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func, or_, select

from sql.db import async_session
from sql.models import Admins, OrdinaryUser
from .admin_buttons import (
    ADMIN_ADD_CB,
    ADMIN_CANCEL_CB,
    ADMIN_DEL_CB,
    ADMIN_MENU_TEXT,
    get_admin_cancel_kb,
    get_admin_inline_actions_kb,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
ADMIN_NAV_PREFIX = "admadmin"
ADMIN_PAGE_SIZE = 1


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


class AdminManageState(StatesGroup):
    adding_lookup = State()
    adding_phone = State()


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
                types.InlineKeyboardButton(text="➕ Admin qo'shish", callback_data=ADMIN_ADD_CB),
                types.InlineKeyboardButton(text="➖ Admin o'chirish", callback_data=ADMIN_DEL_CB),
            ],
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
        row = (
            await session.execute(
                select(
                    Admins.admin_fullname,
                    Admins.username,
                    Admins.phone,
                    Admins.tg_id,
                )
                .order_by(Admins.id.asc())
                .limit(ADMIN_PAGE_SIZE)
                .offset(offset)
            )
        ).first()

    return total, normalized_index, row


def _render_admin_page_text(total: int, index: int, row) -> str:
    if total <= 0 or not row:
        return (
            "👔 <b>Adminlar ro'yxati</b>\n\n"
            "⚠️ <i>Hozircha adminlar mavjud emas.</i>\n\n"
            "📌 <i>(0 / 0)</i>"
        )

    admin_fullname, username, phone, tg_id = row
    username_text = (username or "").strip()
    if username_text and not username_text.startswith("@"):
        username_text = f"@{username_text}"
    display_name = (admin_fullname or "").strip() or username_text or "Noma'lum admin"

    return (
        "👔 <b>Adminlar ro'yxati</b>\n\n"
        f"🧩 <b>{display_name}</b>\n"
        f"├ Username: {username_text or '-'}\n"
        f"├ Telefon: <code>{phone or '-'}</code>\n"
        f"└ TG ID: <code>{tg_id or '-'}</code>\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _show_admin_page_message(
    message: types.Message,
    index: int = 0,
    total: int | None = None,
) -> None:
    total, index, row = await _fetch_admin_page(index, total=total)
    await message.answer(
        _render_admin_page_text(total, index, row),
        parse_mode="HTML",
        reply_markup=_admin_nav_keyboard(index),
    )


async def _show_admin_page_callback(
    callback: types.CallbackQuery,
    index: int = 0,
    total: int | None = None,
) -> None:
    if not callback.message:
        return

    total, index, row = await _fetch_admin_page(index, total=total)
    text = _render_admin_page_text(total, index, row)
    keyboard = _admin_nav_keyboard(index)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


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


@router.message(
    StateFilter(AdminManageState.adding_lookup, AdminManageState.adding_phone),
    Command("cancel"),
)
async def cancel_add_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=get_admin_inline_actions_kb())


@router.message(F.text == ADMIN_MENU_TEXT)
async def show_admin_actions(message: types.Message, state: FSMContext):
    await state.clear()
    await _show_admin_page_message(message, index=0)


@router.callback_query(F.data == ADMIN_ADD_CB)
async def start_add_admin(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message:
        await _show_admin_page_message(callback.message, index=0)
        await state.set_state(AdminManageState.adding_lookup)
        await callback.message.answer(
            with_cancel_hint("Adminning to'liq ismini yoki @username ni kiriting:"),
            reply_markup=get_admin_cancel_kb(),
        )
    await callback.answer()


@router.callback_query(F.data == ADMIN_CANCEL_CB)
async def admin_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message:
        await _show_admin_page_message(callback.message, index=0)
    await callback.answer()


@router.message(StateFilter(AdminManageState.adding_lookup))
async def add_admin_lookup(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return await message.answer(
            with_cancel_hint("Iltimos, to'liq ism yoki @username kiriting."),
            reply_markup=get_admin_cancel_kb(),
        )

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
            res = await session.execute(select(OrdinaryUser).where(OrdinaryUser.username.ilike(text)))
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
            return await message.answer(
                with_cancel_hint("Oddiy foydalanuvchi topilmadi. Qayta kiriting:"),
                reply_markup=get_admin_cancel_kb(),
            )

        existing = await session.execute(select(Admins).where(Admins.tg_id == user.tg_id))
        if existing.scalars().first():
            return await message.answer(
                with_cancel_hint("Admin allaqachon mavjud."),
                reply_markup=get_admin_cancel_kb(),
            )

        fullname = None
        if user.first_name or user.last_name:
            fullname = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not fullname and user.username:
            fullname = user.username if user.username.startswith("@") else f"@{user.username}"

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
        return await message.answer(
            with_cancel_hint("Telefon raqamini kiriting:"),
            reply_markup=get_admin_cancel_kb(),
        )

    data = await state.get_data()
    tg_id = data.get("tg_id")
    admin_fullname = data.get("admin_fullname")
    username = data.get("username")

    if not tg_id:
        await state.clear()
        return await message.answer(
            "Ma'lumotlar topilmadi. Qayta boshlang.",
            reply_markup=get_admin_inline_actions_kb(),
        )

    async with async_session() as session:
        existing = await session.execute(select(Admins).where(Admins.tg_id == tg_id))
        if existing.scalars().first():
            await state.clear()
            return await message.answer(
                "Admin allaqachon mavjud.",
                reply_markup=get_admin_inline_actions_kb(),
            )

        new_admin = Admins(
            tg_id=tg_id,
            admin_fullname=admin_fullname,
            phone=phone,
            username=username,
        )
        session.add(new_admin)
        await session.commit()

    await state.clear()
    await message.answer(
        "Admin muvaffaqiyatli qo'shildi ✅",
        reply_markup=get_admin_inline_actions_kb(),
    )
