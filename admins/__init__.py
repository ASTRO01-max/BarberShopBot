# admins/__init__.py
#barcha fayillarni toplash
from aiogram import Router

from .admin import router as admin_router
from .statistics import router as stats_router
from .order_list import router as orders_router
from .add_service import router as services_router
from .add_barbers import router as barbers_router
from .special_message import router as broadcast_router
from .service_shutdown import router as service_shutdown_router
from .barbers_shutdown import router as barbers_shutdown_router
from.info_handle import router as info_handle_router

router = Router()
router.include_router(admin_router)
router.include_router(stats_router)
router.include_router(orders_router)
router.include_router(services_router)
router.include_router(barbers_router)
router.include_router(broadcast_router)
router.include_router(service_shutdown_router)
router.include_router(barbers_shutdown_router)
router.include_router(info_handle_router)