# handlers/info.py
import re
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sql.db_info import ensure_info_row, get_info
from handlers.back import back_to_menu

router = Router()

# FSM ichida hozirgi "Kontakt" xabarining holatini saqlaymiz
_LOC_MSG_ID_KEY = "contact_location_msg_id"         # venue message_id (xarita)
_INFO_MSG_ID_KEY = "contact_info_msg_id"            # oddiy info message_id yoki venue message_id
_IS_VENUE_KEY = "contact_is_venue"                  # True bo'lsa hozir venue ko'rinyapti


def _safe(x: str | None) -> str:
    x = (x or "").strip()
    return x if x else "—"


def _clip(s: str, max_len: int) -> str:
    s = s or ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _is_http_url(u: str | None) -> bool:
    u = (u or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _normalize_telegram(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if _is_http_url(v):
        return v
    if v.startswith("@"):
        return "https://t.me/" + v[1:]
    # username bo'lsa
    if " " not in v and "/" not in v and "." not in v:
        return "https://t.me/" + v
    return None


def _normalize_instagram(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if _is_http_url(v):
        return v
    # username bo'lsa -> https://instagram.com/<username>
    v = v.lstrip("@").strip()
    if not v or " " in v or "/" in v:
        return None
    return f"https://instagram.com/{v}"


def _normalize_website(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None

    # bo'sh joylarni olib tashla
    v = v.replace(" ", "")

    # vergul, underscore bilan domen bo'lmasin (xatoga olib keladi)
    if "," in v:
        return None

    # agar http(s) yo'q bo'lsa qo'shamiz
    if not v.startswith("http://") and not v.startswith("https://"):
        v = "https://" + v

    # juda sodda, ammo Telegram uchun yetarli tekshiruv
    if not re.match(r"^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$", v):
        return None

    return v


def _display_title(info) -> str:
    title = _safe(getattr(info, "title", None))
    return "Barbershop" if title == "—" else title


def _parse_coord(value) -> float | None:
    try:
        v = str(value).strip()
        if not v:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


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


def _pretty_text(info) -> str:
    title = _display_title(info)

    # Kontaktlar
    telegram_raw = getattr(info, "telegram", None)
    instagram_raw = getattr(info, "instagram", None)
    website_raw = getattr(info, "website", None)

    # Telefonlar
    phone1 = _safe(getattr(info, "phone", None))
    phone2 = _safe(getattr(info, "phone2", None))

    # Manzil
    region = _safe(getattr(info, "region", None))
    district = _safe(getattr(info, "district", None))
    street = _safe(getattr(info, "street", None))
    address_text = _safe(getattr(info, "address_text", None))

    # Ish vaqti
    work_time_text = _safe(getattr(info, "work_time_text", None))

    # Linklar (agar user @username yoki username kiritgan bo‘lsa ham chiroyli URL bo‘ladi)
    tg = _normalize_telegram(telegram_raw)
    ig = _normalize_instagram(instagram_raw)
    web = _normalize_website(website_raw)

    # Matnda ko‘rinishi uchun (link bo‘lsa URL, bo‘lmasa "—")
    telegram_show = tg or _safe(telegram_raw)
    instagram_show = ig or _safe(instagram_raw)
    website_show = web or _safe(website_raw)

    phones_block = []
    if phone1 != "—":
        phones_block.append(f"📞 <b>Telefon 1:</b> {phone1}")
    if phone2 != "—":
        phones_block.append(f"📞 <b>Telefon 2:</b> {phone2}")
    if not phones_block:
        phones_block.append("📞 <b>Telefon:</b> —")

    return (
        f"ℹ️ <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Ish vaqti</b>\n"
        f"• {work_time_text}\n\n"
        f"📍 <b>Manzil</b>\n"
        f"• {address_text}\n"
        f"• {region} / {district}\n"
        f"• {street}\n\n"
        f"{chr(10).join(phones_block)}\n\n"
        f"🌐 <b>Onlayn aloqa</b>\n"
        f"✈️ Telegram: {telegram_show}\n"
        f"📷 Instagram: {instagram_show}\n"
        f"🔗 Website: {website_show}\n"
    )


def _venue_address(info) -> str:
    """
    Venue'da caption bo'lmaydi. Shuning uchun UI/UX uchun address maydoniga
    kompakt, foydali satrlarni joylaymiz (uzunlikni clip qilamiz).
    """
    address_text = _safe(getattr(info, "address_text", None))
    region = _safe(getattr(info, "region", None))
    district = _safe(getattr(info, "district", None))
    street = _safe(getattr(info, "street", None))
    work_time_text = _safe(getattr(info, "work_time_text", None))

    lines = []
    if address_text != "—":
        lines.append(address_text)
    if region != "—" or district != "—":
        if region != "—" and district != "—":
            lines.append(f"{region} / {district}")
        else:
            lines.append(region if region != "—" else district)
    if street != "—":
        lines.append(street)
    if work_time_text != "—":
        lines.append(f"Ish vaqti: {work_time_text}")

    if not lines:
        lines.append("Manzil")

    compact = "\n".join(lines)
    # Venue address limitlari qat'iy bo'lishi mumkin ? ehtiyot uchun qisqartiramiz
    return _clip(compact, 240)


def _kb(info, is_venue: bool) -> InlineKeyboardMarkup:
    """
    is_venue=True bo'lsa, "📍 Manzilni xaritada ko‘rish" o'rniga "🗺 Xarita ochiq" ko'rsatamiz
    (yana bosib spam bo'lmasin).
    """
    kb = []

    if not is_venue:
        kb.append([InlineKeyboardButton(text="📍 Manzilni xaritada ko‘rish", callback_data="contact:map")])
    else:
        kb.append([InlineKeyboardButton(text="🗺 Xarita ochiq", callback_data="contact:map")])

    # Telefonlar: URL tel ishlatmaymiz. Contact yuboramiz.
    if (getattr(info, "phone", None) or "").strip():
        kb.append([InlineKeyboardButton(text="📞 1-raqamni yuborish", callback_data="contact:send_phone1")])
    if (getattr(info, "phone2", None) or "").strip():
        kb.append([InlineKeyboardButton(text="📞 2-raqamni yuborish", callback_data="contact:send_phone2")])

    # Linklar: normalize+validate
    tg = _normalize_telegram(getattr(info, "telegram", None))
    if tg:
        kb.append([InlineKeyboardButton(text="✈️ Telegram", url=tg)])

    ig = _normalize_instagram(getattr(info, "instagram", None))
    if ig:
        kb.append([InlineKeyboardButton(text="📷 Instagram", url=ig)])

    web = _normalize_website(getattr(info, "website", None))
    if web:
        kb.append([InlineKeyboardButton(text="🌐 Website", url=web)])


    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="contact:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def _kb_only_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Ortga", callback_data="contact:back")]
        ]
    )


@router.callback_query(F.data == "contact")
async def open_contact(callback: types.CallbackQuery, state: FSMContext):
    await ensure_info_row()
    info = await get_info()

    # Kontakt sahifasiga kirganda holatni tozalab olamiz
    await state.update_data(**{
        _LOC_MSG_ID_KEY: None,
        _INFO_MSG_ID_KEY: callback.message.message_id,
        _IS_VENUE_KEY: False
    })

    await callback.message.edit_text(
        _pretty_text(info),
        reply_markup=_kb(info, is_venue=False),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contact:map")
async def show_map_as_single_message(callback: types.CallbackQuery, state: FSMContext):
    """
    Talab:
    "📍 Manzilni xaritada ko‘rish" bosilganda faqat geolokatsiya chiqadi
    va uning tagida "🔙 Ortga" tugmasi bo'ladi.
    """
    await ensure_info_row()
    info = await get_info()

    lat = _parse_coord(getattr(info, "latitude", None))
    lon = _parse_coord(getattr(info, "longitude", None))
    if lat is None or lon is None:
        await callback.answer("⚠️ Lokatsiya hali kiritilmagan.", show_alert=True)
        return

    data = await state.get_data()
    is_venue = data.get(_IS_VENUE_KEY, False)

    # Agar allaqachon xarita ochilgan bo'lsa, qaytadan spam qilmaymiz
    if is_venue:
        await callback.answer("🗺 Xarita allaqachon ochiq.", show_alert=True)
        return

    # UI tez javob qaytarsin (spinner qotib qolmasin)
    await callback.answer("📍 Xarita yuborildi ✅")

    # Avvalgi info xabarining id si (odatda shu edit qilingan xabar)
    old_info_msg_id = data.get(_INFO_MSG_ID_KEY) or callback.message.message_id

    # Eski xabarni fon rejimida olib tashlaymiz (tezkor UX)
    asyncio.create_task(
        _safe_delete_or_clear(callback.bot, callback.message.chat.id, old_info_msg_id)
    )

    # Venue yuboramiz: xarita + nom + kompakt manzil (pro UI)
    loc_msg = await callback.message.answer_venue(
        latitude=float(lat),
        longitude=float(lon),
        title=_display_title(info),
        address=_venue_address(info),
        reply_markup=_kb_only_back(),
    )

    await state.update_data(**{
        _LOC_MSG_ID_KEY: loc_msg.message_id,     # location message id
        _INFO_MSG_ID_KEY: loc_msg.message_id,    # compatibility uchun
        _IS_VENUE_KEY: True
    })



@router.callback_query(F.data == "contact:send_phone1")
async def send_phone1(callback: types.CallbackQuery):
    await ensure_info_row()
    info = await get_info()

    phone = (getattr(info, "phone", None) or "").strip()
    if not phone:
        await callback.answer("Telefon raqam yo‘q.", show_alert=True)
        return

    await callback.message.answer_contact(
        phone_number=phone,
        first_name=(getattr(info, "title", None) or "Barbershop")
    )
    await callback.answer("📞 Kontakt yuborildi ✅")


@router.callback_query(F.data == "contact:send_phone2")
async def send_phone2(callback: types.CallbackQuery):
    await ensure_info_row()
    info = await get_info()

    phone = (getattr(info, "phone2", None) or "").strip()
    if not phone:
        await callback.answer("Telefon raqam yo‘q.", show_alert=True)
        return

    await callback.message.answer_contact(
        phone_number=phone,
        first_name=(getattr(info, "title", None) or "Barbershop")
    )
    await callback.answer("📞 Kontakt yuborildi ✅")


@router.callback_query(F.data == "contact:back")
async def contact_back(callback: types.CallbackQuery, state: FSMContext):
    """
    Talab:
    - Agar venue (xarita) ochiq bo'lsa: venue o'chsin va oddiy info qaytsin
    - Agar venue yo'q bo'lsa: handlers/back.py dagi back_to_menu() ishlasin
    """
    data = await state.get_data()
    is_venue = data.get(_IS_VENUE_KEY, False)
    msg_id = data.get(_INFO_MSG_ID_KEY)
    loc_msg_id = data.get(_LOC_MSG_ID_KEY)

    if is_venue:
        # UI darhol javob qaytarsin (spinner qotib qolmasin)
        await callback.answer("↩️ Ortga qaytildi")

        # Xaritadagi xabarni o'chiramiz
        target_id = loc_msg_id or msg_id
        if target_id:
            asyncio.create_task(
                _safe_delete_or_clear(callback.bot, callback.message.chat.id, target_id)
            )

        # Oddiy info xabarni qayta yuboramiz (sezilmas darajada)
        await ensure_info_row()
        info = await get_info()

        msg = await callback.message.answer(
            _pretty_text(info),
            reply_markup=_kb(info, is_venue=False),
            parse_mode="HTML"
        )

        await state.update_data(**{
            _LOC_MSG_ID_KEY: None,
            _INFO_MSG_ID_KEY: msg.message_id,
            _IS_VENUE_KEY: False
        })

        return

    # Venue yo'q bo'lsa — menu ga qaytish
    await callback.answer()
    await state.update_data(**{
        _LOC_MSG_ID_KEY: None,
        _INFO_MSG_ID_KEY: None,
        _IS_VENUE_KEY: False
    })
    await back_to_menu(callback)


# Backward compatibility (old bot.py may import contact.contact)
info = router

