from dataclasses import dataclass
from html import escape
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sql.db_info import ensure_info_row, get_info, get_info_expanded
from sql.db_info_profile import get_info_hidden_fields
from sql.models import Info, InfoExpanded

PROFILE_TITLE = "Barbershop"


@dataclass(slots=True)
class InfoProfileSnapshot:
    info: Info
    expanded: InfoExpanded | None
    hidden_fields: set[str]


def safe_text(value) -> str:
    text = str(value or "").strip()
    return text if text else "—"


def clip_text(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def is_http_url(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def normalize_telegram(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if is_http_url(normalized):
        return normalized
    if normalized.startswith("@"):
        return f"https://t.me/{normalized[1:]}"
    if " " not in normalized and "/" not in normalized and "." not in normalized:
        return f"https://t.me/{normalized}"
    return None


def normalize_instagram(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if is_http_url(normalized):
        return normalized
    normalized = normalized.lstrip("@").strip()
    if not normalized or " " in normalized or "/" in normalized:
        return None
    return f"https://instagram.com/{normalized}"


def normalize_website(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None

    normalized = normalized.replace(" ", "")
    if "," in normalized:
        return None
    if not normalized.startswith("http://") and not normalized.startswith("https://"):
        normalized = f"https://{normalized}"
    if not re.match(r"^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$", normalized):
        return None
    return normalized


def parse_coord(value) -> float | None:
    try:
        normalized = str(value).strip()
        if not normalized:
            return None
        return float(normalized)
    except (TypeError, ValueError):
        return None


def is_hidden(snapshot: InfoProfileSnapshot, field_key: str) -> bool:
    return field_key in snapshot.hidden_fields


def get_field_raw_value(snapshot: InfoProfileSnapshot, field_key: str):
    if field_key in {"phone_number", "phone_number2"}:
        return getattr(snapshot.expanded, field_key, None) if snapshot.expanded else None
    return getattr(snapshot.info, field_key, None)


def get_field_display_value(snapshot: InfoProfileSnapshot, field_key: str) -> str:
    return safe_text(get_field_raw_value(snapshot, field_key))


def get_phone_value(snapshot: InfoProfileSnapshot, field_key: str) -> str | None:
    if field_key not in {"phone_number", "phone_number2"}:
        return None
    if is_hidden(snapshot, field_key):
        return None
    raw_value = get_field_raw_value(snapshot, field_key)
    normalized = str(raw_value or "").strip()
    return normalized or None


def get_location_coordinates(snapshot: InfoProfileSnapshot) -> tuple[float | None, float | None]:
    return (
        parse_coord(get_field_raw_value(snapshot, "latitude")),
        parse_coord(get_field_raw_value(snapshot, "longitude")),
    )


def get_display_title(snapshot: InfoProfileSnapshot) -> str:
    address = get_field_raw_value(snapshot, "address_text")
    if str(address or "").strip():
        return PROFILE_TITLE
    return PROFILE_TITLE


def _compose_region_district(snapshot: InfoProfileSnapshot) -> str | None:
    if is_hidden(snapshot, "region") and is_hidden(snapshot, "district"):
        return None

    values: list[str] = []
    if not is_hidden(snapshot, "region"):
        values.append(get_field_display_value(snapshot, "region"))
    if not is_hidden(snapshot, "district"):
        values.append(get_field_display_value(snapshot, "district"))
    return " / ".join(values) if values else None


def _build_section_lines(snapshot: InfoProfileSnapshot) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}

    if not is_hidden(snapshot, "work_time_text"):
        sections["work_time"] = [get_field_display_value(snapshot, "work_time_text")]

    address_lines: list[str] = []
    if not is_hidden(snapshot, "address_text"):
        address_lines.append(get_field_display_value(snapshot, "address_text"))
    region_district = _compose_region_district(snapshot)
    if region_district is not None:
        address_lines.append(region_district)
    if not is_hidden(snapshot, "street"):
        address_lines.append(get_field_display_value(snapshot, "street"))
    if address_lines:
        sections["address"] = address_lines

    phone_lines: list[str] = []
    if not is_hidden(snapshot, "phone_number"):
        phone_lines.append(f"📞 <b>Telefon 1:</b> {escape(get_field_display_value(snapshot, 'phone_number'))}")
    if not is_hidden(snapshot, "phone_number2"):
        phone_lines.append(f"📞 <b>Telefon 2:</b> {escape(get_field_display_value(snapshot, 'phone_number2'))}")
    if phone_lines:
        sections["phones"] = phone_lines

    online_lines: list[str] = []
    if not is_hidden(snapshot, "telegram"):
        online_lines.append(
            f"✈️ Telegram: {escape(normalize_telegram(get_field_raw_value(snapshot, 'telegram')) or get_field_display_value(snapshot, 'telegram'))}"
        )
    if not is_hidden(snapshot, "instagram"):
        online_lines.append(
            f"📷 Instagram: {escape(normalize_instagram(get_field_raw_value(snapshot, 'instagram')) or get_field_display_value(snapshot, 'instagram'))}"
        )
    if not is_hidden(snapshot, "website"):
        online_lines.append(
            f"🔗 Website: {escape(normalize_website(get_field_raw_value(snapshot, 'website')) or get_field_display_value(snapshot, 'website'))}"
        )
    if online_lines:
        sections["online"] = online_lines

    return sections


def build_info_text(snapshot: InfoProfileSnapshot) -> str:
    sections = _build_section_lines(snapshot)
    lines = [
        f"ℹ️ <b>{escape(get_display_title(snapshot))}</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    work_time = sections.get("work_time")
    if work_time:
        lines.extend(["🕒 <b>Ish vaqti</b>", *[f"• {escape(line)}" for line in work_time], ""])

    address = sections.get("address")
    if address:
        lines.extend(["📍 <b>Manzil</b>", *[f"• {escape(line)}" for line in address], ""])

    phones = sections.get("phones")
    if phones:
        lines.extend(phones + [""])

    online = sections.get("online")
    if online:
        lines.extend(["🌐 <b>Onlayn aloqa</b>", *online])

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def build_venue_address(snapshot: InfoProfileSnapshot) -> str:
    sections = _build_section_lines(snapshot)
    lines: list[str] = []
    for line in sections.get("address", []):
        if line != "—":
            lines.append(line)
    if sections.get("work_time"):
        work_time_value = sections["work_time"][0]
        if work_time_value != "—":
            lines.append(f"Ish vaqti: {work_time_value}")
    if not lines:
        lines.append("Manzil")
    return clip_text("\n".join(lines), 240)


def build_social_link_rows(
    snapshot: InfoProfileSnapshot,
    *,
    include_website: bool = True,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []

    if not is_hidden(snapshot, "telegram"):
        telegram_url = normalize_telegram(get_field_raw_value(snapshot, "telegram"))
        if telegram_url:
            rows.append([InlineKeyboardButton(text="✈️ Telegram", url=telegram_url)])

    if not is_hidden(snapshot, "instagram"):
        instagram_url = normalize_instagram(get_field_raw_value(snapshot, "instagram"))
        if instagram_url:
            rows.append([InlineKeyboardButton(text="📷 Instagram", url=instagram_url)])

    if include_website and not is_hidden(snapshot, "website"):
        website_url = normalize_website(get_field_raw_value(snapshot, "website"))
        if website_url:
            rows.append([InlineKeyboardButton(text="🌐 Website", url=website_url)])

    return rows


def build_public_info_keyboard(
    snapshot: InfoProfileSnapshot,
    *,
    is_venue: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if not is_venue:
        rows.append(
            [InlineKeyboardButton(text="📍 Manzilni xaritada ko‘rish", callback_data="contact:map")]
        )
    else:
        rows.append([InlineKeyboardButton(text="🗺 Xarita ochiq", callback_data="contact:map")])

    phone_one = get_phone_value(snapshot, "phone_number")
    if phone_one:
        rows.append([InlineKeyboardButton(text="📞 1-raqamni yuborish", callback_data="contact:send_phone1")])

    phone_two = get_phone_value(snapshot, "phone_number2")
    if phone_two:
        rows.append([InlineKeyboardButton(text="📞 2-raqamni yuborish", callback_data="contact:send_phone2")])

    rows.extend(build_social_link_rows(snapshot))
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="contact:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def get_info_profile_snapshot() -> InfoProfileSnapshot:
    await ensure_info_row()
    info = await get_info()
    expanded = await get_info_expanded()
    hidden_fields = set(await get_info_hidden_fields())
    return InfoProfileSnapshot(
        info=info if info is not None else Info(id=1),
        expanded=expanded,
        hidden_fields=hidden_fields,
    )
