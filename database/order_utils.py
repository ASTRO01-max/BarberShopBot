# # database/order_utils.py

# import os
# import json
# from pathlib import Path

# ORDER_FILE = Path("database/orders.json")


# def load_orders() -> list:
#     """Barcha buyurtmalarni yuklaydi, xatoga chidamli."""
#     if not ORDER_FILE.exists():
#         return []
#     try:
#         with ORDER_FILE.open("r", encoding="utf-8") as f:
#             return json.load(f)
#     except (json.JSONDecodeError, FileNotFoundError):
#         return []

# def save_order(order: dict):
#     """
#     Yangi buyurtmani saqlaydi.
#     Fayl mavjud bo‘lmasa avtomatik yaratiladi.
#     """
#     orders = load_orders()

#     # ✅ Faqat kerakli maydonlarni saqlash
#     new_order = {
#         "user_id": order.get("user_id"),
#         "fullname": order.get("fullname"),
#         "phonenumber": order.get("phonenumber"),
#         "service_id": order.get("service_id"),
#         "barber_id": order.get("barber_id"),
#         "date": order.get("date"),
#         "time": order.get("time"),
#     }

#     orders.append(new_order)

#     ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
#     with ORDER_FILE.open("w", encoding="utf-8") as f:
#         json.dump(orders, f, ensure_ascii=False, indent=4)


# def get_booked_times(service_id: str, barber_id: str, date: str) -> list:
#     """
#     Berilgan xizmat, barber va sanaga tegishli band qilingan vaqtlar ro'yxatini qaytaradi.
#     """
#     orders = load_orders()
#     return [
#         order['time']
#         for order in orders
#         if order.get('service_id') == service_id and
#            order.get('barber_id') == barber_id and
#            order.get('date') == date
#     ]

# def delete_last_order_by_user(user_id):
#     if not os.path.exists(ORDER_FILE):
#         return None

#     with open(ORDER_FILE, "r", encoding="utf-8") as file:
#         try:
#             orders = json.load(file)
#         except json.JSONDecodeError:
#             return None

#     user_orders = [order for order in orders if order.get("user_id") == user_id]


#     if not user_orders:
#         return None

#     last_order = user_orders[-1]
#     orders.remove(last_order)

#     with open(ORDER_FILE, "w", encoding="utf-8") as file:
#         json.dump(orders, file, indent=4, ensure_ascii=False)

#     return last_order


