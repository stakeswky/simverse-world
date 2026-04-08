"""Admin router package — all endpoints require is_admin=True."""
from fastapi import APIRouter

from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(dashboard_router)
router.include_router(users_router)
