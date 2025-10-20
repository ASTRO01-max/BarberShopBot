# #admins/statistics.py
# from aiogram import Router, types, F
# from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# from datetime import date
# from sqlalchemy import select, func, and_
# from sql.db import async_session
# from sql.models import Order, Barbers

# router = Router()

# @router.message(F.text == "📊 Statistika")
# async def show_stats(message: types.Message):
#     async with async_session() as session:
#         total_orders = await session.scalar(select(func.count(Order.id)))
#         total_users = await session.scalar(select(func.count(func.distinct(Order.user_id))))
#         today = date.today()
#         today_orders = await session.scalar(select(func.count(Order.id)).where(Order.date == today))
#         today_users = await session.scalar(
#             select(func.count(func.distinct(Order.user_id))).where(Order.date == today)
#         )
#         barbers = (await session.execute(select(Barbers))).scalars().all()

#     buttons = [
#         [InlineKeyboardButton(text=f"💈 {b.barber_fullname}", callback_data=f"barber_stats:{b.id}")]
#         for b in barbers
#     ] or [[InlineKeyboardButton(text="❌ Barberlar mavjud emas", callback_data="none")]]
    
#     markup = InlineKeyboardMarkup(inline_keyboard=buttons)

#     await message.answer(
#         f"📊 <b>Umumiy Statistika</b>\n\n"
#         f"📦 <b>Jami buyurtmalar:</b> {total_orders}\n"
#         f"👥 <b>Foydalanuvchilar soni:</b> {total_users}\n"
#         f"📅 <b>Bugungi buyurtmalar:</b> {today_orders}\n"
#         f"🙋‍♂️ <b>Bugungi foydalanuvchilar:</b> {today_users}\n\n"
#         f"💈 <b>Barberlar bo‘yicha statistika:</b>",
#         reply_markup=markup,
#         parse_mode="HTML"
#     )


# @router.callback_query(F.data.startswith("barber_stats:"))
# async def barber_stats(callback: types.CallbackQuery):
#     # ⚠️ Har doim butun son sifatida ishlatamiz
#     barber_id = int(callback.data.split(":")[1])
#     today = date.today()

#     async with async_session() as session:
#         # 🔒 int() konvertatsiya muhim
#         barber = await session.get(Barbers, barber_id)
#         if not barber:
#             return await callback.answer("❌ Barber topilmadi!", show_alert=True)

#         total_orders = await session.scalar(
#             select(func.count(Order.id)).where(Order.barber_id == str(barber_id))
#         )
#         today_orders = await session.scalar(
#             select(func.count(Order.id)).where(
#                 and_(Order.barber_id == str(barber_id), Order.date == today)
#             )
#         )
#         upcoming_orders = await session.scalar(
#             select(func.count(Order.id)).where(
#                 and_(Order.barber_id == str(barber_id), Order.date > today)
#             )
#         )

#     back_button = InlineKeyboardMarkup(
#         inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_stats")]]
#     )

#     await callback.message.edit_text(
#         f"💈 <b>{barber.barber_fullname}</b> statistikasi:\n\n"
#         f"📦 <b>Jami buyurtmalar:</b> {total_orders}\n"
#         f"📅 <b>Bugungi buyurtmalar:</b> {today_orders}\n"
#         f"⏳ <b>Kutilayotgan buyurtmalar:</b> {upcoming_orders}",
#         reply_markup=back_button,
#         parse_mode="HTML"
#     )
#     await callback.answer()


# @router.callback_query(F.data == "back_to_stats")
# async def back_to_stats(callback: types.CallbackQuery):
#     await callback.message.delete()
#     await show_stats(callback.message)
