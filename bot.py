#bot.py
import asyncio
from aiogram import Bot, Dispatcher, F
from config import BOT_TOKEN
from utils.logger import setup_logger
from admins import router as admins_router
from superadmins import router as barber_router
from sql.db import init_db
#kere bopqoldi
# from utils.get_file_id import router as fileid_router
from handlers import (
    start,
    services,
    barbers,
    info,
    booking,
    back,
    support,
)
from handlers.main_btn_handle import router as main_btn_router

# Bot va Dispatcher obyektlari
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# dp.message.register(
#     start.start_handler,
#     CommandStart()
# )


"""startda chiqarish kerak bo'lgan video yuborilganda
uni file_id to'kenini yuborib beradigan kod"""
# dp.include_router(fileid_router)

dp.include_router(start.router)

#ADMIN_PANEL
dp.include_router(admins_router)

#BARBER PANEL
dp.include_router(barber_router)

#SUPPORT_PANEL
dp.include_router(support.router)

# Xizmatlarni ko‘rsatish
dp.callback_query.register(
    services.show_services,
    lambda c: c.data == "services"
)

# ✅ Services Next / Prev
dp.callback_query.register(
    services.navigate_services,
    lambda c: c.data.startswith(("services_next_", "services_prev_"))
)

# ✅ Service orqali booking boshlash
dp.callback_query.register(
    booking.start_booking_from_service,
    lambda c: c.data.startswith("book_service_")
)

# Ustalarni ko‘rsatish
dp.callback_query.register(
    barbers.show_barbers,
    lambda c: c.data == "barbers"
)

# Next / Prev
dp.callback_query.register(
    barbers.navigate_barbers,
    lambda c: c.data.startswith(("barber_next_", "barber_prev_"))
)


# Bog‘lanish uchun
dp.include_router(info.router)


dp.callback_query.register(
    booking.start_booking_from_barber,
    lambda c: c.data.startswith("book_barber_")
)


dp.callback_query.register(
    booking.start_booking,
    lambda c: c.data == "book"
)

dp.callback_query.register(
    booking.booking_for_me_callback,
    lambda c: c.data == "booking_for_me"
)

dp.callback_query.register(
    booking.booking_for_other_callback,
    lambda c: c.data == "booking_for_other"
)

dp.include_router(main_btn_router)

# FSM - Xizmat tanlash
dp.callback_query.register(
    booking.booking_service_nav,
    booking.UserState.waiting_for_service,
    F.data.startswith("booksrv_next_")
)

dp.callback_query.register(
    booking.booking_service_nav,
    booking.UserState.waiting_for_service,
    F.data.startswith("booksrv_prev_")
)

dp.callback_query.register(
    booking.booking_service_pick,
    booking.UserState.waiting_for_service,
    F.data.startswith("booksrv_pick_")
)

dp.callback_query.register(
    booking.book_step1,
    booking.UserState.waiting_for_service,
    F.data.startswith("service_")
)

# FSM - Usta tanlash
dp.callback_query.register(
    booking.booking_barber_nav,
    booking.UserState.waiting_for_barber,
    F.data.startswith("bookbar_next_")
)

dp.callback_query.register(
    booking.booking_barber_nav,
    booking.UserState.waiting_for_barber,
    F.data.startswith("bookbar_prev_")
)

dp.callback_query.register(
    booking.booking_barber_pick,
    booking.UserState.waiting_for_barber,
    F.data.startswith("bookbar_pick_")
)

dp.callback_query.register(
    booking.book_step2,
    booking.UserState.waiting_for_barber,
    F.data.regexp(r"^barber_\d+_\d+$")
)

# FSM - Sana tanlash
dp.callback_query.register(
    booking.book_step3,
    booking.UserState.waiting_for_date,
    F.data.startswith("date_")
)

# FSM - Sana tanlash (orqaga)
dp.callback_query.register(
    booking.back_to_date,
    F.data.startswith("back_date_")
)

# FSM - Tasdiqlash
dp.callback_query.register(
    booking.confirm,
    booking.UserState.waiting_for_time,
    F.data.startswith("confirm_")
)

# Orqaga menyuga qaytish
dp.callback_query.register(
    back.back_to_menu,
    lambda c: c.data == "back"
)

# FSM - Booking bekor qilish (/cancel)
BOOKING_CANCEL_STATES = (
    booking.UserState.waiting_for_fullname,
    booking.UserState.waiting_for_phonenumber,
    booking.UserState.waiting_for_service,
    booking.UserState.waiting_for_barber,
    booking.UserState.waiting_for_date,
    booking.UserState.waiting_for_time,
)

for booking_state in BOOKING_CANCEL_STATES:
    dp.message.register(
        booking.cancel_booking,
        booking_state,
        F.text.startswith("/cancel"),
    )

# FSM - To‘liq ism qadam
dp.message.register(
    booking.process_fullname,
    booking.UserState.waiting_for_fullname
)

# FSM - Telefon raqami qadam
dp.message.register(
    booking.process_phonenumber,
    booking.UserState.waiting_for_phonenumber
)

dp.message.register(
    booking.book_step3_message,
    booking.UserState.waiting_for_date
)

# Asosiy ishga tushirish
async def main():
    setup_logger()
    await init_db()
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
