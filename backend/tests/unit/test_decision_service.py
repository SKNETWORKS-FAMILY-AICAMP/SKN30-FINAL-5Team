from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.domain.agents.contracts import AgentTypeCode, RecommendedActionCode
from backend.app.domain.agents.coordinator import CoordinatorCandidate
from backend.app.domain.rules.duration import DurationPlan, PlanItemDuration
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import (
    DecisionAssembly,
    StoredIdempotency,
)
from backend.app.modules.decisions.schemas import DecisionCreateRequest
from backend.app.modules.decisions.service import (
    DecisionFailedError,
    DecisionService,
    StaleDecisionContextError,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


class FakeSession:
    def begin(self) -> Any:
        return nullcontext()


class FakeRepository:
    def __init__(self, context: DecisionContext) -> None:
        candidate = CoordinatorCandidate(
            candidate_id="candidate-1",
            action_code=RecommendedActionCode.KEEP,
            exercise_ids=("00000000-0000-0000-0000-000000000001",),
            goal_tags=("GENERAL_FITNESS",),
            catalog_version="catalog-v1",
            duration_plan=DurationPlan(
                setup_seconds=0,
                warmup_seconds=60,
                items=(PlanItemDuration(465, 0, 15),),
                cooldown_seconds=60,
            ),
        )
        self.assembly = DecisionAssembly(
            context=context,
            routine_id=uuid4(),
            catalog_version_id=uuid4(),
            catalog_version="catalog-v1",
            catalog_status_code="ACTIVE",
            catalog_review_status_code="DOMAIN_APPROVED",
            catalog_production_eligible=True,
            catalog_activated=True,
            candidate=candidate,
            candidate_data={},
            items=(),
        )
        self.prior: StoredIdempotency | None = None
        self.persisted: dict[str, Any] | None = None

    def acquire_lock(self, session: Any, user_id: UUID, key: UUID) -> None:
        pass

    def get_idempotency(self, session: Any, user_id: UUID, key: UUID) -> StoredIdempotency | None:
        return self.prior

    def assemble(
        self, session: Any, user_id: UUID, daily_context_id: UUID
    ) -> DecisionAssembly | None:
        return self.assembly

    def persist(self, session: Any, **values: Any) -> UUID:
        self.persisted = values
        self.decision_id = uuid4()
        return self.decision_id

    def save_idempotency(self, session: Any, **values: Any) -> None:
        self.prior = StoredIdempotency(values["request_hash"], values["payload"])

    def get_response(self, session: Any, user_id: UUID, decision_id: UUID) -> dict[str, Any] | None:
        if self.persisted is None:
            return None
        result = self.persisted["result"]
        if result.status_code.value == "BLOCKED":
            action = result.final_action_code.value
            return {
                "decision_id": decision_id,
                "local_date": self.assembly.context.local_date,
                "status_code": "COMPLETED",
                "safety_status_code": "BLOCKED",
                "action_code": action,
                "requested_duration_minutes": 10,
                "duration_adjustment_source_code": "PROFILE",
                "final_plan": None,
                "options": [],
                "reason_codes": list(result.reason_codes)[:2],
                "summary": "blocked",
                "guidance": {
                    "code": action,
                    "title": "안전 안내",
                    "message": "운동을 진행하지 마세요.",
                    "tone_code": "SERIOUS",
                },
                "public_agent_summaries": None,
                "safety_summary": None,
                "created_at": NOW,
            }
        if result.selected_candidate_id is None:
            return None
        context = self.assembly.context
        return {
            "decision_id": decision_id,
            "local_date": context.local_date,
            "status_code": "COMPLETED",
            "safety_status_code": "PASS",
            "action_code": "KEEP",
            "requested_duration_minutes": 10,
            "duration_adjustment_source_code": "PROFILE",
            "final_plan": {
                "plan_id": uuid4(),
                "action_code": "KEEP",
                "training_type_code": "STRENGTH",
                "body_focus_code": None,
                "requested_duration_minutes": 10,
                "estimated_duration_seconds": 600,
                "estimated_calories_burned": None,
                "setup_seconds": 0,
                "warmup_seconds": 60,
                "cooldown_seconds": 60,
                "items": [],
            },
            "options": [
                {
                    "option_id": uuid4(),
                    "option_code": "FINAL_ROUTINE",
                    "action_code": "KEEP",
                    "plan_id": uuid4(),
                },
                {
                    "option_id": uuid4(),
                    "option_code": "REST",
                    "action_code": "REST",
                    "plan_id": None,
                },
            ],
            "reason_codes": [],
            "summary": "ready",
            "guidance": None,
            "public_agent_summaries": None,
            "safety_summary": None,
            "created_at": NOW,
        }


def _context(*, version: int = 2, discomforts: tuple[tuple[str, str], ...] = ()) -> DecisionContext:
    return DecisionContext(
        date(2026, 8, 14),
        uuid4(),
        version,
        "LOW",
        10,
        "PROFILE",
        "HOME",
        None,
        None,
        None,
        discomforts,
        (),
        10,
        "GENERAL_FITNESS",
        "BEGINNER",
        (),
    )


def _request(context: DecisionContext, version: int = 2) -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=context.local_date,
        daily_context_id=context.daily_context_id,
        expected_context_version=version,
    )


def test_decision_persists_four_proposals_before_success_and_is_idempotent() -> None:
    context = _context()
    repository = FakeRepository(context)
    service = DecisionService(repository, clock=lambda: NOW)
    key = uuid4()
    first = service.create(FakeSession(), uuid4(), _request(context), key)  # type: ignore[arg-type]
    retry = service.create(FakeSession(), uuid4(), _request(context), key)  # type: ignore[arg-type]
    assert first == retry
    assert len(repository.persisted["proposals"]) == 4  # type: ignore[index]
    snapshot = repository.persisted["input_snapshot"]  # type: ignore[index]
    assert "date_of_birth" not in str(snapshot)
    assert "age" not in snapshot.get("profile", {})


def test_one_missing_proposal_makes_whole_decision_failed_without_plan() -> None:
    context = _context()
    repository = FakeRepository(context)
    agents = tuple(
        agent for agent in default_agents() if agent.agent_type_code is not AgentTypeCode.RECOVERY
    )
    with pytest.raises(DecisionFailedError):
        DecisionService(repository, agents=agents, clock=lambda: NOW).create(
            FakeSession(), uuid4(), _request(context), uuid4()
        )  # type: ignore[arg-type]
    assert repository.persisted["result"].status_code.value == "FAILED"  # type: ignore[index]
    assert repository.persisted["result"].selected_candidate_id is None  # type: ignore[index]


def test_unavailable_discomfort_rules_fail_closed_and_stale_version_is_rejected() -> None:
    context = _context(discomforts=(("KNEE", "MILD"),))
    repository = FakeRepository(context)
    with pytest.raises(DecisionFailedError):
        DecisionService(repository, clock=lambda: NOW).create(
            FakeSession(), uuid4(), _request(context), uuid4()
        )  # type: ignore[arg-type]
    safety = next(
        p for p in repository.persisted["proposals"] if p.agent_type_code is AgentTypeCode.SAFETY
    )  # type: ignore[index]
    assert safety.safety_vetoed is True
    with pytest.raises(StaleDecisionContextError):
        DecisionService(FakeRepository(context), clock=lambda: NOW).create(
            FakeSession(), uuid4(), _request(context, 1), uuid4()
        )  # type: ignore[arg-type]


def test_safety_veto_cannot_return_a_success_plan() -> None:
    base = _context()
    context = DecisionContext(
        base.local_date,
        base.daily_context_id,
        base.context_version,
        base.fatigue_level_code,
        base.requested_duration_minutes,
        base.duration_adjustment_source_code,
        base.location_code,
        base.sleep_minutes,
        base.fasting_state_code,
        base.hydration_state_code,
        (),
        ("CHEST_DISCOMFORT",),
        base.profile_duration_minutes,
        base.primary_goal_code,
        base.experience_level_code,
        base.equipment_codes,
    )
    response = DecisionService(FakeRepository(context), clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]
    assert response.safety_status_code == "BLOCKED"
    assert response.action_code == "STOP_AND_SEEK_HELP"
    assert response.final_plan is None
    assert response.options == []
