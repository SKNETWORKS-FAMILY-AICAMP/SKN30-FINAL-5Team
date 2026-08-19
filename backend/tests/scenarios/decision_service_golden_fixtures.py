"""Synthetic inputs for exercising the production decision pipeline end to end."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from backend.app.domain.agents.contracts import AgentProposal, RecommendedActionCode
from backend.app.domain.agents.coordinator import CoordinatorCandidate, CoordinatorResult
from backend.app.domain.rules.duration import (
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
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
    SafetyStatusCode,
)
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import (
    AlternativeItemData,
    CandidateItemData,
    DecisionAssembly,
    NarrationProviderPort,
    StoredIdempotency,
)
from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse
from backend.app.modules.decisions.service import DecisionService

NOW = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 8, 18)
USER_ID = UUID("00000000-0000-0000-0000-000000000062")
DAILY_CONTEXT_ID = UUID("00000000-0000-0000-0000-000000000063")
ROUTINE_ID = UUID("00000000-0000-0000-0000-000000000064")
CATALOG_VERSION_ID = UUID("00000000-0000-0000-0000-000000000065")
BASE_EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000066")
ALTERNATIVE_EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000067")
DECISION_ID = UUID("00000000-0000-0000-0000-000000000068")
CATALOG_VERSION = "golden-approved-catalog-v2"
SAFETY_RULE_VERSION = "golden-safety-rules-v2"


@dataclass(frozen=True, slots=True)
class ServiceGoldenExpected:
    action_code: str
    safety_status_code: SafetyStatusCode
    safety_vetoed: bool
    selected_candidate_suffix: str | None
    excluded_exercise_ids: tuple[str, ...] = ()
    replacement_exercise_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceDecisionGoldenCase:
    case_code: str
    requested_duration_minutes: int = 40
    profile_duration_minutes: int = 40
    duration_source: DurationAdjustmentSourceCode = DurationAdjustmentSourceCode.PROFILE
    fatigue_level_code: str = "LOW"
    discomforts: tuple[tuple[str, str], ...] = ()
    attention_area_codes: tuple[str, ...] = ()
    adverse_reaction_codes: tuple[str, ...] = ()
    safety_effect: SafetyRuleEffectCode | None = None
    with_approved_alternative: bool = False
    wearable_input_mode: str = "NOT_APPLICABLE"
    explanation_execution_modes: tuple[str, ...] = ("LLM_DISABLED",)
    expected: ServiceGoldenExpected = ServiceGoldenExpected(
        action_code="KEEP",
        safety_status_code=SafetyStatusCode.PASS,
        safety_vetoed=False,
        selected_candidate_suffix="candidate-original",
    )


SERVICE_DECISION_GOLDEN_CASES: tuple[ServiceDecisionGoldenCase, ...] = (
    ServiceDecisionGoldenCase(
        case_code="HEALTHY_KEEP",
        expected=ServiceGoldenExpected("KEEP", SafetyStatusCode.PASS, False, "candidate-original"),
    ),
    ServiceDecisionGoldenCase(
        case_code="REQUESTED_DURATION_PRESERVING_DOWNSHIFT",
        requested_duration_minutes=30,
        profile_duration_minutes=40,
        duration_source=DurationAdjustmentSourceCode.USER_OVERRIDE,
        fatigue_level_code="MODERATE",
        expected=ServiceGoldenExpected(
            "DOWNSHIFT",
            SafetyStatusCode.PASS,
            False,
            "approved-downshift",
        ),
    ),
    ServiceDecisionGoldenCase(
        case_code="KNEE_MODERATE_APPROVED_REPLACEMENT",
        discomforts=(("KNEE", "MODERATE"),),
        safety_effect=SafetyRuleEffectCode.EXCLUDE,
        with_approved_alternative=True,
        expected=ServiceGoldenExpected(
            "CHANGE",
            SafetyStatusCode.REVISE,
            True,
            "safety-change",
            excluded_exercise_ids=(str(BASE_EXERCISE_ID),),
            replacement_exercise_id=str(ALTERNATIVE_EXERCISE_ID),
        ),
    ),
    ServiceDecisionGoldenCase(
        case_code="WEARABLE_MISSING_MANUAL_FALLBACK",
        wearable_input_mode="MANUAL_CHECK_IN_ONLY",
        expected=ServiceGoldenExpected("KEEP", SafetyStatusCode.PASS, False, "candidate-original"),
    ),
    ServiceDecisionGoldenCase(
        case_code="LLM_DISABLED_OR_FAILED_SAME_DECISION",
        explanation_execution_modes=("LLM_DISABLED", "LLM_FAILED"),
        expected=ServiceGoldenExpected("KEEP", SafetyStatusCode.PASS, False, "candidate-original"),
    ),
    ServiceDecisionGoldenCase(
        case_code="SAFETY_VETO_BYPASS_BLOCKED",
        discomforts=(("KNEE", "SEVERE"),),
        expected=ServiceGoldenExpected("REST", SafetyStatusCode.BLOCKED, True, None),
    ),
    ServiceDecisionGoldenCase(
        case_code="KNEE_MILD_CAUTION_DOWNSHIFT",
        discomforts=(("KNEE", "MILD"),),
        safety_effect=SafetyRuleEffectCode.CAUTION,
        expected=ServiceGoldenExpected(
            "DOWNSHIFT",
            SafetyStatusCode.REVISE,
            False,
            "approved-downshift",
        ),
    ),
    ServiceDecisionGoldenCase(
        case_code="KNEE_MODERATE_APPROVED_ALTERNATIVE",
        discomforts=(("KNEE", "MODERATE"),),
        safety_effect=SafetyRuleEffectCode.EXCLUDE,
        with_approved_alternative=True,
        expected=ServiceGoldenExpected(
            "CHANGE",
            SafetyStatusCode.REVISE,
            True,
            "safety-change",
            excluded_exercise_ids=(str(BASE_EXERCISE_ID),),
            replacement_exercise_id=str(ALTERNATIVE_EXERCISE_ID),
        ),
    ),
    ServiceDecisionGoldenCase(
        case_code="CHRONIC_KNEE_ATTENTION_CAUTION",
        attention_area_codes=("KNEE",),
        safety_effect=SafetyRuleEffectCode.CAUTION,
        expected=ServiceGoldenExpected(
            "DOWNSHIFT",
            SafetyStatusCode.REVISE,
            False,
            "approved-downshift",
        ),
    ),
)


class GoldenSession:
    def begin(self) -> Any:
        return nullcontext()


def case_by_code(case_code: str) -> ServiceDecisionGoldenCase:
    return next(case for case in SERVICE_DECISION_GOLDEN_CASES if case.case_code == case_code)


def _duration_plan(minutes: int) -> DurationPlan:
    target_seconds = minutes * 60
    return DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(PlanItemDuration(target_seconds - 360, 120, 15),),
        cooldown_seconds=75,
    )


def _candidate_item(minutes: int, *, alternative: bool = False) -> CandidateItemData:
    exercise_id = ALTERNATIVE_EXERCISE_ID if alternative else BASE_EXERCISE_ID
    work_seconds = minutes * 60 - 360
    return CandidateItemData(
        exercise_id=exercise_id,
        sequence=1,
        phase_code="MAIN",
        tier_code="CORE",
        sets=1,
        reps=None,
        work_seconds_per_set=work_seconds,
        rest_seconds_per_set=120,
        transition_seconds=15,
        intensity_code="LOW" if alternative else "MODERATE",
        instruction_content_version="golden-instruction-v1",
        display_name="합성 대체 운동" if alternative else "합성 기본 운동",
        work_seconds=work_seconds,
        rest_seconds=120,
    )


def _safety_rule_set(case: ServiceDecisionGoldenCase) -> SafetyRuleSet | None:
    if case.safety_effect is None:
        return None
    severity = (
        DiscomfortSeverityCode.MODERATE
        if case.safety_effect is SafetyRuleEffectCode.EXCLUDE
        else DiscomfortSeverityCode.MILD
    )
    return SafetyRuleSet(
        version_code=SAFETY_RULE_VERSION,
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=True,
        rules=(
            SafetyRule(
                rule_code=f"KNEE_{case.safety_effect.value}_GOLDEN",
                catalog_version_code=CATALOG_VERSION,
                body_area_code=BodyAreaCode.KNEE,
                minimum_severity_code=severity,
                maximum_severity_code=severity,
                effect_code=case.safety_effect,
                reason_code="DIRECT_JOINT_LOAD",
                scope_code=SafetyRuleScopeCode.EXERCISE,
                rule_version="golden-rule-v1",
                exercise_code=str(BASE_EXERCISE_ID),
            ),
        ),
    )


class RecordingDecisionRepository:
    """Repository port double; it supplies data but delegates every decision to production code."""

    def __init__(self, case: ServiceDecisionGoldenCase) -> None:
        self.case = case
        self.prior: StoredIdempotency | None = None
        self.persisted: dict[str, Any] | None = None
        duration_plan = _duration_plan(case.requested_duration_minutes)
        candidate = CoordinatorCandidate(
            candidate_id="candidate-original",
            action_code=RecommendedActionCode.KEEP,
            exercise_ids=(str(BASE_EXERCISE_ID),),
            goal_tags=("GENERAL_FITNESS",),
            catalog_version=CATALOG_VERSION,
            duration_plan=duration_plan,
        )
        item = _candidate_item(case.requested_duration_minutes)
        context = DecisionContext(
            LOCAL_DATE,
            DAILY_CONTEXT_ID,
            1,
            case.fatigue_level_code,
            case.requested_duration_minutes,
            case.duration_source.value,
            "HOME",
            None,
            None,
            None,
            case.discomforts,
            case.adverse_reaction_codes,
            case.profile_duration_minutes,
            "GENERAL_FITNESS",
            "BEGINNER",
            ("BODYWEIGHT", "MAT"),
            case.attention_area_codes,
            "HOME",
            (),
            ("BODYWEIGHT",),
            ("HOME",),
        )
        alternative_item = _candidate_item(case.requested_duration_minutes, alternative=True)
        self.assembly = DecisionAssembly(
            context=context,
            routine_id=ROUTINE_ID,
            catalog_version_id=CATALOG_VERSION_ID,
            catalog_version=CATALOG_VERSION,
            catalog_status_code="ACTIVE",
            catalog_review_status_code="DOMAIN_APPROVED",
            catalog_production_eligible=True,
            catalog_activated=True,
            candidate=candidate,
            candidate_data={
                "candidate_code": candidate.candidate_id,
                "training_type_code": "STRENGTH",
                "body_focus_code": "LOWER_BODY",
                "requested_duration_minutes": case.requested_duration_minutes,
                "estimated_duration_seconds": case.requested_duration_minutes * 60,
                "estimated_calories_burned": None,
                "setup_seconds": duration_plan.setup_seconds,
                "warmup_seconds": duration_plan.warmup_seconds,
                "cooldown_seconds": duration_plan.cooldown_seconds,
                "goal_tags": ["GENERAL_FITNESS"],
            },
            items=(item,),
            safety_candidate=SafetyCandidate(
                items=(
                    SafetyCandidateItem(str(BASE_EXERCISE_ID), CATALOG_VERSION, "KNEE_DOMINANT"),
                )
            ),
            safety_rule_set=_safety_rule_set(case),
            alternative_items=(
                (
                    AlternativeItemData(
                        source_exercise_id=BASE_EXERCISE_ID,
                        item=alternative_item,
                        safety_item=SafetyCandidateItem(
                            str(ALTERNATIVE_EXERCISE_ID), CATALOG_VERSION, "HIP_DOMINANT"
                        ),
                        evidence_reference_code="ALTERNATIVE/golden-approved-relation",
                    ),
                )
                if case.with_approved_alternative
                else ()
            ),
        )

    def acquire_lock(self, _session: Any, _user_id: UUID, _key: UUID) -> None:
        return None

    def get_idempotency(
        self, _session: Any, _user_id: UUID, _key: UUID
    ) -> StoredIdempotency | None:
        return self.prior

    def assemble(self, _session: Any, _user_id: UUID, _daily_context_id: UUID) -> DecisionAssembly:
        return self.assembly

    def persist(self, _session: Any, **values: Any) -> UUID:
        self.persisted = values
        return DECISION_ID

    def save_idempotency(self, _session: Any, **values: Any) -> None:
        self.prior = StoredIdempotency(values["request_hash"], values["payload"])

    def get_response(
        self, _session: Any, _user_id: UUID, decision_id: UUID
    ) -> dict[str, Any] | None:
        if self.persisted is None:
            return None
        result: CoordinatorResult = self.persisted["result"]
        context = self.persisted["assembly"].context
        if result.selected_candidate_id is None:
            action_code = result.final_action_code.value if result.final_action_code else "REST"
            return {
                "decision_id": decision_id,
                "local_date": context.local_date,
                "status_code": "COMPLETED",
                "safety_status_code": result.safety_status_code.value,
                "action_code": action_code,
                "requested_duration_minutes": context.requested_duration_minutes,
                "duration_adjustment_source_code": context.duration_adjustment_source_code,
                "final_plan": None,
                "options": [],
                "reason_codes": list(result.reason_codes[:2]),
                "summary": "합성 안전 결과",
                "guidance": {
                    "code": action_code,
                    "title": "안전 안내",
                    "message": "운동을 진행하지 마세요.",
                    "tone_code": "SERIOUS",
                },
                "public_agent_summaries": None,
                "safety_summary": None,
                "created_at": NOW,
            }
        selected = next(
            candidate
            for candidate in self.persisted["assembly"].coordinator_candidates
            if candidate.candidate_id == result.selected_candidate_id
        )
        return {
            "decision_id": decision_id,
            "local_date": context.local_date,
            "status_code": "COMPLETED",
            "safety_status_code": result.safety_status_code.value,
            "action_code": result.final_action_code.value,
            "requested_duration_minutes": context.requested_duration_minutes,
            "duration_adjustment_source_code": context.duration_adjustment_source_code,
            "final_plan": {
                "plan_id": DECISION_ID,
                "action_code": result.final_action_code.value,
                "training_type_code": "STRENGTH",
                "body_focus_code": "LOWER_BODY",
                "requested_duration_minutes": context.requested_duration_minutes,
                "estimated_duration_seconds": selected.estimated_duration_seconds,
                "estimated_calories_burned": None,
                "setup_seconds": selected.duration_plan.setup_seconds,
                "warmup_seconds": selected.duration_plan.warmup_seconds,
                "cooldown_seconds": selected.duration_plan.cooldown_seconds,
                "items": [],
            },
            "options": [
                {
                    "option_id": DECISION_ID,
                    "option_code": "FINAL_ROUTINE",
                    "action_code": result.final_action_code.value,
                    "plan_id": DECISION_ID,
                    "selectable": True,
                    "blocked_reason_code": None,
                }
            ],
            "reason_codes": list(result.reason_codes[:2]),
            "adjustment_reason_codes": None,
            "summary": "합성 결정 결과",
            "guidance": None,
            "public_agent_summaries": None,
            "safety_summary": None,
            "created_at": NOW,
        }


def safety_proposal(repository: RecordingDecisionRepository) -> AgentProposal:
    assert repository.persisted is not None
    return next(
        proposal
        for proposal in repository.persisted["proposals"]
        if proposal.agent_type_code.value == "SAFETY"
    )


def execute_service_case(
    case: ServiceDecisionGoldenCase,
    *,
    narration_provider: NarrationProviderPort | None = None,
) -> tuple[DecisionResponse, RecordingDecisionRepository]:
    """Run the production decision service; narration stays optional and non-deciding."""

    repository = RecordingDecisionRepository(case)
    response = DecisionService(
        repository,
        narration_provider=narration_provider,
        clock=lambda: NOW,
    ).create(
        GoldenSession(),  # type: ignore[arg-type]
        USER_ID,
        DecisionCreateRequest(
            local_date=LOCAL_DATE,
            daily_context_id=DAILY_CONTEXT_ID,
            expected_context_version=1,
        ),
        UUID("00000000-0000-0000-0000-000000000069"),
    )
    return response, repository


__all__ = [
    "ALTERNATIVE_EXERCISE_ID",
    "BASE_EXERCISE_ID",
    "DAILY_CONTEXT_ID",
    "GoldenSession",
    "RecordingDecisionRepository",
    "SERVICE_DECISION_GOLDEN_CASES",
    "ServiceDecisionGoldenCase",
    "USER_ID",
    "case_by_code",
    "execute_service_case",
    "safety_proposal",
]
