import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.weekly_plans.ports import (
    LatestPlanRevision,
    PlanContext,
    PlanIdempotencyRecord,
    PlanRevisionValues,
    RoutinePlanEvidence,
)
from backend.app.modules.weekly_plans.schemas import (
    InitialWeeklyPlanRequest,
    WeeklyPlanRevisionRequest,
)
from backend.app.modules.weekly_plans.service import (
    AiRevisionLimitReachedError,
    IdempotencyKeyReusedError,
    PlanRevisionRejectedError,
    PreviousWeeklyReportRequiredError,
    StalePlanRevisionError,
    WeeklyPlanService,
)
from backend.app.modules.weekly_reports.schemas import WeekResponse

WEEK_START = date(2026, 8, 17)
WEEK_END = WEEK_START + timedelta(days=6)
NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> Any:
        return nullcontext()


class FakeWeekResolver:
    def __init__(self, week_id: UUID) -> None:
        self.response = WeekResponse(
            week_id=week_id,
            week_start=WEEK_START,
            week_end=WEEK_END,
            timezone="Asia/Seoul",
            target_workout_count=4,
            plan_origin_code="COLD_START",
            cold_start_applied=True,
            status_code="OPEN",
            closed_at=None,
            report_id=None,
            report_status_code=None,
        )

    def get_week(self, *args: Any) -> WeekResponse:
        return self.response


class FakeRoutineRepository:
    def __init__(self, routine_id: UUID) -> None:
        self.payloads = {
            routine_id: {
                "id": routine_id,
                "version": 2,
                "goal_code": "GENERAL_FITNESS",
                "status_code": "ACTIVE",
                "effective_from": WEEK_START,
                "catalog_version": "catalog-v1",
                "days": [],
                "created_at": NOW,
            }
        }

    def get_routine_response_payload(
        self, session: Any, user_id: UUID, routine_id: UUID
    ) -> dict[str, Any] | None:
        return self.payloads.get(routine_id)


class FakeWeeklyPlanRepository:
    def __init__(self, context: PlanContext, evidence: RoutinePlanEvidence) -> None:
        self.context = context
        self.evidence = {evidence.routine_id: evidence}
        self.revisions: list[PlanRevisionValues] = []
        self.idempotency: dict[tuple[str, UUID], PlanIdempotencyRecord] = {}

    def acquire_week_lock(self, *args: Any) -> None:
        pass

    def acquire_idempotency_lock(self, *args: Any) -> None:
        pass

    def get_idempotency_record(
        self, session: Any, user_id: UUID, endpoint_code: str, key: UUID
    ) -> PlanIdempotencyRecord | None:
        return self.idempotency.get((endpoint_code, key))

    def save_idempotency_record(self, session: Any, **values: Any) -> None:
        self.idempotency[(values["endpoint_code"], values["key"])] = PlanIdempotencyRecord(
            values["request_hash"], values["response_payload"]
        )

    def get_plan_context(self, *args: Any) -> PlanContext:
        return self.context

    def get_routine_evidence(
        self, session: Any, user_id: UUID, routine_id: UUID
    ) -> RoutinePlanEvidence | None:
        return self.evidence.get(routine_id)

    def get_latest_revision(self, session: Any, week_id: UUID) -> LatestPlanRevision | None:
        if not self.revisions:
            return None
        latest = self.revisions[-1]
        return LatestPlanRevision(
            latest.revision_id,
            latest.revision_sequence,
            max((value.ai_revision_number or 0 for value in self.revisions), default=0),
            latest.routine_id,
        )

    def create_revision(self, session: Any, values: PlanRevisionValues) -> PlanRevisionValues:
        self.revisions.append(values)
        return values


def _fixture() -> tuple[
    WeeklyPlanService,
    FakeWeeklyPlanRepository,
    FakeWeekResolver,
    UUID,
    UUID,
]:
    user_id = uuid4()
    week_id = uuid4()
    routine_id = uuid4()
    exercise_id = uuid4()
    context = PlanContext(
        week_id=week_id,
        week_start=WEEK_START,
        week_end=WEEK_END,
        is_first_user_week=True,
        cold_start_applied=True,
        source_weekly_report_id=None,
        previous_report_status_code=None,
        requested_duration_minutes=40,
        preferred_location_code="HOME",
        allowed_location_codes=("GYM", "HOME"),
        available_equipment_codes=("BAND", "MAT"),
        safety_status_code="PASS",
        safety_opinion_codes=(),
        excluded_exercise_ids=(),
        current_routine_id=routine_id,
    )
    evidence = RoutinePlanEvidence(
        routine_id=routine_id,
        routine_version=2,
        requested_duration_minutes=40,
        supported_location_codes=("HOME",),
        required_equipment_codes=("MAT",),
        exercise_ids=(exercise_id,),
    )
    repository = FakeWeeklyPlanRepository(context, evidence)
    resolver = FakeWeekResolver(week_id)
    service = WeeklyPlanService(
        repository,  # type: ignore[arg-type]
        FakeRoutineRepository(routine_id),  # type: ignore[arg-type]
        resolver,
        clock=lambda: NOW,
    )
    return service, repository, resolver, user_id, routine_id


def _initial(service: WeeklyPlanService, user_id: UUID, key: UUID | None = None):
    return service.create_initial(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        InitialWeeklyPlanRequest(),
        key or uuid4(),
    )


def test_cold_start_initial_is_the_only_acknowledgement_exception() -> None:
    service, repository, _, user_id, _ = _fixture()
    response = _initial(service, user_id)

    assert response.source_code == "INITIAL"
    assert response.revision_sequence == 1
    assert response.ai_revision_count == 0
    assert response.finalized is True
    assert response.finalized_at == NOW
    assert response.routine is not None
    assert repository.revisions[0].source_weekly_report_id is None
    serialized_snapshot = json.dumps(repository.revisions[0].input_snapshot)
    assert "user_id" not in serialized_snapshot
    assert "raw_health" not in serialized_snapshot
    assert "wearable" not in serialized_snapshot
    assert "calendar" not in serialized_snapshot


@pytest.mark.parametrize(
    ("report_status", "finalized"),
    [("GENERATED", False), ("ACKNOWLEDGED", True)],
)
def test_previous_report_acknowledgement_controls_finalize_only(
    report_status: str, finalized: bool
) -> None:
    service, repository, resolver, user_id, _ = _fixture()
    report_id = uuid4()
    repository.context = replace(
        repository.context,
        is_first_user_week=False,
        cold_start_applied=False,
        source_weekly_report_id=report_id,
        previous_report_status_code=report_status,
    )
    resolver.response = resolver.response.model_copy(
        update={"plan_origin_code": "WEEKLY_REPORT", "cold_start_applied": False}
    )

    response = _initial(service, user_id)

    assert response.source_weekly_report_id == report_id
    assert response.finalized is finalized
    assert (response.finalized_at is not None) is finalized
    if not finalized:
        assert "PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED" in (response.finalization_reason_codes)


def test_non_cold_start_requires_previous_weekly_report() -> None:
    service, repository, resolver, user_id, _ = _fixture()
    repository.context = replace(
        repository.context, is_first_user_week=False, cold_start_applied=False
    )
    resolver.response = resolver.response.model_copy(
        update={"plan_origin_code": "WEEKLY_REPORT", "cold_start_applied": False}
    )

    with pytest.raises(PreviousWeeklyReportRequiredError):
        _initial(service, user_id)


def test_only_two_successful_ai_revisions_are_allowed() -> None:
    service, _, _, user_id, _ = _fixture()
    _initial(service, user_id)

    first = service.create_revision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=1),
        uuid4(),
    )
    second = service.create_revision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=2),
        uuid4(),
    )

    assert first.ai_revision_count == 1
    assert second.ai_revision_count == 2
    with pytest.raises(AiRevisionLimitReachedError):
        service.create_revision(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            WEEK_START,
            WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=3),
            uuid4(),
        )


@pytest.mark.parametrize("status_code", ["NEEDS_INPUT", "BLOCKED", "FAILED"])
def test_non_plan_safety_status_never_links_or_finalizes_routine(status_code: str) -> None:
    service, repository, _, user_id, _ = _fixture()
    repository.context = replace(repository.context, safety_status_code=status_code)

    response = _initial(service, user_id)

    assert response.safety_status_code == status_code
    assert response.routine is None
    assert response.selected_location_code is None
    assert response.finalized is False
    assert response.finalized_at is None
    assert repository.revisions[0].routine_id is None


def test_non_successful_ai_revision_does_not_consume_ai_count() -> None:
    service, repository, _, user_id, _ = _fixture()
    _initial(service, user_id)
    repository.context = replace(repository.context, safety_status_code="BLOCKED")

    response = service.create_revision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=1),
        uuid4(),
    )

    assert response.source_code == "AI"
    assert response.ai_revision_count == 0
    assert response.routine is None
    assert response.finalized is False
    assert repository.revisions[-1].ai_revision_number is None


@pytest.mark.parametrize(
    ("change", "reason_code"),
    [
        ("duration", "REQUESTED_DURATION_NOT_PRESERVED"),
        ("location", "LOCATION_CONSTRAINT_NOT_SATISFIED"),
        ("equipment", "EQUIPMENT_CONSTRAINT_NOT_SATISFIED"),
        ("safety", "SAFETY_OPINION_NOT_APPLIED"),
    ],
)
def test_user_revision_revalidates_routine_constraints(change: str, reason_code: str) -> None:
    service, repository, _, user_id, routine_id = _fixture()
    _initial(service, user_id)
    location = "HOME"
    evidence = repository.evidence[routine_id]
    if change == "duration":
        repository.evidence[routine_id] = replace(evidence, requested_duration_minutes=30)
    elif change == "location":
        location = "GYM"
    elif change == "equipment":
        repository.context = replace(repository.context, available_equipment_codes=("BAND",))
    else:
        repository.context = replace(
            repository.context,
            safety_status_code="REVISE",
            safety_opinion_codes=("EXCLUDE_CONFLICT",),
            excluded_exercise_ids=(evidence.exercise_ids[0],),
        )

    with pytest.raises(PlanRevisionRejectedError) as error:
        service.create_revision(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            WEEK_START,
            WeeklyPlanRevisionRequest(
                source_code="USER",
                expected_revision_sequence=1,
                user_edits={"routine_id": routine_id, "location_code": location},
            ),
            uuid4(),
        )
    assert reason_code in error.value.reason_codes


def test_user_revision_does_not_consume_ai_revision_count() -> None:
    service, _, _, user_id, routine_id = _fixture()
    _initial(service, user_id)
    ai = service.create_revision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=1),
        uuid4(),
    )
    user = service.create_revision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        WEEK_START,
        WeeklyPlanRevisionRequest(
            source_code="USER",
            expected_revision_sequence=2,
            user_edits={"routine_id": routine_id, "location_code": "HOME"},
        ),
        uuid4(),
    )

    assert ai.ai_revision_count == 1
    assert user.ai_revision_count == 1
    assert user.source_code == "USER"


def test_revision_sequence_and_idempotency_are_enforced() -> None:
    service, repository, _, user_id, _ = _fixture()
    key = uuid4()
    first = _initial(service, user_id, key)
    replay = _initial(service, user_id, key)
    assert replay == first
    assert len(repository.revisions) == 1

    with pytest.raises(IdempotencyKeyReusedError):
        service.create_initial(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            WEEK_START + timedelta(days=7),
            InitialWeeklyPlanRequest(),
            key,
        )
    with pytest.raises(StalePlanRevisionError):
        service.create_revision(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            WEEK_START,
            WeeklyPlanRevisionRequest(source_code="AI", expected_revision_sequence=2),
            uuid4(),
        )
