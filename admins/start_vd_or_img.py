# admins/start_vd_or_img.py
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sql.db_start_vd_or_img import (
    clear_start_media,
    get_start_media,
    set_start_image,
    set_start_video,
)
from .admin_buttons import (
    ADMIN_START_VD_OR_IMG_CB,
    START_MEDIA_CLEAR_CB,
    START_MEDIA_IMAGE_CB,
    START_MEDIA_VIDEO_CB,
    get_start_media_inline_actions_kb,
)
from .service_admin_common import ensure_admin_callback, ensure_admin_message, with_cancel_hint

router = Router()

START_MEDIA_PANEL_KEY = "start_media_panel_message_id"
START_MEDIA_TITLE = "<b>Kirish media sahnasi</b>"


class StartMediaState(StatesGroup):
    waiting_for_video = State()
    waiting_for_image = State()


def _resolve_media_status(settings) -> tuple[str, str | None]:
    if settings is not None:
        if settings.vd_file_id:
            return "Video", settings.vd_file_id
        if settings.img_file_id:
            return "Rasm", settings.img_file_id
    return "O'rnatilmagan", None


def _render_start_media_text(settings, notice: str | None = None) -> str:
    media_label, file_id = _resolve_media_status(settings)
    lines = [
        START_MEDIA_TITLE,
        "",
        "/start dan oldin chiqadigan kirish videosi yoki rasmi shu yerda boshqariladi.",
        f"Faol media: <b>{escape(media_label)}</b>",
    ]

    if file_id:
        lines.append(f"Saqlangan file_id: <code>{escape(file_id)}</code>")
    else:
        lines.append(
            "Hozircha media saqlanmagan. Bu holatda /start yuborilganda bot media chiqarmasdan ishga tushadi."
        )

    lines.extend(
        [
            "",
            "Video yoki rasm yuborish bosqichidan chiqish uchun /cancel yuboring.",
            "Asosiy admin menyusini qayta ochish uchun /admin yuborishingiz mumkin.",
        ]
    )

    text = "\n".join(lines)
    if notice:
        return f"{notice}\n\n{text}"
    return text


async def _show_start_media_menu(
    *,
    bot,
    chat_id: int,
    message_id: int | None,
    notice: str | None = None,
) -> int:
    settings = await get_start_media()
    text = _render_start_media_text(settings, notice=notice)
    markup = get_start_media_inline_actions_kb()

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return message_id
        except Exception:
            pass

    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=markup,
    )
    return sent.message_id


async def _refresh_start_media_menu(
    *,
    state: FSMContext,
    bot,
    chat_id: int,
    notice: str | None = None,
) -> int:
    data = await state.get_data()
    panel_message_id = data.get(START_MEDIA_PANEL_KEY)
    shown_message_id = await _show_start_media_menu(
        bot=bot,
        chat_id=chat_id,
        message_id=panel_message_id,
        notice=notice,
    )
    await state.update_data(**{START_MEDIA_PANEL_KEY: shown_message_id})
    return shown_message_id


@router.callback_query(F.data == ADMIN_START_VD_OR_IMG_CB)
async def open_start_media_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.clear()
    shown_message_id = await _show_start_media_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await state.update_data(**{START_MEDIA_PANEL_KEY: shown_message_id})
    await callback.answer()


@router.callback_query(F.data == START_MEDIA_VIDEO_CB)
async def ask_start_video(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.set_state(StartMediaState.waiting_for_video)
    await state.update_data(**{START_MEDIA_PANEL_KEY: callback.message.message_id})
    await callback.message.answer(
        with_cancel_hint(
            "<b>Kirish videosi</b>\n\nTelegram video yuboring. Yuborilgan videoning file_id qiymati saqlanadi."
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == START_MEDIA_IMAGE_CB)
async def ask_start_image(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await state.set_state(StartMediaState.waiting_for_image)
    await state.update_data(**{START_MEDIA_PANEL_KEY: callback.message.message_id})
    await callback.message.answer(
        with_cancel_hint(
            "<b>Kirish rasmi</b>\n\nTelegram rasm yuboring. Yuborilgan rasmning file_id qiymati saqlanadi."
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == START_MEDIA_CLEAR_CB)
async def clear_start_media_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await ensure_admin_callback(callback):
        return

    await clear_start_media()
    await state.clear()
    shown_message_id = await _show_start_media_menu(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        notice="<b>Kirish media o'chirildi.</b>",
    )
    await state.update_data(**{START_MEDIA_PANEL_KEY: shown_message_id})
    await callback.answer("Media o'chirildi")


@router.message(
    StateFilter(StartMediaState.waiting_for_video, StartMediaState.waiting_for_image),
    Command("cancel"),
)
async def cancel_start_media_input(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        return

    await state.set_state(None)
    await _refresh_start_media_menu(
        state=state,
        bot=message.bot,
        chat_id=message.chat.id,
        notice="<b>Amal bekor qilindi.</b>",
    )
    await message.answer("Amal bekor qilindi.")


@router.message(StateFilter(StartMediaState.waiting_for_video), F.video)
async def save_start_video_message(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        return

    await set_start_video(message.video.file_id)
    await state.set_state(None)
    await _refresh_start_media_menu(
        state=state,
        bot=message.bot,
        chat_id=message.chat.id,
        notice="<b>Kirish videosi saqlandi.</b>",
    )
    await message.answer("Kirish videosi saqlandi.")


@router.message(StateFilter(StartMediaState.waiting_for_image), F.photo)
async def save_start_image_message(message: types.Message, state: FSMContext) -> None:
    if not await ensure_admin_message(message):
        return

    await set_start_image(message.photo[-1].file_id)
    await state.set_state(None)
    await _refresh_start_media_menu(
        state=state,
        bot=message.bot,
        chat_id=message.chat.id,
        notice="<b>Kirish rasmi saqlandi.</b>",
    )
    await message.answer("Kirish rasmi saqlandi.")


@router.message(StateFilter(StartMediaState.waiting_for_video))
async def reject_non_video_message(message: types.Message) -> None:
    if not await ensure_admin_message(message):
        return

    await message.answer("Faqat video yuboring yoki /cancel yuboring.")


@router.message(StateFilter(StartMediaState.waiting_for_image))
async def reject_non_image_message(message: types.Message) -> None:
    if not await ensure_admin_message(message):
        return

    await message.answer("Faqat rasm yuboring yoki /cancel yuboring.")
