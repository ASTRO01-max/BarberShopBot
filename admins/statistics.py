# admins/statistics.py
import logging
from datetime import datetime
from typing import Any

from aiogram import F, Router, types
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import Barbers, Order, Services

logger = logging.getLogger(__name__)
router = Router()

STATS_MENU_TEXT = "📊 Statistika"
CB_PREFIX = "stats"
CB_BARBER_PREFIX = f"{CB_PREFIX}:barber:"
CB_BACK_TO_OVERVIEW = f"{CB_PREFIX}:overview"
CB_NO_BARBERS = f"{CB_PREFIX}:none"
LEGACY_BACK_TO_OVERVIEW = "back_to_stats"
LEGACY_NO_BARBERS = "none"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _barber_display_name(first_name: str | None, last_name: str | None) -> str:
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or "Noma'lum barber"


def _build_overall_keyboard(barbers: list[tuple[int, str | None, str | None]]) -> InlineKeyboardMarkup:
    if not barbers:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Barberlar topilmadi", callback_data=CB_NO_BARBERS)]
            ]
        )

    rows = []
    for barber_id, first_name, last_name in barbers:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💈 {_barber_display_name(first_name, last_name)}",
                    callback_data=f"{CB_BARBER_PREFIX}{barber_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=CB_BACK_TO_OVERVIEW)]
        ]
    )


def _overall_panel_text(stats: dict[str, int], now_dt: datetime) -> str:
    return (
        "📊 <b>BARBERSHOP ANALITIKA PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Real-time:</b> {now_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📅 <b>Bugungi sana:</b> {now_dt.strftime('%Y-%m-%d')}\n\n"
        f"👥 <b>Jami navbat olgan foydalanuvchilar:</b> {stats['queue_users']}\n"
        f"📦 <b>Jami buyurtmalar:</b> {stats['total_orders']}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {stats['today_orders']}\n"
        f"✅ <b>Bugungi yakunlangan:</b> {stats['today_completed']}\n"
        f"⏳ <b>Bugungi kelasi navbatlar:</b> {stats['today_upcoming']}\n"
        f"📆 <b>Umumiy kelasi navbatlar:</b> {stats['overall_upcoming']}\n\n"
        f"💈 <b>Faol barberlar:</b> {stats['active_barbers']}\n"
        f"⏸ <b>Pause barberlar:</b> {stats['paused_barbers']}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Barberni tanlang:</i>"
    )


def _barber_panel_text(
    barber_name: str,
    stats: dict[str, int],
    top_service_name: str,
    top_service_count: int,
    now_dt: datetime,
) -> str:
    if top_service_count > 0:
        top_service_text = f"{top_service_name} ({top_service_count} marta)"
    else:
        top_service_text = "Mavjud emas"

    return (
        f"💈 <b>{barber_name} – Analitika</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Real-time:</b> {now_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📦 <b>Jami buyurtmalar:</b> {stats['total_orders']}\n"
        f"📅 <b>Bugungi buyurtmalar:</b> {stats['today_orders']}\n"
        f"✅ <b>Bugungi yakunlangan:</b> {stats['today_completed']}\n"
        f"⏳ <b>Bugungi kelasi navbatlar:</b> {stats['today_upcoming']}\n"
        f"📆 <b>Umumiy kelasi navbatlar:</b> {stats['overall_upcoming']}\n"
        f"👥 <b>Unikal mijozlar:</b> {stats['unique_users']}\n"
        f"🔥 <b>Eng ko‘p olingan xizmat:</b> {top_service_text}\n"
        "━━━━━━━━━━━━━━━━━━━"
    )


async def _fetch_overall_data(now_dt: datetime) -> tuple[dict[str, int], list[tuple[int, str | None, str | None]]]:
    today = now_dt.date()
    now_time = now_dt.time()

    upcoming_condition = or_(
        Order.date > today,
        and_(Order.date == today, Order.time >= now_time),
    )

    try:
        async with async_session() as session:
            order_row = (
                await session.execute(
                    select(
                        func.count(Order.id).label("total_orders"),
                        func.count(func.distinct(Order.user_id)).label("queue_users"),
                        func.count(Order.id).filter(Order.booked_date == today).label("today_orders"),
                        func.count(Order.id)
                        .filter(and_(Order.date == today, Order.time < now_time))
                        .label("today_completed"),
                        func.count(Order.id)
                        .filter(and_(Order.date == today, Order.time >= now_time))
                        .label("today_upcoming"),
                        func.count(Order.id).filter(upcoming_condition).label("overall_upcoming"),
                    )
                )
            ).mappings().one()

            barber_row = (
                await session.execute(
                    select(
                        func.count(Barbers.id)
                        .filter(Barbers.is_paused.is_(False))
                        .label("active_barbers"),
                        func.count(Barbers.id)
                        .filter(Barbers.is_paused.is_(True))
                        .label("paused_barbers"),
                    )
                )
            ).mappings().one()

            barbers_result = await session.execute(
                select(Barbers.id, Barbers.barber_first_name, Barbers.barber_last_name).order_by(
                    func.coalesce(Barbers.barber_first_name, ""),
                    func.coalesce(Barbers.barber_last_name, ""),
                )
            )
            barbers = [
                (_safe_int(row.id), row.barber_first_name, row.barber_last_name)
                for row in barbers_result.all()
            ]
    except SQLAlchemyError:
        logger.exception("DB error when fetching overall analytics")
        raise

    stats = {
        "queue_users": _safe_int(order_row["queue_users"]),
        "total_orders": _safe_int(order_row["total_orders"]),
        "today_orders": _safe_int(order_row["today_orders"]),
        "today_completed": _safe_int(order_row["today_completed"]),
        "today_upcoming": _safe_int(order_row["today_upcoming"]),
        "overall_upcoming": _safe_int(order_row["overall_upcoming"]),
        "active_barbers": _safe_int(barber_row["active_barbers"]),
        "paused_barbers": _safe_int(barber_row["paused_barbers"]),
    }
    return stats, barbers


async def _show_overall_as_message(message: Message) -> None:
    now_dt = datetime.now()
    try:
        stats, barbers = await _fetch_overall_data(now_dt)
    except SQLAlchemyError:
        await message.answer("❌ Statistikani olishda xatolik yuz berdi.")
        return

    await message.answer(
        _overall_panel_text(stats, now_dt),
        parse_mode="HTML",
        reply_markup=_build_overall_keyboard(barbers),
    )


async def _show_overall_as_callback(callback: CallbackQuery) -> None:
    now_dt = datetime.now()
    try:
        stats, barbers = await _fetch_overall_data(now_dt)
    except SQLAlchemyError:
        await callback.answer("❌ Statistikani olishda xatolik yuz berdi.", show_alert=True)
        return

    text = _overall_panel_text(stats, now_dt)
    markup = _build_overall_keyboard(barbers)

    if callback.message:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()


@router.message(F.sticker)
async def ignore_stickers(message: types.Message):
    await message.answer("⚠️ Iltimos, stiker emas, faqat matn yuboring.")


@router.message(F.text == STATS_MENU_TEXT)
async def show_stats(message: Message):
    await _show_overall_as_message(message)


@router.callback_query(F.data.regexp(r"^(stats:barber:\d+|barber:\d+)$"))
async def barber_stats(callback: CallbackQuery):
    try:
        barber_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError, AttributeError):
        logger.warning("Invalid callback.data for barber_stats: %r", callback.data)
        await callback.answer("❌ Noto‘g‘ri barber ID.", show_alert=True)
        return

    now_dt = datetime.now()
    today = now_dt.date()
    now_time = now_dt.time()
    upcoming_condition = or_(
        Order.date > today,
        and_(Order.date == today, Order.time >= now_time),
    )

    try:
        async with async_session() as session:
            barber = await session.get(Barbers, barber_id)
            if not barber:
                await callback.answer("❌ Barber topilmadi.", show_alert=True)
                return

            barber_id_str = str(barber.id)
            row = (
                await session.execute(
                    select(
                        func.count(Order.id).label("total_orders"),
                        func.count(Order.id).filter(Order.booked_date == today).label("today_orders"),
                        func.count(Order.id)
                        .filter(and_(Order.date == today, Order.time < now_time))
                        .label("today_completed"),
                        func.count(Order.id)
                        .filter(and_(Order.date == today, Order.time >= now_time))
                        .label("today_upcoming"),
                        func.count(Order.id).filter(upcoming_condition).label("overall_upcoming"),
                        func.count(func.distinct(Order.user_id)).label("unique_users"),
                    ).where(Order.barber_id == barber_id_str)
                )
            ).mappings().one()

            top_service_row = (
                await session.execute(
                    select(
                        Order.service_id.label("service_id"),
                        func.count(Order.id).label("service_count"),
                    )
                    .where(Order.barber_id == barber_id_str)
                    .group_by(Order.service_id)
                    .order_by(func.count(Order.id).desc(), Order.service_id.asc())
                    .limit(1)
                )
            ).mappings().first()

            top_service_name = "Mavjud emas"
            top_service_count = 0
            if top_service_row:
                top_service_count = _safe_int(top_service_row["service_count"])
                raw_service_id = top_service_row["service_id"]
                top_service_name = str(raw_service_id)

                service_pk = None
                try:
                    service_pk = int(raw_service_id)
                except (TypeError, ValueError):
                    service_pk = None

                if service_pk is not None:
                    service_name = await session.scalar(
                        select(Services.name).where(Services.id == service_pk)
                    )
                    if service_name:
                        top_service_name = service_name

    except SQLAlchemyError:
        logger.exception("DB error when fetching barber analytics for barber_id=%s", barber_id)
        await callback.answer("❌ Statistikani olishda xatolik yuz berdi.", show_alert=True)
        return

    stats = {
        "total_orders": _safe_int(row["total_orders"]),
        "today_orders": _safe_int(row["today_orders"]),
        "today_completed": _safe_int(row["today_completed"]),
        "today_upcoming": _safe_int(row["today_upcoming"]),
        "overall_upcoming": _safe_int(row["overall_upcoming"]),
        "unique_users": _safe_int(row["unique_users"]),
    }

    text = _barber_panel_text(
        barber_name=_barber_display_name(barber.barber_first_name, barber.barber_last_name),
        stats=stats,
        top_service_name=top_service_name,
        top_service_count=top_service_count,
        now_dt=now_dt,
    )

    if callback.message:
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=_build_back_keyboard(),
            )
        except Exception:
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=_build_back_keyboard(),
            )
    await callback.answer()


@router.callback_query(F.data == CB_BACK_TO_OVERVIEW)
@router.callback_query(F.data == LEGACY_BACK_TO_OVERVIEW)
async def back_to_stats(callback: CallbackQuery):
    await _show_overall_as_callback(callback)


@router.callback_query(F.data == CB_NO_BARBERS)
@router.callback_query(F.data == LEGACY_NO_BARBERS)
async def none_callback(callback: CallbackQuery):
    await callback.answer("ℹ️ Hozircha barberlar mavjud emas.", show_alert=True)
