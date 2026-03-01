#handlers/main_btn_handle/__init__.py
from aiogram import Router

from . import queue, user_info

router = Router()
router.include_router(queue.router)
router.include_router(user_info.router)
