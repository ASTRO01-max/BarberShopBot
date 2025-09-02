import json
import os

FILE_PATH = os.path.join(os.path.dirname(__file__), "services.json")

# default xizmatlar
DEFAULT_SERVICES = {
    "haircut": ("✂️ Soch olish", 50000, "30 daqiqa"),
    "beard": ("🧔 Soqol olish", 30000, "15 daqiqa"),
    "combo": ("💎 Komplekt", 70000, "45 daqiqa")
}

# xizmatlarni yuklash
def load_services():
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, ValueError):
            # agar fayl buzilgan bo‘lsa
            pass
    # agar fayl mavjud bo‘lmasa yoki buzilgan bo‘lsa → defaultdan yozamiz
    save_services(DEFAULT_SERVICES)
    return DEFAULT_SERVICES.copy()


def save_services(data: dict):
    """Servislarni faylga saqlash"""
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# global services o‘zgaruvchisi
services = load_services()
