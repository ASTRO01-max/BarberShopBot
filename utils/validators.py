#utils/validators.py
import re
from datetime import datetime, timedelta

INT32_MAX = 2_147_483_647

OY_NOMLARI = {
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
    "may": 5,
    "iyun": 6,
    "iyul": 7,
    "avgust": 8,
    "sentabr": 9,
    "sentyabr": 9,
    "oktabr": 10,
    "oktyabr": 10,
    "noyabr": 11,
    "dekabr": 12,
}

TABIIY_KUNLAR = {
    "bugun": 0,
    "ertaga": 1,
    "indin": 2,
}

HAFTA_KUNLARI = (
    "dushanba",
    "seshanba",
    "chorshanba",
    "payshanba",
    "juma",
    "shanba",
    "yakshanba",
)


def validate_fullname(fullname: str) -> bool:
    name_part = r"[A-Za-z\u00C0-\u024F\u02BB\u02BC\u2019'`-]+"
    pattern = rf"{name_part} {name_part}"
    return bool(re.fullmatch(pattern, fullname.strip()))


def validate_phone(phone: str) -> bool:
    return bool(re.fullmatch(r"\+998\d{9}", phone))


def normalize_text(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace("С‘", "yo")
        .replace("Р№РёР»", "")
        .replace("РіРѕРґР°", "")
    )


def parse_int_safe(val):
    try:
        return int(val)
    except Exception:
        return None


def is_int32(value: int) -> bool:
    try:
        return isinstance(value, int) and -2_147_483_648 <= value <= INT32_MAX
    except Exception:
        return False


def _validate_and_format(day, month, year) -> str | None:
    if not (day and month and year):
        return None

    try:
        parsed_date = datetime(year, month, day)
    except ValueError:
        return None

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if parsed_date < now:
        return None

    return parsed_date.strftime("%Y-%m-%d")


def _try_parse_numeric_date(
    text: str,
    *,
    reference: datetime,
    same_month_only: bool,
) -> str | None:
    normalized = text.replace(".", "-").replace("/", "-")

    iso_match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = int(iso_match.group(3))
        parsed = _validate_and_format(day, month, year)
        if parsed is None:
            return None
        if same_month_only and month != reference.month:
            return None
        return parsed

    compact_match = re.fullmatch(r"(\d{1,2})-(\d{1,2})(?:-(\d{2,4}))?", normalized)
    if not compact_match:
        return None

    day = int(compact_match.group(1))
    month = int(compact_match.group(2))
    year_token = compact_match.group(3)
    if year_token is None:
        year = reference.year
    else:
        year = int(year_token)
        if year < 100:
            year += 2000

    parsed = _validate_and_format(day, month, year)
    if parsed is None:
        return None
    if same_month_only and month != reference.month:
        return None
    return parsed


def parse_future_date(
    raw_text: str,
    *,
    same_month_only: bool = False,
    reference: datetime | None = None,
) -> str | None:
    text = normalize_text(raw_text)
    if not text:
        return None

    now = reference or datetime.now()

    if text in TABIIY_KUNLAR:
        target = now + timedelta(days=TABIIY_KUNLAR[text])
        if same_month_only and target.month != now.month:
            return None
        return target.strftime("%Y-%m-%d")

    numeric_date = _try_parse_numeric_date(
        text,
        reference=now,
        same_month_only=same_month_only,
    )
    if numeric_date is not None:
        return numeric_date

    for weekday in HAFTA_KUNLARI:
        text = text.replace(weekday, "")

    cleaned_text = (
        text.replace(",", " ")
        .replace("-", " ")
        .replace("/", " ")
    )
    cleaned_text = " ".join(cleaned_text.split())
    if not cleaned_text:
        return None

    parts = cleaned_text.split()
    if not parts:
        return None

    day = parse_int_safe(parts[0])
    if not day or not (1 <= day <= 31):
        return None

    month = None
    if len(parts) >= 2:
        month_token = parts[1].strip(" .")
        if month_token.isdigit():
            month = int(month_token)
        else:
            month = OY_NOMLARI.get(month_token.lower())

    if month is None:
        return None

    if same_month_only and month != now.month:
        return None

    if len(parts) >= 3 and parts[2].isdigit():
        year = int(parts[2])
        if year < 100:
            year += 2000
    else:
        year = now.year

    try:
        target_date = datetime(year, month, day)
    except ValueError:
        return None

    if target_date.date() < now.date():
        return None

    return target_date.strftime("%Y-%m-%d")


def parse_user_date(raw_text: str) -> str | None:
    return parse_future_date(raw_text, same_month_only=True)


def parse_user_time(raw_text: str) -> str | None:
    text = normalize_text(raw_text)
    if not text:
        return None

    normalized = text.replace(".", ":")
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", normalized)
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None

    return f"{hours:02d}:{minutes:02d}"
