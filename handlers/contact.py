import re
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sql.db_contacts import ensure_info_row, get_info
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


def _pretty_text(info) -> str:
    title = _safe(getattr(info, "title", None))

    phone1 = _safe(getattr(info, "phone", None))
    phone2 = _safe(getattr(info, "phone2", None))

    telegram = _safe(getattr(info, "telegram", None))
    instagram = _safe(getattr(info, "instagram", None))
    website = _safe(getattr(info, "website", None))

    region = _safe(getattr(info, "region", None))
    district = _safe(getattr(info, "district", None))
    street = _safe(getattr(info, "street", None))
    landmark = _safe(getattr(info, "landmark", None))
    address_text = _safe(getattr(info, "address_text", None))

    work_time_text = _safe(getattr(info, "work_time_text", None))
    extra = _safe(getattr(info, "extra", None))

    # Zamonaviy card-style
    return (
        f"✨ <b>{title}</b>\n"
        f"<i>Kontaktlar va manzil ma’lumotlari</i>\n"
        f"────────────────────\n\n"
        f"📞 <b>Aloqa</b>\n"
        f"• 1-raqam: <code>{phone1}</code>\n"
        f"• 2-raqam: <code>{phone2}</code>\n\n"
        f"🕒 <b>Ish vaqti</b>\n"
        f"• {work_time_text}\n\n"
        f"📍 <b>Manzil</b>\n"
        f"• {address_text}\n"
        f"• {region} / {district}\n"
        f"• {street}\n"
        f"• Mo‘ljal: {landmark}\n\n"
        f"🌐 <b>Onlayn</b>\n"
        f"• Telegram: {_safe(telegram)}\n"
        f"• Instagram: {_safe(instagram)}\n"
        f"• Website: {_safe(website)}\n\n"
        f"📝 <b>Qo‘shimcha</b>\n"
        f"• {extra}\n"
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
    phone1 = _safe(getattr(info, "phone", None))

    compact = (
        f"{address_text}\n"
        f"{region} / {district}\n"
        f"{street}\n"
        f"Ish vaqti: {work_time_text}\n"
        f"Tel: {phone1}"
    )
    # Venue address limitlari qat’iy bo‘lishi mumkin — ehtiyot uchun qisqartiramiz
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
    Talab: xarita + info "bitta xabar" bo'lib ko'rinsin.
    Telegram cheklovi: Location caption olmaydi. Eng to'g'ri yo'l: Venue.
    Shuning uchun:
      - info xabarni o'chiramiz
      - o'rniga Venue yuboramiz (title + address ichida kompakt info)
      - keyboard venue ostida turadi
    """
    await ensure_info_row()
    info = await get_info()

    lat = getattr(info, "latitude", None)
    lon = getattr(info, "longitude", None)
    if lat is None or lon is None:
        await callback.answer("⚠️ Lokatsiya hali kiritilmagan.", show_alert=True)
        return

    data = await state.get_data()
    is_venue = data.get(_IS_VENUE_KEY, False)

    # Agar allaqachon venue ochiq bo'lsa, qaytadan yubormaymiz
    if is_venue:
        await callback.answer("🗺 Xarita allaqachon ochiq.", show_alert=True)
        return

    # Avvalgi info xabarini o'chiramiz (sezilmas darajada)
    info_msg_id = data.get(_INFO_MSG_ID_KEY) or callback.message.message_id
    try:
        await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=int(info_msg_id))
    except Exception:
        pass

    title = _clip(_safe(getattr(info, "title", None)), 100)
    address = _venue_address(info)

    venue_msg = await callback.message.answer_venue(
        latitude=float(lat),
        longitude=float(lon),
        title=title if title != "—" else "Barbershop",
        address=address if address != "—" else "Manzil",
        reply_markup=_kb(info, is_venue=True)
    )

    await state.update_data(**{
        _LOC_MSG_ID_KEY: venue_msg.message_id,
        _INFO_MSG_ID_KEY: venue_msg.message_id,
        _IS_VENUE_KEY: True
    })

    await callback.answer("📍 Xarita ochildi ✅")


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

    if is_venue and msg_id:
        # Venue'ni o'chiramiz
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=int(msg_id))
        except Exception:
            pass

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

        await callback.answer()
        return

    # Venue yo'q bo'lsa — menu ga qaytish
    await callback.answer()
    await back_to_menu(callback)


# Backward compatibility (old bot.py may import contact.contact)
contact = router
