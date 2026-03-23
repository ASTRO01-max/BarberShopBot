from html import escape

from sqlalchemy import select

from sql.db import async_session
from sql.db_barber_profile import get_barber_hidden_fields
from sql.models import BarberPhotos, Barbers


def barber_full_name(barber: Barbers) -> str:
    return " ".join(
        [part for part in [barber.barber_first_name, barber.barber_last_name] if part]
    ).strip() or f"Barber #{barber.id}"


def build_barber_caption(
    barber: Barbers,
    *,
    title: str | None = None,
    include_status: bool = False,
    hidden_fields: set[str] | None = None,
    position: tuple[int, int] | None = None,
) -> str:
    hidden = hidden_fields or set()
    lines: list[str] = []

    if title:
        lines.append(f"{title}\n")

    lines.append(f"\n👨‍🎤 <b>{escape(barber_full_name(barber))}</b>\n")

    if include_status:
        if getattr(barber, "is_paused", False):
            lines.append("ℹ️ <b>Holati:</b> ⛔ Bugun ishlamaydi\n")
        else:
            lines.append("ℹ️ <b>Holati:</b> 🕒 Bugun ishda\n")

    if barber.experience and "experience" not in hidden:
        lines.append(f"💼 <b>Tajriba:</b> {escape(str(barber.experience))}\n")

    if barber.work_days and "work_days" not in hidden:
        lines.append(f"📅 <b>Ish kunlari:</b> {escape(str(barber.work_days))}\n")

    if barber.work_time and "work_time" not in hidden:
        lines.append(f"⏰ <b>Ish vaqti:</b> {escape(str(barber.work_time))}\n")

    if barber.breakdown and "breakdown" not in hidden:
        lines.append(f"⏸️ <b>Tanaffus:</b> {escape(str(barber.breakdown))}\n")

    if barber.phone and "phone" not in hidden:
        lines.append(f"📞 <b>Aloqa:</b> <code>{escape(str(barber.phone))}</code>\n")

    if position:
        current, total = position
        lines.append(f"\n📌 <i>({current} / {total})</i>")

    return "".join(lines)


async def fetch_latest_barber_photo(barber_id: int) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(BarberPhotos.photo)
            .where(BarberPhotos.barber_id == barber_id)
            .order_by(BarberPhotos.id.desc())
            .limit(1)
        )
        return result.scalar()


async def get_barber_card_content(
    barber: Barbers,
    *,
    title: str | None = None,
    include_status: bool = False,
    position: tuple[int, int] | None = None,
) -> tuple[str, str | None]:
    hidden_fields = set(await get_barber_hidden_fields(barber.id))
    caption = build_barber_caption(
        barber,
        title=title,
        include_status=include_status,
        hidden_fields=hidden_fields,
        position=position,
    )
    photo = await fetch_latest_barber_photo(barber.id)
    return caption, photo
