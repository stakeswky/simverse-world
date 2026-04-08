"""Admin router package — all endpoints require is_admin=True."""
from fastapi import APIRouter

from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router
from app.routers.admin.residents import router as residents_router
from app.routers.admin.forge_monitor import router as forge_monitor_router
from app.routers.admin.economy import router as economy_router
from app.routers.admin.system_config import router as system_config_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(dashboard_router)
router.include_router(users_router)
router.include_router(residents_router)
router.include_router(forge_monitor_router)
router.include_router(economy_router)
router.include_router(system_config_router)
