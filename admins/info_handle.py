# admins/info_handle.py
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from sql.db import async_session
from sql.models import Admins
from sql.db_contacts import ensure_info_row, get_info, update_info_field

router = Router()


class InfoEditState(StatesGroup):
    waiting_value = State()


EDITABLE_FIELDS = [
    ("telegram", "✈️ Telegram"),
    ("instagram", "📷 Instagram"),
    ("website", "🌐 Website"),
    ("region", "🗺️ Viloyat/Shahar"),
    ("district", "🏙️ Tuman"),
    ("street", "🛣️ Ko'cha/Manzil"),
    ("address_text", "📍 Manzil (matn)"),
    ("work_time_text", "🕒 Ish vaqti"),
    ("location", "📌 Lokatsiya (xarita)"),  # virtual field: lat/lon
]


def _edit_keyboard() -> types.InlineKeyboardMarkup:
    kb = []
    for field, title in EDITABLE_FIELDS:
        kb.append([types.InlineKeyboardButton(text=title, callback_data=f"info_edit:{field}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Ortga", callback_data="info_back")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)


async def _is_admin(message: types.Message) -> bool:
    tg_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(Admins).where(Admins.tg_id == tg_id))
        return res.scalars().first() is not None


async def _is_admin_cb(callback: types.CallbackQuery) -> bool:
    tg_id = callback.from_user.id
    async with async_session() as session:
        res = await session.execute(select(Admins).where(Admins.tg_id == tg_id))
        return res.scalars().first() is not None


def _info_preview_text(info) -> str:
    def v(x):
        return x if x not in (None, "", "None") else "—"

    lat = v(info.latitude)
    lon = v(info.longitude)

    return (
        "ℹ️ Kontakt/Info sozlamalari:\n\n"
        f"✈️ Telegram: {v(info.telegram)}\n"
        f"📷 Instagram: {v(info.instagram)}\n"
        f"🌐 Website: {v(info.website)}\n\n"
        f"🗺️ Viloyat/Shahar: {v(info.region)}\n"
        f"🏙️ Tuman: {v(info.district)}\n"
        f"🛣️ Ko'cha/Manzil: {v(info.street)}\n"
        f"📍 Manzil (matn): {v(info.address_text)}\n\n"
        f"📌 Lokatsiya: {lat}, {lon}\n"
        f"🕒 Ish vaqti: {v(info.work_time_text)}\n"
    )


@router.message(F.text.in_(["ℹ️ Kontakt/Info kiritish", "✏️ Kontakt/Info tahrirlash"]))
async def open_info_editor(message: types.Message):
    if not await _is_admin(message):
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")

    await ensure_info_row()
    info = await get_info()
    await message.answer(_info_preview_text(info), reply_markup=_edit_keyboard())


@router.callback_query(F.data == "info_back")
async def info_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    info = await get_info()
    await callback.message.edit_text(_info_preview_text(info), reply_markup=_edit_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("info_edit:"))
async def choose_field(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin_cb(callback):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    field = callback.data.split(":", 1)[1]
    await state.clear()

    if field == "location":
        await state.update_data(field="location")
        await state.set_state(InfoEditState.waiting_value)
        await callback.message.edit_text(
            "📌 Lokatsiyani yuboring:\n\n"
            "1) Telegram Location yuboring (📎 → Location)\n"
            "yoki\n"
            "2) Matn ko'rinishida: lat,lon (masalan: 41.3111,69.2797)",
            reply_markup=_edit_keyboard()
        )
        await callback.answer()
        return

    await state.update_data(field=field)
    await state.set_state(InfoEditState.waiting_value)

    # Field nomini chiroyli chiqarish
    title = next((t for f, t in EDITABLE_FIELDS if f == field), field)

    await callback.message.edit_text(
        f"{title} uchun yangi qiymat yuboring:\n\n"
        "Bekor qilish uchun: /cancel",
        reply_markup=_edit_keyboard()
    )
    await callback.answer()


@router.message(InfoEditState.waiting_value)
async def set_field_value(message: types.Message, state: FSMContext):
    if not await _is_admin(message):
        await state.clear()
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")

    data = await state.get_data()
    field = data.get("field")

    if not field:
        await state.clear()
        return await message.answer("⚠️ Xatolik: maydon topilmadi.")

    # /cancel
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        info = await get_info()
        return await message.answer(_info_preview_text(info), reply_markup=_edit_keyboard())

    # location: either message.location or "lat,lon"
    if field == "location":
        lat = None
        lon = None

        if message.location:
            lat = float(message.location.latitude)
            lon = float(message.location.longitude)
        else:
            if not message.text:
                return await message.answer("⚠️ Lokatsiya yuboring yoki lat,lon ko'rinishida yozing.")
            raw = message.text.replace(" ", "")
            if "," not in raw:
                return await message.answer("⚠️ Format xato. Masalan: 41.3111,69.2797")
            a, b = raw.split(",", 1)
            try:
                lat = float(a)
                lon = float(b)
            except ValueError:
                return await message.answer("⚠️ Format xato. Masalan: 41.3111,69.2797")

        await update_info_field("latitude", lat)
        await update_info_field("longitude", lon)

        await state.clear()
        info = await get_info()
        return await message.answer("✅ Lokatsiya saqlandi.\n\n" + _info_preview_text(info), reply_markup=_edit_keyboard())

    # other fields: plain text
    value = (message.text or "").strip()
    await update_info_field(field, value)

    await state.clear()
    info = await get_info()
    await message.answer("✅ Ma'lumot saqlandi.\n\n" + _info_preview_text(info), reply_markup=_edit_keyboard())
