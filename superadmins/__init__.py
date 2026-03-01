#superadmins/__init__.py
"""
Barber panel tizimi - barcha modullarni birlashtirish
"""
from aiogram import Router

from .superadmin import router as main_router
from .own_statistics import router as stats_router
from .modify_work_schedule import router as schedule_router
from .pause_today import router as pause_router
from .own_special_message import router as message_router
from .todays_orders import router as orders_router
from .order_notify_handlers import router as notify_router
from .barber_including import router as including_router

# Asosiy router yaratish
router = Router()

# Barcha sub-routerlarni qo'shish
router.include_router(main_router)
router.include_router(stats_router)
router.include_router(schedule_router)
router.include_router(pause_router)
router.include_router(message_router)
router.include_router(orders_router)
router.include_router(notify_router)
router.include_router(including_router)

__all__ = ['router']
