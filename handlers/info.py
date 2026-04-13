# handlers/info.py

import asyncio

from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.back import back_to_menu
from utils.info_profile import (
    build_info_text,
    build_public_info_keyboard,
    build_venue_address,
    get_display_title,
    get_info_profile_snapshot,
    get_location_coordinates,
    get_phone_value,
)

router = Router()

_LOC_MSG_ID_KEY = "contact_location_msg_id"
_INFO_MSG_ID_KEY = "contact_info_msg_id"
_IS_VENUE_KEY = "contact_is_venue"


async def _safe_delete_or_clear(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
        return
    except Exception:
        pass
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=int(message_id),
            reply_markup=None,
        )
    except Exception:
        pass


def _kb_only_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Ortga", callback_data="contact:back")]
        ]
    )


@router.callback_query(F.data == "contact")
async def open_contact(callback: types.CallbackQuery, state: FSMContext):
    snapshot = await get_info_profile_snapshot()

    await state.update_data(
        **{
            _LOC_MSG_ID_KEY: None,
            _INFO_MSG_ID_KEY: callback.message.message_id,
            _IS_VENUE_KEY: False,
        }
    )

    await callback.message.edit_text(
        build_info_text(snapshot),
        reply_markup=build_public_info_keyboard(snapshot, is_venue=False),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "contact:map")
async def show_map_as_single_message(callback: types.CallbackQuery, state: FSMContext):
    snapshot = await get_info_profile_snapshot()
    lat, lon = get_location_coordinates(snapshot)
    if lat is None or lon is None:
        await callback.answer("⚠️ Lokatsiya hali kiritilmagan.", show_alert=True)
        return

    data = await state.get_data()
    if data.get(_IS_VENUE_KEY, False):
        await callback.answer("🗺 Xarita allaqachon ochiq.", show_alert=True)
        return

    await callback.answer("📍 Xarita yuborildi ✅")

    old_info_msg_id = data.get(_INFO_MSG_ID_KEY) or callback.message.message_id
    asyncio.create_task(
        _safe_delete_or_clear(callback.bot, callback.message.chat.id, old_info_msg_id)
    )

    loc_msg = await callback.message.answer_venue(
        latitude=float(lat),
        longitude=float(lon),
        title=get_display_title(snapshot),
        address=build_venue_address(snapshot),
        reply_markup=_kb_only_back(),
    )

    await state.update_data(
        **{
            _LOC_MSG_ID_KEY: loc_msg.message_id,
            _INFO_MSG_ID_KEY: loc_msg.message_id,
            _IS_VENUE_KEY: True,
        }
    )


@router.callback_query(F.data == "contact:send_phone1")
async def send_phone1(callback: types.CallbackQuery):
    snapshot = await get_info_profile_snapshot()
    phone = get_phone_value(snapshot, "phone_number")
    if not phone:
        await callback.answer("Telefon raqam yo‘q.", show_alert=True)
        return

    await callback.message.answer_contact(
        phone_number=phone,
        first_name=get_display_title(snapshot),
    )
    await callback.answer("📞 Kontakt yuborildi ✅")


@router.callback_query(F.data == "contact:send_phone2")
async def send_phone2(callback: types.CallbackQuery):
    snapshot = await get_info_profile_snapshot()
    phone = get_phone_value(snapshot, "phone_number2")
    if not phone:
        await callback.answer("Telefon raqam yo‘q.", show_alert=True)
        return

    await callback.message.answer_contact(
        phone_number=phone,
        first_name=get_display_title(snapshot),
    )
    await callback.answer("📞 Kontakt yuborildi ✅")


@router.callback_query(F.data == "contact:back")
async def contact_back(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_venue = data.get(_IS_VENUE_KEY, False)
    msg_id = data.get(_INFO_MSG_ID_KEY)
    loc_msg_id = data.get(_LOC_MSG_ID_KEY)

    if is_venue:
        await callback.answer("↩️ Ortga qaytildi")

        target_id = loc_msg_id or msg_id
        if target_id:
            asyncio.create_task(
                _safe_delete_or_clear(callback.bot, callback.message.chat.id, target_id)
            )

        snapshot = await get_info_profile_snapshot()
        msg = await callback.message.answer(
            build_info_text(snapshot),
            reply_markup=build_public_info_keyboard(snapshot, is_venue=False),
            parse_mode="HTML",
        )

        await state.update_data(
            **{
                _LOC_MSG_ID_KEY: None,
                _INFO_MSG_ID_KEY: msg.message_id,
                _IS_VENUE_KEY: False,
            }
        )
        return

    await callback.answer()
    await state.update_data(
        **{
            _LOC_MSG_ID_KEY: None,
            _INFO_MSG_ID_KEY: None,
            _IS_VENUE_KEY: False,
        }
    )
    await back_to_menu(callback, state)


info = router
