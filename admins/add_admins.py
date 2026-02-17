# admins/add_admins.py
from aiogram import Router, types, F
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, or_

from sql.db import async_session
from sql.models import Admins, OrdinaryUser
from .admin_buttons import (
    ADMIN_MENU_TEXT,
    ADMIN_ADD_CB,
    ADMIN_CANCEL_CB,
    get_admin_inline_actions_kb,
    get_admin_cancel_kb,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


class AdminManageState(StatesGroup):
    adding_lookup = State()
    adding_phone = State()


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
    await message.answer("Admin bo'limi:", reply_markup=get_admin_inline_actions_kb())


@router.callback_query(F.data == ADMIN_ADD_CB)
async def start_add_admin(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminManageState.adding_lookup)
    await callback.message.answer(
        with_cancel_hint("Adminning to'liq ismini yoki @username ni kiriting:"),
        reply_markup=get_admin_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == ADMIN_CANCEL_CB)
async def admin_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Admin bo'limi:", reply_markup=get_admin_inline_actions_kb())
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
            # single token: avval username, keyin first_name, so'ng last_name
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
