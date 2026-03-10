# admins/add_service.py
from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import func, select

from sql.db import async_session
from sql.models import Services
from utils.emoji_map import SERVICE_EMOJIS
from utils.states import AdminStates
from utils.validators import INT32_MAX
from .admin_buttons import (
    SERVICE_ADD_CB,
    SERVICE_DEL_CB,
    SERVICE_MENU_TEXT,
    get_service_inline_actions_kb,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
SERVICE_NAV_PREFIX = "admsrv"
SERVICE_PAGE_SIZE = 1


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


def _service_nav_keyboard(index: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"{SERVICE_NAV_PREFIX}_prev_{index}",
                ),
                types.InlineKeyboardButton(
                    text="➡️ Keyingi",
                    callback_data=f"{SERVICE_NAV_PREFIX}_next_{index}",
                ),
            ],
            [
                types.InlineKeyboardButton(text="➕ Servis qo'shish", callback_data=SERVICE_ADD_CB),
                types.InlineKeyboardButton(text="➖ Servis o'chirish", callback_data=SERVICE_DEL_CB),
            ],
        ]
    )


async def _count_services() -> int:
    async with async_session() as session:
        total = await session.scalar(select(func.count(Services.id)))
    return int(total or 0)


async def _fetch_service_page(index: int, total: int | None = None):
    if total is None:
        total = await _count_services()
    if total <= 0:
        return 0, 0, None

    normalized_index = index % total
    offset = normalized_index * SERVICE_PAGE_SIZE

    async with async_session() as session:
        row = (
            await session.execute(
                select(
                    Services.name,
                    Services.price,
                    Services.duration,
                )
                .order_by(Services.id.asc())
                .limit(SERVICE_PAGE_SIZE)
                .offset(offset)
            )
        ).first()

    return total, normalized_index, row


def _render_service_page_text(total: int, index: int, row) -> str:
    if total <= 0 or not row:
        return (
            "💈 <b>Xizmatlar ro'yxati</b>\n\n"
            "⚠️ <i>Hozircha xizmatlar mavjud emas.</i>\n\n"
            "📌 <i>(0 / 0)</i>"
        )

    name, price, duration = row
    service_name = (name or "").strip() or "Noma'lum xizmat"
    emoji = SERVICE_EMOJIS.get(service_name, "🔹")
    price_text = str(price if price is not None else "-")

    return (
        "💈 <b>Xizmatlar ro'yxati</b>\n\n"
        f"{emoji} <b>{service_name}</b>\n"
        f"💵 <b>Narx:</b> {price_text} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {duration or '-'}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _show_service_page_message(
    message: types.Message,
    index: int = 0,
    total: int | None = None,
) -> None:
    total, index, row = await _fetch_service_page(index, total=total)
    await message.answer(
        _render_service_page_text(total, index, row),
        parse_mode="HTML",
        reply_markup=_service_nav_keyboard(index),
    )


async def _show_service_page_callback(
    callback: types.CallbackQuery,
    index: int = 0,
    total: int | None = None,
) -> None:
    if not callback.message:
        return

    total, index, row = await _fetch_service_page(index, total=total)
    text = _render_service_page_text(total, index, row)
    keyboard = _service_nav_keyboard(index)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{SERVICE_NAV_PREFIX}_"))
async def service_pagination_nav(callback: types.CallbackQuery):
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

    total = await _count_services()
    if total > 0:
        if action == "next":
            index = (index + 1) % total
        else:
            index = (index - 1) % total
    else:
        index = 0

    await _show_service_page_callback(callback, index=index, total=total)
    await callback.answer()


@router.message(F.text == SERVICE_MENU_TEXT)
async def show_service_actions(message: types.Message, state: FSMContext):
    await state.clear()
    await _show_service_page_message(message, index=0)


@router.message(
    StateFilter(
        AdminStates.adding_service,
        AdminStates.adding_service_price,
        AdminStates.adding_service_duration,
        AdminStates.adding_service_photo,
    ),
    Command("cancel"),
)
async def cancel_add_service(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Jarayon bekor qilindi.",
        reply_markup=get_service_inline_actions_kb(),
    )


@router.message(F.text == "💈 Servis qo'shish")
async def add_service_prompt(message: types.Message, state: FSMContext):
    await state.clear()
    await _show_service_page_message(message, index=0)
    await state.set_state(AdminStates.adding_service)
    await message.answer(with_cancel_hint("📝 Yangi xizmat nomini kiriting:"))


@router.message(StateFilter(AdminStates.adding_service))
async def save_service_name(message: types.Message, state: FSMContext):
    service_name = message.text.strip()

    async with async_session() as session:
        result = await session.execute(select(Services).where(Services.name.ilike(service_name)))
        existing = result.scalar()

        if existing:
            await message.answer(with_cancel_hint("⚠️ Bunday xizmat allaqachon mavjud."))
            return await state.clear()

    await state.update_data(service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer(with_cancel_hint("💵 Xizmat narxini kiriting (so'mda, faqat raqam):"))


@router.message(StateFilter(AdminStates.adding_service_price))
async def save_service_price(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        return await message.answer(
            with_cancel_hint("❌ Narx faqat raqam bo'lishi kerak. Qayta kiriting:")
        )

    price = int(text)
    if price > INT32_MAX:
        return await message.answer(
            with_cancel_hint(
                f"❌ Narx juda katta. Maksimal qiymat: {INT32_MAX}. Qayta kiriting:"
            )
        )

    await state.update_data(price=price)
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer(with_cancel_hint("⏰ Xizmat davomiyligini kiriting (masalan: 30 daqiqa):"))


@router.message(StateFilter(AdminStates.adding_service_duration))
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = message.text.strip()
    await state.update_data(duration=duration)

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📸 Rasm qo‘shaman", callback_data="add_service_photo_yes"),
                types.InlineKeyboardButton(text="➡️ Rasm kerak emas", callback_data="add_service_photo_no"),
            ]
        ]
    )

    await state.set_state(AdminStates.adding_service_photo)
    await message.answer(with_cancel_hint("Xizmat uchun rasm qo‘shasizmi?"), reply_markup=markup)


@router.callback_query(F.data == "add_service_photo_no", StateFilter(AdminStates.adding_service_photo))
async def save_service_without_photo(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        new_service = Services(
            name=data["service_name"],
            price=data["price"],
            duration=data["duration"],
            photo=None,
        )
        session.add(new_service)
        await session.commit()

    emoji = SERVICE_EMOJIS.get(data["service_name"], "🔹")

    await call.message.answer(
        "✅ <b>Yangi xizmat qo‘shildi!</b>\n\n"
        f"{emoji} <b>{data['service_name']}</b>\n"
        f"💵 Narxi: <b>{data['price']}</b> so‘m\n"
        f"⏰ Davomiyligi: <b>{data['duration']}</b>\n"
        f"📸 Rasm: <i>Yo'q</i>",
        parse_mode="HTML",
    )

    await state.clear()
    await call.answer()


@router.callback_query(F.data == "add_service_photo_yes", StateFilter(AdminStates.adding_service_photo))
async def ask_service_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AdminStates.adding_service_photo)
    await call.message.answer(with_cancel_hint("📸 Iltimos, xizmat rasmini yuboring."))


@router.message(StateFilter(AdminStates.adding_service_photo), F.photo)
async def add_service_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()

    if not data.get("service_name") or not data.get("price") or not data.get("duration"):
        await message.answer(with_cancel_hint("❌ Xizmat ma'lumotlari topilmadi. Qayta boshlang."))
        await state.clear()
        return

    async with async_session() as session:
        new_service = Services(
            name=data["service_name"],
            price=data["price"],
            duration=data["duration"],
            photo=photo_file_id,
        )
        session.add(new_service)
        await session.commit()

    emoji = SERVICE_EMOJIS.get(data["service_name"], "🔹")

    await message.answer(
        "✅ <b>Xizmat rasm bilan saqlandi!</b>\n\n"
        f"{emoji} <b>{data['service_name']}</b>\n"
        f"💵 Narxi: <b>{data['price']}</b> so‘m\n"
        f"⏰ Davomiyligi: <b>{data['duration']}</b>\n"
        f"📸 Rasm: <i>mavjud</i>",
        parse_mode="HTML",
    )

    await state.clear()


@router.message(StateFilter(AdminStates.adding_service_photo))
async def expected_photo_or_choice(message: types.Message):
    await message.answer(
        with_cancel_hint("❌ Iltimos, rasm yuboring (📸) yoki rasm tanlash tugmalaridan foydalaning.")
    )
