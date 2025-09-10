import re

def validate_fullname(fullname: str) -> bool:
    # Faqat harflar va bo‘shliq bo‘lishi kerak
    return bool(re.fullmatch(r"[A-Za-zʻʼ‘’`'\"-]+ [A-Za-zʻʼ‘’`'\"-]+", fullname))

def validate_phone(phone: str) -> bool:
    # Telefon raqami +998 bilan boshlanishi va 12 ta raqamdan iborat bo‘lishi kerak
    return bool(re.fullmatch(r"\+998\d{9}", phone))
