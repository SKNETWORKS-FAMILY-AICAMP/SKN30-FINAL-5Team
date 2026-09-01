from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.modules.profiles.schemas import OnboardingResponse, OnboardingUpsertRequest
from backend.app.modules.profiles.service import ProfileService
from backend.app.modules.routines.schemas import RoutineCreateRequest
from backend.app.modules.routines.service import RoutineService


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OnboardingCompletionService:
    """Atomically persist onboarding and provision its initial base routine."""

    def __init__(
        self,
        profile_service: ProfileService,
        routine_service: RoutineService,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._profile_service = profile_service
        self._routine_service = routine_service
        self._clock = clock

    def complete(
        self,
        session: Session,
        user_id: UUID,
        request: OnboardingUpsertRequest,
        idempotency_key: UUID,
    ) -> OnboardingResponse:
        # The profile writes are flushed before the routine service reads its
        # context, but neither is committed until both operations succeed.
        self._profile_service.ensure_age_eligible(session, user_id, request)
        with session.begin():
            response = self._profile_service.upsert_onboarding_in_transaction(
                session, user_id, request, idempotency_key
            )
            effective_from = self._clock().astimezone(ZoneInfo(request.timezone)).date()
            self._routine_service.ensure_initial_routine(
                session,
                user_id,
                RoutineCreateRequest(
                    effective_from=effective_from,
                    goal_code=request.primary_goal_code,
                ),
            )
            return response


__all__ = ["OnboardingCompletionService"]
