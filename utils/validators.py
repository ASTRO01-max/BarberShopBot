import re
from datetime import datetime, timedelta

def validate_fullname(fullname: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-zʻʼ‘’`'\"-]+ [A-Za-zʻʼ‘’`'\"-]+", fullname))

def validate_phone(phone: str) -> bool:
    return bool(re.fullmatch(r"\+998\d{9}", phone))


OY_NOMLARI = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentabr": 9, "oktabr": 10, "noyabr": 11, "dekabr": 12,
    "sentyabr": 9, "oktyabr": 10
}

TABIIY_KUNLAR = {
    "bugun": 0,
    "ertaga": 1,
    "indin": 2,
}

def normalize_text(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace("ё", "yo")
        .replace("йил", "")
        .replace("года", "")
    )

def parse_int_safe(val):
    try:
        return int(val)
    except:
        return None


def parse_user_date(raw_text: str) -> str | None:
    text = normalize_text(raw_text)

    now = datetime.now()
    current_year = now.year
    current_month = now.month

    if text in TABIIY_KUNLAR:
        target = now + timedelta(days=TABIIY_KUNLAR[text])
        if target.month != current_month:
            return None
        return target.strftime("%Y-%m-%d")

    week_words = [
        "dushanba","seshanba","chorshanba","payshanba",
        "juma","shanba","yakshanba"
    ]
    for w in week_words:
        text = text.replace(w, "")

    text = text.replace(",", " ")
    text = text.replace("-", " ")
    text = " ".join(text.split())

    parts = text.split()
    if len(parts) == 0:
        return None

    day = parse_int_safe(parts[0])
    if not day or not (1 <= day <= 31):
        return None

    month = None
    if len(parts) >= 2:
        p2 = parts[1].strip(" .")
        if p2.isdigit():
            month = int(p2)
        else:
            month = OY_NOMLARI.get(p2.lower())

    if month is None:
        return None

    if month != current_month:
        return None

    if len(parts) >= 3 and parts[2].isdigit():
        year = int(parts[2])
        if year < 100:
            year += 2000
    else:
        year = current_year

    try:
        date = datetime(year, month, day)
    except:
        return None

    if date.date() < now.date():
        return None

    return date.strftime("%Y-%m-%d")


def _validate_and_format(day, month, year) -> str | None:
    if not (day and month and year):
        return None

    try:
        date = datetime(year, month, day)
    except ValueError:
        return None

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if date < now:
        return None

    return date.strftime("%Y-%m-%d")
