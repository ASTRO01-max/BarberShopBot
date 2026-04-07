from collections.abc import Sequence
from html import escape

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select

from sql.db import async_session
from sql.models import Admins, Services
from utils.emoji_map import SERVICE_EMOJIS
from utils.service_pricing import build_service_price_lines, format_price
from .admin_buttons import ADMIN_MAIN_MENU_TITLE, get_main_menu

CANCEL_HINT = "\n\n❌ Bekor qilish uchun /cancel yuboring."


def with_cancel_hint(text: str) -> str:
    return f"{text}{CANCEL_HINT}"


def render_service_text(
    service: Services,
    *,
    title: str,
    index: int,
    total: int,
    extra_lines: Sequence[str] | None = None,
) -> str:
    service_name = (service.name or "").strip() or "Noma'lum xizmat"
    emoji = SERVICE_EMOJIS.get(service_name, "🔹")

    lines = [
        title,
        "",
        f"{emoji} <b>{escape(service_name)}</b>",
        *build_service_price_lines(service),
        f"🕒 <b>Davomiyligi:</b> {escape(str(service.duration or '-'))}",
    ]

    if extra_lines:
        lines.extend(["", *extra_lines])

    lines.extend(["", f"📌 <i>({index + 1} / {total})</i>"])
    return "\n".join(lines)


def render_empty_services_text(
    *,
    title: str,
    description: str = "⚠️ Hozircha xizmatlar mavjud emas.",
) -> str:
    return f"{title}\n\n{description}\n\n📌 <i>(0 / 0)</i>"


async def is_admin_user(user_id: int) -> bool:
    async with async_session() as session:
        admin_id = await session.scalar(select(Admins.id).where(Admins.tg_id == user_id))
    return admin_id is not None


async def ensure_admin_callback(callback: types.CallbackQuery) -> bool:
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat adminlar uchun.", show_alert=True)
        return False

    if callback.message is None:
        await callback.answer()
        return False

    return True


async def ensure_admin_message(message: types.Message) -> bool:
    if await is_admin_user(message.from_user.id):
        return True

    await message.answer("Bu bo'lim faqat adminlar uchun.")
    return False


async def show_admin_main_menu(
    *,
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    text = notice or ADMIN_MAIN_MENU_TITLE

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=get_main_menu(),
            )
            return message_id
        except Exception:
            pass

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )
    return sent.message_id


async def show_service_card(
    *,
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    service: Services | None,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> int:
    service_photo = getattr(service, "photo", None) if service is not None else None

    if message_id:
        if service_photo:
            try:
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=types.InputMediaPhoto(
                        media=service_photo,
                        caption=text,
                        parse_mode="HTML",
                    ),
                    reply_markup=reply_markup,
                )
                return message_id
            except Exception:
                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    return message_id
                except Exception:
                    pass
        else:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                return message_id
            except Exception:
                pass

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    if service_photo:
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=service_photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    return sent.message_id
