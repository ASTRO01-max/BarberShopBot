# admins/special_message.py
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from sql.db import async_session
from sql.models import Admins, Barbers, OrdinaryUser, User
from utils.states import BroadcastState

router = Router()

SPECIAL_MSG_ADMINS_CB = "special_msg_admins"
SPECIAL_MSG_BARBERS_CB = "special_msg_barbers"
SPECIAL_MSG_ALL_CB = "special_msg_all"

SPECIAL_MSG_TARGET_LABELS = {
    SPECIAL_MSG_ADMINS_CB: "Adminlar",
    SPECIAL_MSG_BARBERS_CB: "Barberlar",
    SPECIAL_MSG_ALL_CB: "Hamma",
}


def _broadcast_target_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Adminlar uchun", callback_data=SPECIAL_MSG_ADMINS_CB)],
            [types.InlineKeyboardButton(text="Barberlar uchun", callback_data=SPECIAL_MSG_BARBERS_CB)],
            [types.InlineKeyboardButton(text="Hamma uchun", callback_data=SPECIAL_MSG_ALL_CB)],
        ]
    )


async def _is_admin(tg_id: int) -> bool:
    async with async_session() as session:
        res = await session.execute(select(Admins.tg_id).where(Admins.tg_id == tg_id))
        return res.scalar_one_or_none() is not None


async def _fetch_tg_ids(session, model) -> set[int]:
    res = await session.execute(select(model.tg_id).where(model.tg_id.isnot(None)))
    return {tg_id for (tg_id,) in res if tg_id}


async def _resolve_target_tg_ids(target: str) -> set[int]:
    async with async_session() as session:
        tg_ids = set()

        if target == SPECIAL_MSG_ADMINS_CB:
            tg_ids.update(await _fetch_tg_ids(session, Admins))
        elif target == SPECIAL_MSG_BARBERS_CB:
            tg_ids.update(await _fetch_tg_ids(session, Barbers))
        elif target == SPECIAL_MSG_ALL_CB:
            tg_ids.update(await _fetch_tg_ids(session, Admins))
            tg_ids.update(await _fetch_tg_ids(session, Barbers))
            tg_ids.update(await _fetch_tg_ids(session, User))
            tg_ids.update(await _fetch_tg_ids(session, OrdinaryUser))

        return tg_ids


@router.message(F.text == "✉️ Mahsus xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")

    await state.clear()
    await message.answer(
        "Qaysi guruhga maxsus xabar yubormoqchisiz?",
        reply_markup=_broadcast_target_kb(),
    )


@router.callback_query(
    F.data.in_(
        {
            SPECIAL_MSG_ADMINS_CB,
            SPECIAL_MSG_BARBERS_CB,
            SPECIAL_MSG_ALL_CB,
        }
    )
)
async def set_broadcast_target(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return

    target = callback.data
    await state.update_data(broadcast_target=target)
    await state.set_state(BroadcastState.waiting_for_message)

    target_label = SPECIAL_MSG_TARGET_LABELS.get(target, "Tanlangan guruh")
    await callback.answer(f"{target_label} uchun yuborish tanlandi.")
    await callback.message.answer(
        "✏️ Yubormoqchi bo'lgan xabaringizni kiriting.\n\n"
        "❌ Bekor qilish uchun /cancel yuboring."
    )


@router.message(StateFilter(BroadcastState.waiting_for_message), F.text == "/cancel")
async def cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Xabar yuborish bekor qilindi.")


@router.message(BroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        await state.clear()
        return await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")

    text = (message.text or "").strip()
    if not text:
        return await message.answer("⚠️ Iltimos, xabar matnini yuboring.")

    data = await state.get_data()
    target = data.get("broadcast_target")
    if target not in SPECIAL_MSG_TARGET_LABELS:
        await state.clear()
        return await message.answer("⚠️ Xatolik: qabul qiluvchi guruh tanlanmagan.")

    tg_ids = await _resolve_target_tg_ids(target)
    if not tg_ids:
        await state.clear()
        return await message.answer("Hech qanday foydalanuvchi topilmadi.")

    sent = 0
    failed = 0

    await message.answer("📨 Xabar yuborilmoqda, iltimos kuting...")

    for tg_id in tg_ids:
        try:
            await message.bot.send_message(chat_id=tg_id, text=text)
            sent += 1
        except Exception:
            failed += 1

    await state.clear()

    if sent == 0:
        return await message.answer("Xabar yuborilmadi.")
    if failed == 0:
        return await message.answer(f"Xabar muvaffaqiyatli yuborildi ✅\nYuborildi: {sent} ta")

    await message.answer(f"Yuborildi: {sent} ta, Xatolik: {failed} ta")
