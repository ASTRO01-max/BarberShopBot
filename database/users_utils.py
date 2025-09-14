import json
import os

def save_user(user_data):
    file_path = "database/users.json"
    os.makedirs("database", exist_ok=True)

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # ⚡ Telegram IDni majburiy qo‘shamiz
    tg_id = int(user_data.get("id")) if "id" in user_data else None
    if tg_id is None:
        raise ValueError("❌ save_user: 'id' qiymati berilmagan!")

    fullname = user_data.get("fullname", "Noma'lum")
    phone = user_data.get("phone", "Noma'lum")

    # Takrorlanmasligi uchun tekshiramiz
    for u in data:
        if str(u.get("id")) == str(tg_id) or u.get("phone") == phone:
            return  # user allaqachon mavjud

    # Foydalanuvchini saqlash
    data.append({
        "id": tg_id,
        "fullname": fullname,
        "phone": phone
    })

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_user(user_id):
    """Userni Telegram ID orqali olish"""
    file_path = "database/users.json"
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            users = json.load(f)
    except json.JSONDecodeError:
        return None

    return next((u for u in users if str(u.get("id")) == str(user_id)), None)


def get_user_by_phone(phone):
    """Telefon raqam orqali foydalanuvchini olish"""
    file_path = "database/users.json"
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            users = json.load(f)
    except json.JSONDecodeError:
        return None

    return next((u for u in users if u.get("phone") == phone), None)
