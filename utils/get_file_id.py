# utils/get_file_id.py
from aiogram.types import Message


def get_photo_file_id(message: Message) -> str | None:
    photos = list(getattr(message, "photo", []) or [])
    if not photos:
        return None
    return photos[-1].file_id


def get_video_file_id(message: Message) -> str | None:
    video = getattr(message, "video", None)
    return getattr(video, "file_id", None)
