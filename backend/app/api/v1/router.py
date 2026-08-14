from fastapi import APIRouter

from backend.app.api.v1.daily_contexts import router as daily_contexts_router
from backend.app.api.v1.decisions import router as decisions_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.profiles import router as profiles_router
from backend.app.api.v1.routines import router as routines_router

api_router = APIRouter()
api_router.include_router(daily_contexts_router)
api_router.include_router(decisions_router)
api_router.include_router(health_router)
api_router.include_router(profiles_router)
api_router.include_router(routines_router)
