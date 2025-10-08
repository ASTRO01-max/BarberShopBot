# --- 7-qadam: Tasdiqlash ---
# async def confirm(callback: types.CallbackQuery, state: FSMContext):
#     _, service_id, barber_id, date, time = callback.data.split("_")
#     user_data = await state.get_data()
#     user_id = callback.from_user.id

#     service_name = services[service_id][0]
#     barber_name = next((b['name'] for b in barbers if b['id'] == barber_id), "Noma'lum")

#     order = {
#         "user_id": user_id,
#         "fullname": user_data.get("fullname", "Noma'lum"),
#         "phonenumber": user_data.get("phonenumber", "Noma'lum"),
#         "service_id": service_id,
#         "barber_id": barber_id,
#         "date": date,   # format: "YYYY-MM-DD"
#         "time": time    # format: "HH:MM"
#     }

#     # ⚠️ async save — qat'iy await bilan
#     saved = await save_order(order)

#     if saved is None:
#         # DB dan None qaytsa, xatolik haqida xabar bering va log qoldiring
#         await callback.message.answer("❌ Buyurtma saqlanmadi. Iltimos, administrator bilan bog'laning.")
#         await callback.answer()
#         return

#     # muvaffaqiyatli saqlanganda foydalanuvchiga xabar
#     await callback.message.edit_text(
#         f"✅ Siz muvaffaqiyatli navbat oldingiz:\n"
#         f"👤 Ismingiz: {order['fullname']}\n"
#         f"📱 Telefon: {order['phonenumber']}\n"
#         f"💈 Xizmat: {service_name}\n"
#         f"👨‍💼 Usta: {barber_name}\n"
#         f"🗓 Sana: {date}\n"
#         f"🕔 Vaqt: {time}"
#     )

#     await state.clear()
#     await callback.answer()
    # await callback.message.answer(
    #     "Quyidagi menyudan birini tanlang:",
    #     reply_markup=get_main_menu()
    # )