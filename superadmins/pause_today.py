# superadmins/pause_today.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from sqlalchemy import update, select, and_
from datetime import date

from sql.db import async_session
from sql.models import Barbers, Order, Services
from .superadmin import get_barber_by_tg_id
from .superadmin_buttons import get_pause_cancel_keyboard, get_pause_confirm_keyboard

router = Router()


class PauseTodayState(StatesGroup):
    waiting_for_apology = State()


# ====== Inline keyboard: buyurtmalarni bekor qilish ======
def get_pause_reject_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📨 Buyurtmalarni bekor qilish", callback_data="barber_pause_reject")]
        ]
    )


# ====== Helper: bugungi buyurtmalar + xizmat nomlari ======
async def _get_today_orders_with_services(barber_id_str: str):
    today = date.today()
    async with async_session() as session:
        res = await session.execute(
            select(Order).where(
                and_(
                    Order.barber_id == barber_id_str,
                    Order.date == today
                )
            ).order_by(Order.time.asc())
        )
        orders = res.scalars().all()

        # service_id larni yig'amiz (Order.service_id string bo'lishi mumkin)
        service_ids_int = []
        for o in orders:
            try:
                service_ids_int.append(int(o.service_id))
            except Exception:
                pass

        services_map = {}
        if service_ids_int:
            srv_res = await session.execute(
                select(Services).where(Services.id.in_(list(set(service_ids_int))))
            )
            services = srv_res.scalars().all()
            services_map = {int(s.id): s.name for s in services}

    # Order.service_id -> service name
    def service_name(order: Order) -> str:
        try:
            sid = int(order.service_id)
            return services_map.get(sid, str(order.service_id))
        except Exception:
            return str(order.service_id)

    return orders, service_name


def _build_pause_confirmation_text() -> str:
    return (
        "⛔ <b>Bugungi ish rejimini to'xtatish</b>\n\n"
        "Bugun uchun qabulni vaqtincha yopmoqchimisiz?\n"
        "Tasdiqlasangiz, tizim bugungi navbatlarni tekshiradi va keyingi bosqichni ochadi.\n"
        "Bekor qilsangiz, hozirgi holat o'zgarishsiz qoladi."
    )


async def _activate_pause_today(barber: Barbers):
    today = date.today()
    barber_key = str(barber.id)

    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(is_paused=True)
        )
        await session.commit()

    orders, service_name = await _get_today_orders_with_services(barber_key)

    if not orders:
        return (
            "✅ <b>Bugungi ish rejimi to'xtatildi.</b>\n\n"
            "Bugun uchun faol buyurtma topilmadi.",
            None,
        )

    lines = []
    for i, order in enumerate(orders, start=1):
        order_time = order.time.strftime("%H:%M")
        service = service_name(order)
        lines.append(f"{i}) 🕒 {order_time} - ✂️ {service}")

    text = (
        "⚠️ <b>Bugungi navbatlar aniqlandi</b>\n\n"
        f"📅 Sana: <b>{today.strftime('%d.%m.%Y')}</b>\n"
        f"📋 Faol mijozlar soni: <b>{len(orders)}</b>\n\n"
        f"{chr(10).join(lines)}\n\n"
        "Agar bugungi navbatlarni bekor qilmoqchi bo'lsangiz, pastdagi tugmani bosing.\n"
        "Keyin bitta uzr matni yuborasiz va shu matn barcha mijozlarga jo'natiladi."
    )
    return text, get_pause_reject_keyboard()


# =========================================================
# 1) "⛔️ Bugun ishlamayman" bosilganda
# =========================================================
@router.message(F.text == "⛔ Bugun ishlamayman")
async def pause_today_toggle(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    if barber.is_paused:
        await state.clear()
        return await message.answer(
            "Bugun ishga qaytasizmi?",
            reply_markup=get_pause_cancel_keyboard()
        )

    await message.answer(
        _build_pause_confirmation_text(),
        parse_mode="HTML",
        reply_markup=get_pause_confirm_keyboard()
    )


# =========================================================
# 2) Pause tasdiqlanganda yoki bekor qilinganda
# =========================================================
@router.callback_query(F.data == "barber_pause_confirm")
async def pause_today_confirm(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Xatolik!", show_alert=True)
        return

    if barber.is_paused:
        await callback.answer("Bugungi ish rejimi allaqachon to'xtatilgan.", show_alert=True)
        return

    text, reply_markup = await _activate_pause_today(barber)

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

    await callback.answer("✅ Tasdiqlandi")


@router.callback_query(F.data == "barber_pause_cancel")
async def pause_today_cancel(callback: types.CallbackQuery):
    text = (
        "⭕ <b>Jarayon bekor qilindi</b>\n\n"
        "Bugungi ish rejimi o'zgarishsiz qoldi."
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")

    await callback.answer("Bekor qilindi")


# =========================================================
# 3) Buyurtmalarni bekor qilish bosilganda -> uzr matnini so'rash
# =========================================================
@router.callback_query(F.data == "barber_pause_reject")
async def pause_reject_ask_apology(callback: types.CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Xatolik!", show_alert=True)
        return

    barber_key = str(barber.id)

    # Bugungi orders borligini tekshiramiz (bo'lmasa: hech narsa qilmaymiz)
    orders, _ = await _get_today_orders_with_services(barber_key)
    if not orders:
        await callback.answer("Bugun buyurtma yo'q.", show_alert=True)
        return

    await state.set_state(PauseTodayState.waiting_for_apology)
    await state.update_data(barber_id=barber.id)

    await callback.message.answer(
        "📝 Uzr matnini yozing.\n\n"
        "Shu matn bugungi barcha mijozlarga yuboriladi."
    )
    await callback.answer()


# =========================================================
# 4) Barber uzr matnini yozadi -> mijozlarga yuborish + orders o'chirish
# =========================================================
@router.message(PauseTodayState.waiting_for_apology)
async def pause_send_apology_and_delete_orders(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await state.clear()
        return await message.answer("❌ Siz barber sifatida topilmadingiz.")

    apology_text = (message.text or "").strip()
    if not apology_text:
        return await message.answer("Uzr matnini yozing (bo'sh bo'lmasin).")

    today = date.today()
    barber_key = str(barber.id)

    orders, service_name = await _get_today_orders_with_services(barber_key)

    # Agar buyurtmalar bo'lmasa — state tozalaymiz
    if not orders:
        await state.clear()
        return await message.answer("Bugun bekor qilinadigan buyurtma topilmadi.")

    # Mijozlarga uzr yuborish
    sent = 0
    for o in orders:
        try:
            t = o.time.strftime("%H:%M")
            srv = service_name(o)
            await message.bot.send_message(
                chat_id=o.user_id,
                text=(
                    f"⚠️ <b>Navbat bekor qilindi</b>\n\n"
                    f"📅 Sana: <b>{today.strftime('%d.%m.%Y')}</b>\n"
                    f"⏰ Vaqt: <b>{t}</b>\n"
                    f"✂️ Xizmat: <b>{srv}</b>\n\n"
                    f"{apology_text}"
                ),
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            continue

    # Orders ni o'chirish (bugungi) + barber is_paused True bo'lib qoladi
    async with async_session() as session:
        # qayta select qilib, sessionga bog'lab o'chiramiz
        res = await session.execute(
            select(Order).where(
                and_(
                    Order.barber_id == barber_key,
                    Order.date == today
                )
            )
        )
        db_orders = res.scalars().all()

        for o in db_orders:
            await session.delete(o)

        # is_paused ni True qilib qo'yib ketamiz (talabga muvofiq)
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(is_paused=True)
        )

        await session.commit()

    await state.clear()

    await message.answer(
        f"✅ Bekor qilindi.\n"
        f"📨 Xabar yuborildi: {sent}\n"
        f"🗑 O'chirildi: {len(orders)}"
    )


# =========================================================
# 5) "❌ Tugatish" bosilganda -> is_paused = False
#    Eslatma: siz bergan keyboard callback_data="barber_pause_close"
# =========================================================
@router.callback_query(F.data == "barber_pause_close")
async def pause_close(callback: types.CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    barber = await get_barber_by_tg_id(tg_id)

    if not barber:
        await callback.answer("❌ Xatolik!", show_alert=True)
        return

    # Pause ni o'chiramiz
    async with async_session() as session:
        await session.execute(
            update(Barbers)
            .where(Barbers.id == barber.id)
            .values(is_paused=False)
        )
        await session.commit()

    await state.clear()

    # xabarni edit qilib qo'yamiz (xohlasangiz delete ham qilsa bo'ladi)
    try:
        await callback.message.edit_text("✅ Bugun ishga qaytdingiz.")
    except Exception:
        pass

    await callback.answer("✅ Faollashtirildi")
