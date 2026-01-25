#handlers/main_btn_handle/__init__.py
from aiogram import Router

from . import orders_history, cancel_order, user_info

router = Router()
router.include_router(orders_history.router)
router.include_router(cancel_order.router)
router.include_router(user_info.router)
