# sql/db_start_vd_or_img.py

from sqlalchemy.exc import SQLAlchemyError

from sql.db import async_session
from sql.models import StartVdOrImg

START_MEDIA_SINGLETON_ID = 1
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_IMAGE = "image"


async def get_start_media() -> StartVdOrImg | None:
    async with async_session() as session:
        return await session.get(StartVdOrImg, START_MEDIA_SINGLETON_ID)


async def ensure_start_media_row() -> StartVdOrImg:
    async with async_session() as session:
        settings = await session.get(StartVdOrImg, START_MEDIA_SINGLETON_ID)
        if settings is not None:
            return settings

        settings = StartVdOrImg(id=START_MEDIA_SINGLETON_ID)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
        return settings


async def _save_start_media(
    *,
    video_file_id: str | None,
    image_file_id: str | None,
) -> StartVdOrImg:
    async with async_session() as session:
        settings = await session.get(StartVdOrImg, START_MEDIA_SINGLETON_ID)
        if settings is None:
            settings = StartVdOrImg(id=START_MEDIA_SINGLETON_ID)
            session.add(settings)
            await session.flush()

        settings.vd_file_id = (video_file_id or "").strip() or None
        settings.img_file_id = (image_file_id or "").strip() or None

        try:
            await session.commit()
            await session.refresh(settings)
            return settings
        except SQLAlchemyError:
            await session.rollback()
            raise


async def set_start_video(file_id: str) -> StartVdOrImg:
    return await _save_start_media(video_file_id=file_id, image_file_id=None)


async def set_start_image(file_id: str) -> StartVdOrImg:
    return await _save_start_media(video_file_id=None, image_file_id=file_id)


async def clear_start_media() -> StartVdOrImg:
    return await _save_start_media(video_file_id=None, image_file_id=None)


def resolve_start_media_payload(
    settings: StartVdOrImg | None,
) -> tuple[str | None, str | None]:
    if settings is not None:
        if settings.vd_file_id:
            return MEDIA_TYPE_VIDEO, settings.vd_file_id
        if settings.img_file_id:
            return MEDIA_TYPE_IMAGE, settings.img_file_id
    return None, None


async def get_start_media_payload() -> tuple[str | None, str | None]:
    settings = await get_start_media()
    return resolve_start_media_payload(settings)
