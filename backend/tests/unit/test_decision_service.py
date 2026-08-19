from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.domain.agents.contracts import AgentTypeCode, RecommendedActionCode
from backend.app.domain.agents.coordinator import CoordinatorCandidate
from backend.app.domain.rules.duration import DurationPlan, PlanItemDuration
from backend.app.domain.rules.safety import (
    BodyAreaCode,
    DiscomfortSeverityCode,
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyReviewStatusCode,
    SafetyRule,
    SafetyRuleEffectCode,
    SafetyRuleScopeCode,
    SafetyRuleSet,
)
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import (
    AlternativeItemData,
    CandidateItemData,
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
BASE_EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000001")
ALTERNATIVE_EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000002")


class FakeSession:
    def begin(self) -> Any:
        return nullcontext()


class FakeRepository:
    def __init__(
        self,
        context: DecisionContext,
        *,
        safety_rule_set: SafetyRuleSet | None = None,
        with_alternative: bool = False,
    ) -> None:
        candidate = CoordinatorCandidate(
            candidate_id="candidate-1",
            action_code=RecommendedActionCode.KEEP,
            exercise_ids=(str(BASE_EXERCISE_ID),),
            goal_tags=("GENERAL_FITNESS",),
            catalog_version="catalog-v1",
            duration_plan=DurationPlan(
                setup_seconds=0,
                warmup_seconds=60,
                items=(PlanItemDuration(465, 0, 15),),
                cooldown_seconds=60,
            ),
        )
        item = CandidateItemData(
            exercise_id=BASE_EXERCISE_ID,
            sequence=1,
            phase_code="MAIN",
            tier_code="CORE",
            sets=1,
            reps=None,
            work_seconds_per_set=465,
            rest_seconds_per_set=0,
            transition_seconds=15,
            intensity_code="MODERATE",
            instruction_content_version="1.0.0",
            display_name="기본 운동",
            work_seconds=465,
            rest_seconds=0,
        )
        alternative_item = CandidateItemData(
            **{
                **{name: getattr(item, name) for name in item.__dataclass_fields__},
                "exercise_id": ALTERNATIVE_EXERCISE_ID,
                "intensity_code": "LOW",
                "display_name": "대체 운동",
            }
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
            items=(item,),
            safety_candidate=SafetyCandidate(
                items=(SafetyCandidateItem(str(BASE_EXERCISE_ID), "catalog-v1", "KNEE_DOMINANT"),)
            ),
            safety_rule_set=safety_rule_set,
            alternative_items=(
                (
                    AlternativeItemData(
                        source_exercise_id=BASE_EXERCISE_ID,
                        item=alternative_item,
                        safety_item=SafetyCandidateItem(
                            str(ALTERNATIVE_EXERCISE_ID), "catalog-v1", "HIP_DOMINANT"
                        ),
                        evidence_reference_code="ALTERNATIVE/relation-1",
                    ),
                )
                if with_alternative
                else ()
            ),
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

    def get_response_for_date(
        self, session: Any, user_id: UUID, local_date: Any
    ) -> dict[str, Any] | None:
        if self.persisted is None or self.assembly.context.local_date != local_date:
            return None
        result = self.persisted["result"]
        if result.status_code.value in {"NEEDS_INPUT", "FAILED"}:
            return None
        return self.get_response(session, user_id, self.decision_id)

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
        safety_proposal = next(
            proposal
            for proposal in self.persisted["proposals"]
            if proposal.agent_type_code is AgentTypeCode.SAFETY
        )
        return {
            "decision_id": decision_id,
            "local_date": context.local_date,
            "status_code": "COMPLETED",
            "safety_status_code": result.safety_status_code.value,
            "action_code": result.final_action_code.value,
            "requested_duration_minutes": 10,
            "duration_adjustment_source_code": "PROFILE",
            "final_plan": {
                "plan_id": uuid4(),
                "action_code": result.final_action_code.value,
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
                    "action_code": result.final_action_code.value,
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
            "adjustment_reason_codes": (
                list(safety_proposal.reason_codes)[:2]
                if result.final_action_code is not RecommendedActionCode.KEEP
                else None
            ),
            "summary": "ready",
            "guidance": None,
            "public_agent_summaries": None,
            "safety_summary": None,
            "created_at": NOW,
        }


def _context(
    *,
    version: int = 2,
    discomforts: tuple[tuple[str, str], ...] = (),
    attention_area_codes: tuple[str, ...] = (),
) -> DecisionContext:
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
        attention_area_codes,
    )


def _request(context: DecisionContext, version: int = 2) -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=context.local_date,
        daily_context_id=context.daily_context_id,
        expected_context_version=version,
    )


def _approved_rule_set(effect: SafetyRuleEffectCode) -> SafetyRuleSet:
    severity = (
        DiscomfortSeverityCode.MILD
        if effect is SafetyRuleEffectCode.CAUTION
        else DiscomfortSeverityCode.MODERATE
    )
    return SafetyRuleSet(
        version_code="safety-v2",
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=True,
        rules=(
            SafetyRule(
                rule_code=f"KNEE_{effect.value}",
                catalog_version_code="catalog-v1",
                body_area_code=BodyAreaCode.KNEE,
                minimum_severity_code=severity,
                maximum_severity_code=severity,
                effect_code=effect,
                reason_code="DIRECT_JOINT_LOAD",
                scope_code=SafetyRuleScopeCode.MOVEMENT_PATTERN,
                rule_version="2.0.0",
                movement_pattern_code="KNEE_DOMINANT",
            ),
        ),
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
    assert snapshot["profile"]["attention_area_codes"] == []


def test_attention_areas_are_canonical_snapshot_inputs_and_apply_caution() -> None:
    base_context = _context()
    rule_set = _approved_rule_set(SafetyRuleEffectCode.CAUTION)
    first_repository = FakeRepository(
        replace(base_context, attention_area_codes=("SHOULDER", "KNEE", "SHOULDER")),
        safety_rule_set=rule_set,
    )
    reordered_repository = FakeRepository(
        replace(base_context, attention_area_codes=("KNEE", "SHOULDER")),
        safety_rule_set=rule_set,
    )
    different_repository = FakeRepository(
        replace(base_context, attention_area_codes=("LOWER_BACK",)),
        safety_rule_set=rule_set,
    )
    empty_repository = FakeRepository(base_context)

    for repository in (
        first_repository,
        reordered_repository,
        different_repository,
        empty_repository,
    ):
        context = repository.assembly.context
        DecisionService(repository, clock=lambda: NOW).create(
            FakeSession(), uuid4(), _request(context), uuid4()
        )  # type: ignore[arg-type]

    first_snapshot = first_repository.persisted["input_snapshot"]  # type: ignore[index]
    reordered_snapshot = reordered_repository.persisted["input_snapshot"]  # type: ignore[index]
    assert first_repository.assembly.context.attention_area_codes == ("KNEE", "SHOULDER")
    assert first_snapshot == reordered_snapshot
    assert first_snapshot["profile"]["attention_area_codes"] == ["KNEE", "SHOULDER"]
    assert (
        first_repository.persisted["input_hash"]  # type: ignore[index]
        == reordered_repository.persisted["input_hash"]  # type: ignore[index]
    )
    assert (
        first_repository.persisted["input_hash"]  # type: ignore[index]
        != different_repository.persisted["input_hash"]  # type: ignore[index]
    )
    assert first_repository.persisted["result"] == reordered_repository.persisted["result"]  # type: ignore[index]
    assert first_repository.persisted["result"] != empty_repository.persisted["result"]  # type: ignore[index]
    assert first_repository.persisted["result"].status_code.value == "REVISE"  # type: ignore[index]
    assert first_repository.persisted["result"].safety_status_code.value == "REVISE"  # type: ignore[index]
    assert first_repository.persisted["result"].final_action_code.value == "DOWNSHIFT"  # type: ignore[index]


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


def test_mild_caution_returns_duration_preserving_downshift() -> None:
    context = _context(discomforts=(("KNEE", "MILD"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.CAUTION),
    )

    response = DecisionService(repository, clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]

    assert response.safety_status_code == "REVISE"
    assert response.action_code == "DOWNSHIFT"
    assert response.requested_duration_minutes == 10
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 600
    assert "SAFETY_CAUTION_APPLIED" in (response.adjustment_reason_codes or [])
    assert repository.persisted["result"].safety_rule_version == "safety-v2"  # type: ignore[index]


def test_moderate_fatigue_returns_duration_preserving_downshift() -> None:
    context = replace(_context(), fatigue_level_code="MODERATE")
    repository = FakeRepository(context)

    response = DecisionService(repository, clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]

    recovery = next(
        proposal
        for proposal in repository.persisted["proposals"]  # type: ignore[index]
        if proposal.agent_type_code is AgentTypeCode.RECOVERY
    )
    assert response.action_code == "DOWNSHIFT"
    assert response.requested_duration_minutes == 10
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 600
    assert recovery.recommended_action_code is RecommendedActionCode.DOWNSHIFT
    assert repository.persisted["assembly"].adjusted_candidates[0].items[0].intensity_code == "LOW"  # type: ignore[index]


def test_moderate_exclusion_uses_approved_alternative_and_preserves_duration() -> None:
    context = _context(discomforts=(("KNEE", "MODERATE"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.EXCLUDE),
        with_alternative=True,
    )

    response = DecisionService(repository, clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]

    assert response.safety_status_code == "REVISE"
    assert response.action_code == "CHANGE"
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 600
    assert "SAFETY_EXERCISES_REPLACED" in (response.adjustment_reason_codes or [])
    prepared = repository.persisted["assembly"]  # type: ignore[index]
    assert prepared.adjusted_candidates[-1].candidate.exercise_ids == (
        str(ALTERNATIVE_EXERCISE_ID),
    )
    safety_proposal = next(
        proposal
        for proposal in repository.persisted["proposals"]  # type: ignore[index]
        if proposal.agent_type_code is AgentTypeCode.SAFETY
    )
    assert "ALTERNATIVE/relation-1" in safety_proposal.evidence_reference_codes


def test_moderate_exclusion_without_approved_alternative_returns_rest() -> None:
    context = _context(discomforts=(("KNEE", "MODERATE"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.EXCLUDE),
    )

    response = DecisionService(repository, clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]

    assert response.safety_status_code == "BLOCKED"
    assert response.action_code == "REST"
    assert response.final_plan is None


def test_safety_veto_cannot_return_a_success_plan() -> None:
    base = _context()
    context = DecisionContext(
        base.local_date,
        base.daily_context_id,
        base.context_version,
        "MODERATE",
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
        base.attention_area_codes,
    )
    response = DecisionService(FakeRepository(context), clock=lambda: NOW).create(
        FakeSession(), uuid4(), _request(context), uuid4()
    )  # type: ignore[arg-type]
    assert response.safety_status_code == "BLOCKED"
    assert response.action_code == "STOP_AND_SEEK_HELP"
    assert response.final_plan is None
    assert response.options == []
