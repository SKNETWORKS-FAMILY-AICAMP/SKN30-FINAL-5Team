from fastapi import APIRouter

from backend.app.api.v1.account_deletion import router as account_deletion_router
from backend.app.api.v1.daily_contexts import router as daily_contexts_router
from backend.app.api.v1.decisions import router as decisions_router
from backend.app.api.v1.exercises import router as exercises_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.home import router as home_router
from backend.app.api.v1.notifications import router as notifications_router
from backend.app.api.v1.profiles import router as profiles_router
from backend.app.api.v1.rewards import router as rewards_router
from backend.app.api.v1.routines import router as routines_router
from backend.app.api.v1.weekly_plans import router as weekly_plans_router
from backend.app.api.v1.weekly_reports import router as weekly_reports_router
from backend.app.api.v1.weekly_reports import weeks_router
from backend.app.api.v1.workouts import router as workouts_router
from backend.app.api.v1.workouts import selection_router as workout_selection_router

api_router = APIRouter()
api_router.include_router(account_deletion_router)
api_router.include_router(daily_contexts_router)
api_router.include_router(decisions_router)
api_router.include_router(exercises_router)
api_router.include_router(health_router)
api_router.include_router(home_router)
api_router.include_router(notifications_router)
api_router.include_router(profiles_router)
api_router.include_router(rewards_router)
api_router.include_router(routines_router)
api_router.include_router(workout_selection_router)
api_router.include_router(workouts_router)
api_router.include_router(weeks_router)
api_router.include_router(weekly_reports_router)
api_router.include_router(weekly_plans_router)
