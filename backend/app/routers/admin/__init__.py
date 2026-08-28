"""Admin router package — all endpoints require is_admin=True."""
from fastapi import APIRouter

from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router
from app.routers.admin.residents import router as residents_router
from app.routers.admin.forge_monitor import router as forge_monitor_router
from app.routers.admin.economy import router as economy_router
from app.routers.admin.system_config import router as system_config_router
from app.routers.admin.events import router as events_router
from app.routers.admin.items import router as items_router
from app.routers.admin.llm_usage import router as llm_usage_router
from app.routers.admin.gossip import router as gossip_router
from app.routers.admin.lab import router as lab_router
from app.routers.admin.world import router as world_router
from app.routers.admin.social_graph import router as social_graph_router
from app.routers.admin.offices import router as offices_router
from app.routers.admin.policies import router as policies_router
from app.routers.admin.resident_sprites import router as resident_sprites_router
from app.routers.admin.seasons import router as seasons_router
from app.routers.admin.hosted_agents import router as hosted_agents_router
from app.routers.admin.product_metrics import router as product_metrics_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(dashboard_router)
router.include_router(users_router)
router.include_router(residents_router)
router.include_router(forge_monitor_router)
router.include_router(economy_router)
router.include_router(system_config_router)
router.include_router(events_router)
router.include_router(items_router)
router.include_router(llm_usage_router)
router.include_router(gossip_router)
router.include_router(lab_router)
router.include_router(world_router)
router.include_router(social_graph_router)
router.include_router(offices_router)
router.include_router(policies_router)
router.include_router(resident_sprites_router)
router.include_router(seasons_router)
router.include_router(hosted_agents_router)
router.include_router(product_metrics_router)
