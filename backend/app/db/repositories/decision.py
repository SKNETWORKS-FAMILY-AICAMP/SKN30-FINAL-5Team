from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import CatalogVersion, Exercise
from backend.app.db.models.checkin import (
    DailyContext,
    DailyContextAdverseReaction,
    DailyContextDiscomfort,
)
from backend.app.db.models.decision import (
    AgentProposalRecord,
    DecisionOption,
    DecisionPolicyVersion,
    DecisionRun,
    PlanCandidate,
    PlanItem,
    SafetyReview,
)
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAttentionArea,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay
from backend.app.domain.agents.contracts import RecommendedActionCode
from backend.app.domain.agents.coordinator import (
    CoordinatorCandidate,
    CoordinatorResult,
    CoordinatorStatusCode,
)
from backend.app.domain.rules.duration import DURATION_RULE_VERSION, DurationPlan, PlanItemDuration
from backend.app.modules.decisions.codes import (
    DECISION_ENDPOINT_CODE,
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
    DECISION_RESPONSE_SCHEMA_VERSION,
)
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import (
    CandidateItemData,
    DecisionAssembly,
    StoredIdempotency,
)


class DecisionRepository:
    def acquire_lock(self, session: Session, user_id: UUID, key: UUID) -> None:
        lock_key = int.from_bytes(
            sha256(f"{user_id}:{key}".encode()).digest()[:8], "big", signed=True
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_idempotency(
        self, session: Session, user_id: UUID, key: UUID
    ) -> StoredIdempotency | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == DECISION_ENDPOINT_CODE,
                MutationIdempotencyRecord.idempotency_key == key,
            )
        )
        return None if row is None else StoredIdempotency(row.request_hash, row.response_payload)

    def assemble(
        self, session: Session, user_id: UUID, daily_context_id: UUID
    ) -> DecisionAssembly | None:
        daily = session.scalar(
            select(DailyContext)
            .where(DailyContext.id == daily_context_id, DailyContext.user_id == user_id)
            .with_for_update()
        )
        profile = session.get(UserProfile, user_id)
        if daily is None or profile is None:
            return None
        routine = session.scalar(
            select(Routine)
            .options(selectinload(Routine.days).selectinload(RoutineDay.items))
            .where(
                Routine.user_id == user_id,
                Routine.status_code == "ACTIVE",
                Routine.effective_from <= daily.local_date,
                (Routine.effective_to.is_(None)) | (Routine.effective_to >= daily.local_date),
            )
            .order_by(Routine.version.desc())
        )
        if routine is None or not routine.days:
            return None
        catalog = session.get(CatalogVersion, routine.catalog_version_id)
        if catalog is None:
            return None
        if not (
            catalog.status_code == "ACTIVE"
            and catalog.review_status_code == "DOMAIN_APPROVED"
            and catalog.production_eligible
            and catalog.activated_at is not None
        ):
            return None
        day = routine.days[
            (daily.local_date.toordinal() - routine.effective_from.toordinal()) % len(routine.days)
        ]
        exercise_ids = [item.exercise_id for item in day.items]
        exercises = {
            row.id: row
            for row in session.scalars(select(Exercise).where(Exercise.id.in_(exercise_ids))).all()
        }
        if len(exercises) != len(set(exercise_ids)):
            return None
        discomforts = tuple(
            (body_area_code, severity_code)
            for body_area_code, severity_code in sorted(
                session.execute(
                    select(
                        DailyContextDiscomfort.body_area_code, DailyContextDiscomfort.severity_code
                    ).where(DailyContextDiscomfort.daily_context_id == daily.id)
                ).all()
            )
        )
        reactions = tuple(
            sorted(
                session.scalars(
                    select(DailyContextAdverseReaction.reaction_code).where(
                        DailyContextAdverseReaction.daily_context_id == daily.id
                    )
                ).all()
            )
        )
        equipment = tuple(
            sorted(
                session.scalars(
                    select(UserEquipment.equipment_code).where(UserEquipment.user_id == user_id)
                ).all()
            )
        )
        attention_areas = tuple(
            sorted(
                set(
                    session.scalars(
                        select(UserAttentionArea.body_area_code).where(
                            UserAttentionArea.user_id == user_id,
                            UserAttentionArea.is_active.is_(True),
                        )
                    ).all()
                )
            )
        )
        context = DecisionContext(
            daily.local_date,
            daily.id,
            daily.context_version,
            daily.fatigue_level_code,
            daily.requested_duration_minutes,
            daily.duration_adjustment_source_code,
            daily.location_code,
            daily.sleep_minutes,
            daily.fasting_state_code,
            daily.hydration_state_code,
            discomforts,
            reactions,
            profile.default_requested_duration_minutes,
            profile.primary_goal_code,
            profile.experience_level_code,
            equipment,
            attention_areas,
        )
        item_data: list[CandidateItemData] = []
        main_durations: list[PlanItemDuration] = []
        warmup_seconds = 0
        cooldown_seconds = 0
        for item in day.items:
            exercise = exercises[item.exercise_id]
            work_per_set: int | None
            if item.reps is not None:
                if exercise.default_seconds_per_rep is None:
                    return None
                work_per_set = item.reps * exercise.default_seconds_per_rep
            else:
                work_per_set = item.work_seconds_per_set
            if work_per_set is None:
                return None
            duration = PlanItemDuration(
                item.sets * work_per_set,
                max(item.sets - 1, 0) * item.rest_seconds_per_set,
                exercise.default_transition_seconds,
            )
            if item.phase_code == "WARMUP":
                warmup_seconds += duration.estimated_item_seconds
            elif item.phase_code == "COOLDOWN":
                cooldown_seconds += duration.estimated_item_seconds
            else:
                main_durations.append(duration)
            item_data.append(
                CandidateItemData(
                    item.exercise_id,
                    item.sequence,
                    item.phase_code,
                    item.tier_code,
                    item.sets,
                    item.reps,
                    item.work_seconds_per_set,
                    item.rest_seconds_per_set,
                    exercise.default_transition_seconds,
                    item.intensity_code,
                    exercise.instruction_content_version,
                    exercise.name_ko,
                    duration.work_seconds,
                    duration.rest_seconds,
                )
            )
        duration_plan = DurationPlan(
            day.setup_seconds, warmup_seconds, tuple(main_durations), cooldown_seconds
        )
        candidate_code = f"routine-day-{day.id}"
        candidate = CoordinatorCandidate(
            candidate_id=candidate_code,
            action_code=RecommendedActionCode.KEEP,
            exercise_ids=tuple(sorted(str(value) for value in set(exercise_ids))),
            goal_tags=(routine.goal_code,),
            catalog_version=catalog.version_code,
            duration_plan=duration_plan,
        )
        candidate_data = {
            "candidate_code": candidate_code,
            "training_type_code": day.training_type_code,
            "body_focus_code": day.body_focus_code,
            "requested_duration_minutes": daily.requested_duration_minutes,
            "estimated_duration_seconds": candidate.estimated_duration_seconds,
            "estimated_calories_burned": day.estimated_calories_burned,
            "setup_seconds": day.setup_seconds,
            "warmup_seconds": warmup_seconds,
            "cooldown_seconds": cooldown_seconds,
            "goal_tags": [routine.goal_code],
        }
        return DecisionAssembly(
            context,
            routine.id,
            catalog.id,
            catalog.version_code,
            "ACTIVE",
            "DOMAIN_APPROVED",
            True,
            True,
            candidate,
            candidate_data,
            tuple(item_data),
        )

    def persist(
        self,
        session: Session,
        *,
        user_id: UUID,
        assembly: DecisionAssembly,
        input_snapshot: dict[str, Any],
        input_hash: str,
        proposals: tuple[Any, ...],
        result: CoordinatorResult,
        now: datetime,
    ) -> UUID:
        policy = session.scalar(
            select(DecisionPolicyVersion).where(
                DecisionPolicyVersion.version_code == DECISION_POLICY_VERSION
            )
        )
        if policy is None:
            raise RuntimeError("decision policy version is not installed")
        run = DecisionRun(
            id=uuid4(),
            user_id=user_id,
            local_date=assembly.context.local_date,
            daily_context_id=assembly.context.daily_context_id,
            daily_context_version=assembly.context.context_version,
            base_routine_id=assembly.routine_id,
            input_schema_version=DECISION_INPUT_SCHEMA_VERSION,
            input_snapshot=input_snapshot,
            input_hash=input_hash,
            catalog_version_id=assembly.catalog_version_id,
            policy_version_id=policy.id,
            safety_rule_version=result.safety_rule_version,
            duration_rule_version=DURATION_RULE_VERSION,
            graph_version="decision-graph-v1",
            coordinator_version=result.coordinator_version,
            status_code=(
                "COMPLETED"
                if result.status_code
                in {
                    CoordinatorStatusCode.PASS,
                    CoordinatorStatusCode.REVISE,
                    CoordinatorStatusCode.BLOCKED,
                }
                else result.status_code.value
            ),
            safety_status_code=result.safety_status_code.value,
            recommended_action_code=result.final_action_code.value
            if result.final_action_code
            else None,
            coordinator_result=result.model_dump(mode="json"),
            failure_code=(
                result.reason_codes[0]
                if result.status_code is CoordinatorStatusCode.FAILED and result.reason_codes
                else None
            ),
            created_at=now,
            completed_at=now,
        )
        session.add(run)
        session.add_all(
            [
                AgentProposalRecord(
                    id=uuid4(),
                    decision_run_id=run.id,
                    agent_type_code=p.agent_type_code.value,
                    proposal_status_code=p.proposal_status_code.value,
                    schema_version=p.schema_version,
                    proposal_payload=p.model_dump(mode="json"),
                    created_at=now,
                )
                for p in proposals
            ]
        )
        plan = PlanCandidate(
            id=uuid4(),
            decision_run_id=run.id,
            action_code=assembly.candidate.action_code.value,
            duration_adjustment_source_code=assembly.context.duration_adjustment_source_code,
            duration_rule_version=DURATION_RULE_VERSION,
            selected=result.selected_candidate_id == assembly.candidate.candidate_id,
            created_at=now,
            **assembly.candidate_data,
        )
        session.add(plan)
        # plan_items, safety_reviews and decision_options carry a raw
        # plan_candidate_id rather than a relationship, so the unit of work does
        # not know it must insert this row first. Flush it explicitly before the
        # rows that reference it. Everything still shares the caller's
        # transaction, so the decision record stays atomic.
        session.flush()
        session.add_all(
            [
                PlanItem(
                    id=uuid4(),
                    plan_candidate_id=plan.id,
                    **{name: getattr(item, name) for name in item.__dataclass_fields__},
                )
                for item in assembly.items
            ]
        )
        safety = next(p for p in proposals if p.agent_type_code.value == "SAFETY")
        guidance = (
            "STOP_AND_SEEK_HELP"
            if result.final_action_code and result.final_action_code.value == "STOP_AND_SEEK_HELP"
            else ("REST" if result.status_code is CoordinatorStatusCode.BLOCKED else None)
        )
        session.add(
            SafetyReview(
                id=uuid4(),
                decision_run_id=run.id,
                plan_candidate_id=plan.id,
                safety_status_code=result.safety_status_code.value,
                vetoed=bool(safety.safety_vetoed),
                ruleset_version=result.safety_rule_version,
                reason_codes=list(safety.reason_codes),
                excluded_exercise_ids=list(safety.excluded_exercise_ids),
                public_guidance=guidance,
            )
        )
        if result.status_code in {CoordinatorStatusCode.PASS, CoordinatorStatusCode.REVISE}:
            if result.final_action_code is None:
                raise RuntimeError("successful coordinator result is missing an action")
            session.add_all(
                [
                    DecisionOption(
                        id=uuid4(),
                        decision_run_id=run.id,
                        option_code="FINAL_ROUTINE",
                        action_code=result.final_action_code.value,
                        plan_candidate_id=plan.id,
                        display_order=1,
                        selectable=True,
                    ),
                    DecisionOption(
                        id=uuid4(),
                        decision_run_id=run.id,
                        option_code="REST",
                        action_code="REST",
                        plan_candidate_id=None,
                        display_order=2,
                        selectable=True,
                    ),
                ]
            )
        elif (
            result.status_code is CoordinatorStatusCode.BLOCKED
            and result.final_action_code
            and result.final_action_code.value == "REST"
        ):
            session.add(
                DecisionOption(
                    id=uuid4(),
                    decision_run_id=run.id,
                    option_code="REST",
                    action_code="REST",
                    plan_candidate_id=None,
                    display_order=1,
                    selectable=True,
                )
            )
        session.flush()
        return run.id

    def save_idempotency(
        self,
        session: Session,
        *,
        user_id: UUID,
        key: UUID,
        request_hash: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=DECISION_ENDPOINT_CODE,
                idempotency_key=key,
                request_hash=request_hash,
                response_payload=payload,
                response_schema_version=DECISION_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )

    def get_response(
        self, session: Session, user_id: UUID, decision_id: UUID
    ) -> dict[str, Any] | None:
        run = session.scalar(
            select(DecisionRun)
            .options(
                selectinload(DecisionRun.proposals),
                selectinload(DecisionRun.candidates).selectinload(PlanCandidate.items),
                selectinload(DecisionRun.safety_reviews),
                selectinload(DecisionRun.options),
            )
            .where(DecisionRun.id == decision_id, DecisionRun.user_id == user_id)
        )
        if run is None or run.status_code != "COMPLETED":
            return None
        plan = next((p for p in run.candidates if p.selected), None)
        safety = run.safety_reviews[0]
        return {
            "decision_id": run.id,
            "local_date": run.local_date,
            "status_code": "COMPLETED",
            "safety_status_code": run.safety_status_code,
            "action_code": run.recommended_action_code,
            "requested_duration_minutes": run.input_snapshot["requested_duration_minutes"],
            "duration_adjustment_source_code": run.input_snapshot[
                "duration_adjustment_source_code"
            ],
            "final_plan": None
            if plan is None
            else {
                "plan_id": plan.id,
                "action_code": plan.action_code,
                "training_type_code": plan.training_type_code,
                "body_focus_code": plan.body_focus_code,
                "requested_duration_minutes": plan.requested_duration_minutes,
                "estimated_duration_seconds": plan.estimated_duration_seconds,
                "estimated_calories_burned": plan.estimated_calories_burned,
                "setup_seconds": plan.setup_seconds,
                "warmup_seconds": plan.warmup_seconds,
                "cooldown_seconds": plan.cooldown_seconds,
                "items": [
                    {
                        "plan_item_id": i.id,
                        "exercise_id": i.exercise_id,
                        "exercise_name": i.display_name,
                        "sequence": i.sequence,
                        "tier_code": i.tier_code,
                        "sets": i.sets,
                        "reps": i.reps,
                        "work_seconds": i.work_seconds,
                        "rest_seconds": i.rest_seconds,
                        "transition_seconds": i.transition_seconds,
                        "estimated_item_seconds": (
                            i.work_seconds + i.rest_seconds + i.transition_seconds
                        ),
                        "instruction_available": bool(i.instruction_content_version),
                        "mascot_animation_asset_key": None,
                        "replacement_of_exercise_id": None,
                    }
                    for i in plan.items
                ],
            },
            "options": [
                {
                    "option_id": o.id,
                    "option_code": o.option_code,
                    "action_code": o.action_code,
                    "plan_id": o.plan_candidate_id,
                    "selectable": o.selectable,
                    "blocked_reason_code": o.blocked_reason_code,
                }
                for o in sorted(run.options, key=lambda value: value.display_order)
            ],
            "reason_codes": list(run.coordinator_result.get("reason_codes", []))[:2],
            "summary": "오늘의 운동 계획이 준비되었습니다."
            if plan
            else "오늘은 안전을 위해 운동 계획을 제공하지 않습니다.",
            "guidance": self._guidance(safety.public_guidance),
            "public_agent_summaries": [
                {
                    "agent_type_code": p.agent_type_code,
                    "recommendation_code": p.proposal_payload.get("recommended_action_code"),
                    "reason_codes": p.proposal_payload.get("reason_codes", [])[:2],
                    "summary": "규칙 기반 제안이 반영되었습니다.",
                }
                for p in sorted(
                    run.proposals,
                    key=lambda value: ("TRAINING", "RECOVERY", "SAFETY", "FEASIBILITY").index(
                        value.agent_type_code
                    ),
                )
            ]
            + [
                {
                    "agent_type_code": "COORDINATOR",
                    "recommendation_code": run.recommended_action_code,
                    "reason_codes": list(run.coordinator_result.get("reason_codes", []))[:2],
                    "summary": "규칙 기반 최종 결정이 완료되었습니다.",
                }
            ],
            "safety_summary": {
                "safety_status_code": safety.safety_status_code,
                "vetoed": safety.vetoed,
                "reason_codes": safety.reason_codes[:2],
                "summary": "저장된 안전 검토 결과입니다.",
            },
            "created_at": run.created_at,
        }

    @staticmethod
    def _guidance(code: str | None) -> dict[str, str] | None:
        if code == "STOP_AND_SEEK_HELP":
            return {
                "code": code,
                "title": "운동을 중단하세요",
                "message": "운동을 중단하고 필요한 도움을 요청하세요.",
                "tone_code": "SERIOUS",
            }
        if code == "REST":
            return {
                "code": code,
                "title": "오늘은 휴식하세요",
                "message": "오늘은 운동 대신 휴식을 선택하세요.",
                "tone_code": "SERIOUS",
            }
        return None


__all__ = ["DecisionRepository"]
