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

    # Takrorlanmasligi uchun tekshiramiz
    if any(u["phone"] == user_data["phone"] for u in data):
        return

    data.append(user_data)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)