from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseEquipment,
    ExerciseLocation,
    ExerciseSafetyRule,
)
from backend.app.db.models.checkin import (
    DailyContext,
    DailyContextAdverseReaction,
    DailyContextDiscomfort,
)
from backend.app.db.models.decision import (
    AgentProposalRecord,
    DecisionExplanationRecord,
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
from backend.app.db.models.workout import WorkoutSession
from backend.app.domain.agents.contracts import RecommendedActionCode
from backend.app.domain.agents.coordinator import (
    CoordinatorCandidate,
    CoordinatorResult,
    CoordinatorStatusCode,
)
from backend.app.domain.rules.duration import DURATION_RULE_VERSION, DurationPlan, PlanItemDuration
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
from backend.app.modules.decisions.codes import (
    DECISION_ENDPOINT_CODE,
    DECISION_GRAPH_VERSION,
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
    DECISION_RESPONSE_SCHEMA_VERSION,
)
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.explanations import DecisionExplanation
from backend.app.modules.decisions.ports import (
    AlternativeItemData,
    CandidateItemData,
    DecisionAssembly,
    StoredIdempotency,
)


def replace_candidate_item_exercise(
    source: CandidateItemData,
    alternative: Exercise,
) -> CandidateItemData:
    """Keep the approved duration prescription while changing catalog content."""

    return replace(
        source,
        exercise_id=alternative.id,
        instruction_content_version=alternative.instruction_content_version,
        display_name=alternative.name_ko,
    )


class DecisionRepository:
    def acquire_lock(self, session: Session, user_id: UUID, key: UUID) -> None:
        lock_key = int.from_bytes(
            sha256(f"{user_id}:{key}".encode()).digest()[:8], "big", signed=True
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def acquire_input_lock(
        self,
        session: Session,
        user_id: UUID,
        daily_context_id: UUID,
        daily_context_version: int,
        input_hash: str,
    ) -> None:
        """Serialize creation for one immutable daily-context input snapshot."""

        lock_key = int.from_bytes(
            sha256(
                f"{user_id}:{daily_context_id}:{daily_context_version}:{input_hash}".encode()
            ).digest()[:8],
            "big",
            signed=True,
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
        recent_workout_status_codes = tuple(
            session.scalars(
                select(WorkoutSession.status_code)
                .where(
                    WorkoutSession.user_id == user_id,
                    WorkoutSession.status_code.in_(
                        ("COMPLETED", "PARTIAL", "NOT_COMPLETED", "STOPPED_FOR_SAFETY")
                    ),
                    WorkoutSession.ended_at.is_not(None),
                    WorkoutSession.ended_at <= daily.updated_at,
                )
                .order_by(WorkoutSession.ended_at.desc(), WorkoutSession.id.desc())
                .limit(7)
            ).all()
        )
        required_equipment_codes = tuple(
            sorted(
                set(
                    session.scalars(
                        select(ExerciseEquipment.equipment_code).where(
                            ExerciseEquipment.exercise_id.in_(exercise_ids)
                        )
                    ).all()
                )
            )
        )
        exercise_locations: dict[UUID, set[str]] = {
            exercise_id: set() for exercise_id in set(exercise_ids)
        }
        for exercise_id, location_code in session.execute(
            select(ExerciseLocation.exercise_id, ExerciseLocation.location_code).where(
                ExerciseLocation.exercise_id.in_(exercise_ids)
            )
        ):
            exercise_locations[exercise_id].add(location_code)
        supported_location_codes = tuple(sorted(set.intersection(*exercise_locations.values())))
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
            profile.preferred_location_code,
            recent_workout_status_codes,
            required_equipment_codes,
            supported_location_codes,
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
        safety_candidate = SafetyCandidate(
            items=tuple(
                SafetyCandidateItem(
                    str(exercise_id),
                    catalog.version_code,
                    exercises[exercise_id].primary_movement_pattern_code,
                )
                for exercise_id in sorted(set(exercise_ids), key=str)
            )
        )
        safety_rule_rows = session.scalars(
            select(ExerciseSafetyRule).where(
                ExerciseSafetyRule.catalog_version_id == catalog.id,
            )
        ).all()
        rule_set_versions = {row.rule_set_version_code for row in safety_rule_rows}
        safety_rule_set = None
        if safety_rule_rows and len(rule_set_versions) == 1:
            safety_rule_set = SafetyRuleSet(
                version_code=next(iter(rule_set_versions)),
                review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
                production_eligible=all(row.production_eligible for row in safety_rule_rows),
                rules=tuple(
                    SafetyRule(
                        rule_code=str(row.id),
                        catalog_version_code=catalog.version_code,
                        body_area_code=BodyAreaCode(row.body_area_code),
                        minimum_severity_code=DiscomfortSeverityCode[row.minimum_severity_code],
                        maximum_severity_code=DiscomfortSeverityCode[row.maximum_severity_code],
                        effect_code=SafetyRuleEffectCode(row.effect_code),
                        reason_code=row.reason_code,
                        scope_code=(
                            SafetyRuleScopeCode.EXERCISE
                            if row.exercise_id is not None
                            else SafetyRuleScopeCode.MOVEMENT_PATTERN
                        ),
                        rule_version=row.rule_version,
                        exercise_code=(str(row.exercise_id) if row.exercise_id else None),
                        movement_pattern_code=row.movement_pattern_code,
                        review_status_code=SafetyReviewStatusCode(row.review_status_code),
                    )
                    for row in sorted(safety_rule_rows, key=lambda value: str(value.id))
                ),
            )

        alternative_rows = session.execute(
            select(ExerciseAlternative, Exercise)
            .join(Exercise, Exercise.id == ExerciseAlternative.alternative_exercise_id)
            .where(
                ExerciseAlternative.source_exercise_id.in_(exercise_ids),
                ExerciseAlternative.review_status_code == "DOMAIN_APPROVED",
                ExerciseAlternative.production_eligible.is_(True),
                Exercise.catalog_version_id == catalog.id,
                Exercise.review_status_code == "DOMAIN_APPROVED",
            )
            .order_by(
                ExerciseAlternative.source_exercise_id,
                ExerciseAlternative.difficulty_delta,
                ExerciseAlternative.alternative_exercise_id,
            )
        ).all()
        alternative_exercise_ids = {exercise.id for _, exercise in alternative_rows}
        required_equipment: dict[UUID, set[str]] = {
            exercise_id: set() for exercise_id in alternative_exercise_ids
        }
        available_locations: dict[UUID, set[str]] = {
            exercise_id: set() for exercise_id in alternative_exercise_ids
        }
        if alternative_exercise_ids:
            for exercise_id, equipment_code in session.execute(
                select(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code).where(
                    ExerciseEquipment.exercise_id.in_(alternative_exercise_ids)
                )
            ):
                required_equipment[exercise_id].add(equipment_code)
            for exercise_id, location_code in session.execute(
                select(ExerciseLocation.exercise_id, ExerciseLocation.location_code).where(
                    ExerciseLocation.exercise_id.in_(alternative_exercise_ids)
                )
            ):
                available_locations[exercise_id].add(location_code)
        source_items = {item.exercise_id: item for item in item_data}
        alternative_items: list[AlternativeItemData] = []
        for relation, alternative in alternative_rows:
            if not required_equipment[alternative.id].issubset(set(equipment)):
                continue
            if daily.location_code not in available_locations[alternative.id]:
                continue
            source_item = source_items[relation.source_exercise_id]
            alternative_items.append(
                AlternativeItemData(
                    source_exercise_id=relation.source_exercise_id,
                    item=replace_candidate_item_exercise(source_item, alternative),
                    safety_item=SafetyCandidateItem(
                        str(alternative.id),
                        catalog.version_code,
                        alternative.primary_movement_pattern_code,
                    ),
                    evidence_reference_code=f"ALTERNATIVE/{relation.id}",
                    pain_discomfort_area_code=relation.pain_discomfort_area_code,
                    condition_code=relation.condition_code,
                    service_action_code=relation.service_action_code,
                    target_strategy_code=relation.target_strategy_code,
                )
            )
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
            safety_candidate,
            safety_rule_set,
            tuple(alternative_items),
            coaching_style_code=profile.coaching_style_code,
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
        explanation: DecisionExplanation,
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
            graph_version=DECISION_GRAPH_VERSION,
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
        candidate_records = [
            (
                assembly.candidate,
                assembly.candidate_data,
                assembly.items,
            ),
            *(
                (adjusted.candidate, adjusted.candidate_data, adjusted.items)
                for adjusted in assembly.adjusted_candidates
            ),
        ]
        plans_by_candidate_id: dict[str, PlanCandidate] = {}
        for candidate, candidate_data, items in candidate_records:
            plan = PlanCandidate(
                id=uuid4(),
                decision_run_id=run.id,
                action_code=candidate.action_code.value,
                duration_adjustment_source_code=assembly.context.duration_adjustment_source_code,
                duration_rule_version=DURATION_RULE_VERSION,
                selected=result.selected_candidate_id == candidate.candidate_id,
                created_at=now,
                **candidate_data,
            )
            session.add(plan)
            # Referencing rows use raw foreign keys, so establish each candidate
            # before inserting its item records inside the same transaction.
            session.flush()
            session.add_all(
                [
                    PlanItem(
                        id=uuid4(),
                        plan_candidate_id=plan.id,
                        **{name: getattr(item, name) for name in item.__dataclass_fields__},
                    )
                    for item in items
                ]
            )
            plans_by_candidate_id[candidate.candidate_id] = plan
        base_plan = plans_by_candidate_id[assembly.candidate.candidate_id]
        selected_plan = (
            plans_by_candidate_id.get(result.selected_candidate_id)
            if result.selected_candidate_id is not None
            else None
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
                plan_candidate_id=(selected_plan.id if selected_plan is not None else base_plan.id),
                safety_status_code=result.safety_status_code.value,
                vetoed=bool(safety.safety_vetoed),
                ruleset_version=result.safety_rule_version,
                reason_codes=list(safety.reason_codes),
                excluded_exercise_ids=list(safety.excluded_exercise_ids),
                public_guidance=guidance,
            )
        )
        session.add(
            DecisionExplanationRecord(
                id=uuid4(),
                decision_run_id=run.id,
                source_code=explanation.source_code.value,
                summary=explanation.summary,
                reason_codes=list(explanation.reason_codes),
                agent_summaries=explanation.agent_summaries_payload(),
                safety_summary=explanation.safety_summary_payload(),
                final_adjustment_reason=explanation.final_adjustment_reason,
                coaching_style_code=explanation.coaching_style_code,
                template_version=explanation.template_version,
                prompt_version=explanation.prompt_version,
                model_code=explanation.model_code,
                fallback_reason_code=explanation.fallback_reason_code,
                created_at=now,
            )
        )
        if result.status_code in {CoordinatorStatusCode.PASS, CoordinatorStatusCode.REVISE}:
            if result.final_action_code is None:
                raise RuntimeError("successful coordinator result is missing an action")
            if selected_plan is None:
                raise RuntimeError("successful coordinator result is missing a selected plan")
            session.add_all(
                [
                    DecisionOption(
                        id=uuid4(),
                        decision_run_id=run.id,
                        option_code="FINAL_ROUTINE",
                        action_code=result.final_action_code.value,
                        plan_candidate_id=selected_plan.id if selected_plan else None,
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

    def get_response_for_date(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        """Return the day's most recent completed decision, or None.

        A day can hold several runs when the user redoes the check-in, so the
        newest completed run is the one the client resumes.
        """

        decision_id = session.scalar(
            select(DecisionRun.id)
            .where(
                DecisionRun.user_id == user_id,
                DecisionRun.local_date == local_date,
                DecisionRun.status_code == "COMPLETED",
            )
            .order_by(DecisionRun.created_at.desc(), DecisionRun.id.desc())
            .limit(1)
        )
        if decision_id is None:
            return None
        return self.get_response(session, user_id, decision_id)

    def get_completed_response_for_input(
        self,
        session: Session,
        user_id: UUID,
        daily_context_id: UUID,
        daily_context_version: int,
        input_hash: str,
    ) -> dict[str, Any] | None:
        """Replay the completed decision for an identical immutable input."""

        decision_id = session.scalar(
            select(DecisionRun.id)
            .where(
                DecisionRun.user_id == user_id,
                DecisionRun.daily_context_id == daily_context_id,
                DecisionRun.daily_context_version == daily_context_version,
                DecisionRun.input_hash == input_hash,
                DecisionRun.status_code == "COMPLETED",
            )
            .order_by(DecisionRun.created_at.desc(), DecisionRun.id.desc())
            .limit(1)
        )
        if decision_id is None:
            return None
        return self.get_response(session, user_id, decision_id)

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
                selectinload(DecisionRun.explanations),
            )
            .where(DecisionRun.id == decision_id, DecisionRun.user_id == user_id)
        )
        if run is None or run.status_code != "COMPLETED":
            return None
        plan = next((p for p in run.candidates if p.selected), None)
        safety = run.safety_reviews[0]
        # Narration is stored once at decision time. Runs created before the narration
        # record exists keep the reviewed default sentences.
        explanation = run.explanations[0] if run.explanations else None
        adjustment_reason_codes: list[str] | None = None
        if plan is not None and plan.action_code != "KEEP":
            proposal_priority = (
                ("SAFETY",)
                if run.safety_status_code == "REVISE"
                else ("FEASIBILITY", "RECOVERY", "TRAINING", "SAFETY")
            )
            matching_proposal = next(
                (
                    proposal
                    for agent_type in proposal_priority
                    for proposal in run.proposals
                    if proposal.agent_type_code == agent_type
                    and proposal.proposal_payload.get("recommended_action_code") == plan.action_code
                ),
                None,
            )
            if matching_proposal is not None:
                adjustment_reason_codes = list(
                    matching_proposal.proposal_payload.get("reason_codes", [])
                )[:2]
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
            "adjustment_reason_codes": adjustment_reason_codes,
            "summary": (
                explanation.summary
                if explanation is not None
                else (
                    "오늘의 운동 계획이 준비되었습니다."
                    if plan
                    else "오늘은 안전을 위해 운동 계획을 제공하지 않습니다."
                )
            ),
            "guidance": self._guidance(safety.public_guidance),
            "public_agent_summaries": (
                explanation.agent_summaries
                if explanation is not None
                else self._default_agent_summaries(run)
            ),
            "safety_summary": (
                explanation.safety_summary
                if explanation is not None
                else {
                    "safety_status_code": safety.safety_status_code,
                    "vetoed": safety.vetoed,
                    "reason_codes": safety.reason_codes[:2],
                    "summary": "저장된 안전 검토 결과입니다.",
                }
            ),
            "generation_mode_code": run.generation_mode_code,
            "decision_engine_code": run.decision_engine_code,
            "root_decision_id": run.root_decision_run_id,
            "parent_decision_id": run.parent_decision_run_id,
            "regeneration_sequence": run.regeneration_sequence,
            "created_at": run.created_at,
        }

    @staticmethod
    def _default_agent_summaries(run: DecisionRun) -> list[dict[str, Any]]:
        return [
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
        ] + [
            {
                "agent_type_code": "COORDINATOR",
                "recommendation_code": run.recommended_action_code,
                "reason_codes": list(run.coordinator_result.get("reason_codes", []))[:2],
                "summary": "규칙 기반 최종 결정이 완료되었습니다.",
            }
        ]

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
