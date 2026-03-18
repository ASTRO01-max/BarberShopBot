# admins/add_service.py
from html import escape

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
    SERVICE_ADD_TEXT,
    SERVICE_DEL_CB,
    SERVICE_DEL_TEXT,
    SERVICE_MENU_TEXT,
)

router = Router()

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."
SERVICE_NAV_PREFIX = "admsrv"
SERVICE_DELETE_PICK_PREFIX = "service:delete:pick"
SERVICE_DELETE_CONFIRM_PREFIX = "service:delete:confirm"
SERVICE_DELETE_CANCEL_PREFIX = "service:delete:cancel"
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
                types.InlineKeyboardButton(
                    text=SERVICE_ADD_TEXT,
                    callback_data=SERVICE_ADD_CB,
                ),
                types.InlineKeyboardButton(
                    text=SERVICE_DEL_TEXT,
                    callback_data=f"{SERVICE_DELETE_PICK_PREFIX}:{index}",
                ),
            ],
        ]
    )


def _service_delete_confirmation_keyboard(
    service_id: int,
    index: int,
) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"{SERVICE_DELETE_CONFIRM_PREFIX}:{service_id}:{index}",
                ),
                types.InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=f"{SERVICE_DELETE_CANCEL_PREFIX}:{index}",
                ),
            ]
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
        service = (
            await session.execute(
                select(Services)
                .order_by(Services.id.asc())
                .limit(SERVICE_PAGE_SIZE)
                .offset(offset)
            )
        ).scalar_one_or_none()

    return total, normalized_index, service


def _render_service_summary(service: Services) -> str:
    service_name = (service.name or "").strip() or "Noma'lum xizmat"
    emoji = SERVICE_EMOJIS.get(service_name, "🔹")
    safe_name = escape(service_name)
    safe_duration = escape(str(service.duration or "-"))
    price_text = str(service.price if service.price is not None else "-")

    return (
        f"{emoji} <b>{safe_name}</b>\n"
        f"💵 <b>Narx:</b> {price_text} so'm\n"
        f"🕒 <b>Davomiyligi:</b> {safe_duration}"
    )


def _render_service_page_text(total: int, index: int, service: Services | None) -> str:
    if total <= 0 or service is None:
        return (
            "💈 <b>Xizmatlar ro'yxati</b>\n\n"
            "⚠️ <i>Hozircha xizmatlar mavjud emas.</i>\n\n"
            "📌 <i>(0 / 0)</i>"
        )

    return (
        "💈 <b>Xizmatlar ro'yxati</b>\n\n"
        f"{_render_service_summary(service)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


def _render_delete_confirmation_text(total: int, index: int, service: Services) -> str:
    return (
        "🗑 <b>Xizmatni o'chirish</b>\n\n"
        "Quyidagi xizmatni o'chirishni tasdiqlaysizmi?\n\n"
        f"{_render_service_summary(service)}\n\n"
        f"📌 <i>({index + 1} / {total})</i>"
    )


async def _edit_or_send_service_message(
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


async def _show_service_page_message(
    message: types.Message,
    index: int = 0,
    total: int | None = None,
) -> None:
    total, index, service = await _fetch_service_page(index, total=total)
    await message.answer(
        _render_service_page_text(total, index, service),
        parse_mode="HTML",
        reply_markup=_service_nav_keyboard(index),
    )


async def _show_service_page_callback(
    callback: types.CallbackQuery,
    index: int = 0,
    total: int | None = None,
    notice: str | None = None,
) -> None:
    total, index, service = await _fetch_service_page(index, total=total)
    text = _render_service_page_text(total, index, service)
    if notice:
        text = f"{notice}\n\n{text}"

    await _edit_or_send_service_message(
        callback,
        text=text,
        reply_markup=_service_nav_keyboard(index),
    )


async def _start_add_service(message: types.Message | None, state: FSMContext) -> None:
    if message is None:
        return

    await state.clear()
    await state.set_state(AdminStates.adding_service)
    await message.answer(with_cancel_hint("📝 Yangi xizmat nomini kiriting:"))


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


@router.callback_query(F.data == SERVICE_ADD_CB)
async def add_service_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_add_service(callback.message, state)


@router.callback_query(F.data == SERVICE_DEL_CB)
async def open_service_page_for_legacy_delete(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_service_page_callback(callback, index=0)
    await callback.answer(
        "Kerakli xizmatni ochib, shu sahifadan o'chirishni tasdiqlang.",
        show_alert=True,
    )


@router.message(F.text == SERVICE_ADD_TEXT)
async def add_service_prompt(message: types.Message, state: FSMContext):
    await _start_add_service(message, state)


@router.callback_query(F.data.startswith(f"{SERVICE_DELETE_PICK_PREFIX}:"))
async def ask_service_delete_confirmation(callback: types.CallbackQuery, state: FSMContext):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await state.clear()
    total, index, service = await _fetch_service_page(index)
    if service is None:
        await callback.answer("O'chirish uchun xizmat topilmadi.", show_alert=True)
        await _show_service_page_callback(callback, index=0, total=0)
        return

    await _edit_or_send_service_message(
        callback,
        text=_render_delete_confirmation_text(total, index, service),
        reply_markup=_service_delete_confirmation_keyboard(service.id, index),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SERVICE_DELETE_CANCEL_PREFIX}:"))
async def cancel_service_delete(callback: types.CallbackQuery):
    try:
        index = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    await _show_service_page_callback(callback, index=index)
    await callback.answer("O'chirish bekor qilindi.")


@router.callback_query(F.data.startswith(f"{SERVICE_DELETE_CONFIRM_PREFIX}:"))
async def confirm_service_delete(callback: types.CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    try:
        service_id = int(parts[3])
        index = int(parts[4])
    except ValueError:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    async with async_session() as session:
        service = await session.get(Services, service_id)
        if service is None:
            await callback.answer("Xizmat topilmadi.", show_alert=True)
            await _show_service_page_callback(callback, index=index)
            return

        deleted_name = service.name
        await session.delete(service)
        await session.commit()

    remaining_total = await _count_services()
    next_index = 0 if remaining_total <= 0 else min(index, remaining_total - 1)

    await _show_service_page_callback(
        callback,
        index=next_index,
        total=remaining_total,
        notice=f"✅ <b>{escape(deleted_name)}</b> xizmati o'chirildi.",
    )
    await callback.answer("Xizmat o'chirildi.", show_alert=True)


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
    await message.answer("❌ Jarayon bekor qilindi.")
    await _show_service_page_message(message, index=0)


@router.message(StateFilter(AdminStates.adding_service))
async def save_service_name(message: types.Message, state: FSMContext):
    service_name = (message.text or "").strip()
    if not service_name:
        await message.answer(with_cancel_hint("❌ Xizmat nomi bo'sh bo'lmasligi kerak. Qayta kiriting:"))
        return

    async with async_session() as session:
        result = await session.execute(
            select(Services).where(Services.name.ilike(service_name))
        )
        existing = result.scalar_one_or_none()

    if existing:
        await message.answer(
            with_cancel_hint("⚠️ Bunday xizmat allaqachon mavjud. Boshqa nom kiriting:")
        )
        return

    await state.update_data(service_name=service_name)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer(with_cancel_hint("💵 Xizmat narxini kiriting (so'mda, faqat raqam):"))


@router.message(StateFilter(AdminStates.adding_service_price))
async def save_service_price(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer(
            with_cancel_hint("❌ Narx faqat raqam bo'lishi kerak. Qayta kiriting:")
        )
        return

    price = int(text)
    if price > INT32_MAX:
        await message.answer(
            with_cancel_hint(
                f"❌ Narx juda katta. Maksimal qiymat: {INT32_MAX}. Qayta kiriting:"
            )
        )
        return

    await state.update_data(price=price)
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer(
        with_cancel_hint("🕒 Xizmat davomiyligini kiriting (masalan: 30 daqiqa):")
    )


@router.message(StateFilter(AdminStates.adding_service_duration))
async def save_service_duration(message: types.Message, state: FSMContext):
    duration = (message.text or "").strip()
    if not duration:
        await message.answer(
            with_cancel_hint("❌ Davomiylik bo'sh bo'lmasligi kerak. Qayta kiriting:")
        )
        return

    await state.update_data(duration=duration)

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📸 Rasm qo'shaman",
                    callback_data="add_service_photo_yes",
                ),
                types.InlineKeyboardButton(
                    text="➡️ Rasm kerak emas",
                    callback_data="add_service_photo_no",
                ),
            ]
        ]
    )

    await state.set_state(AdminStates.adding_service_photo)
    await message.answer(
        with_cancel_hint("Xizmat uchun rasm qo'shasizmi?"),
        reply_markup=markup,
    )


@router.callback_query(
    F.data == "add_service_photo_no",
    StateFilter(AdminStates.adding_service_photo),
)
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

    if call.message:
        await call.message.answer(
            "✅ <b>Yangi xizmat qo'shildi!</b>\n\n"
            f"{emoji} <b>{escape(data['service_name'])}</b>\n"
            f"💵 Narxi: <b>{data['price']}</b> so'm\n"
            f"🕒 Davomiyligi: <b>{escape(data['duration'])}</b>\n"
            "📸 Rasm: <i>Yo'q</i>",
            parse_mode="HTML",
        )

    await state.clear()
    await call.answer()


@router.callback_query(
    F.data == "add_service_photo_yes",
    StateFilter(AdminStates.adding_service_photo),
)
async def ask_service_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AdminStates.adding_service_photo)
    if call.message:
        await call.message.answer(with_cancel_hint("📸 Iltimos, xizmat rasmini yuboring."))


@router.message(StateFilter(AdminStates.adding_service_photo), F.photo)
async def add_service_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()

    if not data.get("service_name") or not data.get("price") or not data.get("duration"):
        await message.answer(
            with_cancel_hint("❌ Xizmat ma'lumotlari topilmadi. Qayta boshlang.")
        )
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
        f"{emoji} <b>{escape(data['service_name'])}</b>\n"
        f"💵 Narxi: <b>{data['price']}</b> so'm\n"
        f"🕒 Davomiyligi: <b>{escape(data['duration'])}</b>\n"
        "📸 Rasm: <i>mavjud</i>",
        parse_mode="HTML",
    )

    await state.clear()


@router.message(StateFilter(AdminStates.adding_service_photo))
async def expected_photo_or_choice(message: types.Message):
    await message.answer(
        with_cancel_hint(
            "❌ Iltimos, rasm yuboring yoki rasm tanlash tugmalaridan foydalaning."
        )
    )
