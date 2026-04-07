from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.future import select

from sql.db import async_session
from sql.models import Admins
from .admin_buttons import markup
from .service_admin_common import show_admin_main_menu

router = Router()


@router.message(Command("admin"))
async def admin_panel(message: types.Message) -> None:
    user_tg_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(
            select(Admins).where(Admins.tg_id == user_tg_id)
        )
        admin = result.scalars().first()

    if not admin:
        await message.answer("⛔ Bu bo'lim faqat adminlar uchun.")
        return

    await message.answer(
        f"🔐 Xush kelibsiz, {admin.admin_fullname or 'Admin'}!",
        reply_markup=markup,
    )
    await show_admin_main_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=None,
    )
