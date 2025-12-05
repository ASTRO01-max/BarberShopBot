import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from utils.logger import setup_logger
from admins import router as admins_router
from sql.db import init_db

from handlers import (
    start,
    services,
    barbers,
    contact,
    booking,
    back,
    main_btn_handle,
    support,
)

# Bot va Dispatcher obyektlari
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# dp.message.register(
#     start.start_handler,
#     CommandStart()
# )

dp.include_router(start.router)

#ADMIN_PANEL
dp.include_router(admins_router)

#SUPPORT_PANEL
dp.include_router(support.router)

# Xizmatlarni ko‘rsatish
dp.callback_query.register(
    services.show_services,
    lambda c: c.data == "services"
)

# Ustalarni ko‘rsatish
dp.callback_query.register(
    barbers.show_barbers,
    lambda c: c.data == "barbers"
)

# Ustalar menyusi
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
dp.callback_query.register(
    contact.contact,
    lambda c: c.data == "contact"
)

# Buyurtma boshlash
dp.callback_query.register(
    booking.start_booking,
    lambda c: c.data == "book"
)

dp.include_router(main_btn_handle.router)

# FSM - Xizmat tanlash
dp.callback_query.register(
    booking.book_step1,
    lambda c: c.data.startswith("service_")
)

# FSM - Usta tanlash
dp.callback_query.register(
    booking.book_step2,
    lambda c: c.data.startswith("barber_")
)

# FSM - Sana tanlash
dp.callback_query.register(
    booking.book_step3,
    lambda c: c.data.startswith("date_")
)

# FSM - Tasdiqlash
dp.callback_query.register(
    booking.confirm,
    lambda c: c.data.startswith("confirm_")
)

# Orqaga menyuga qaytish
dp.callback_query.register(
    back.back_to_menu,
    lambda c: c.data == "back"
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
