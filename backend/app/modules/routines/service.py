import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Final
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from backend.app.domain.rules.duration import (
    DURATION_TOLERANCE_SECONDS,
    DurationPlan,
    DurationRequest,
    DurationTargetMismatchError,
    PlanItemDuration,
    require_exact_duration,
    validate_requested_duration,
)
from backend.app.domain.rules.plan_shape import (
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
)
from backend.app.modules.routines.codes import RoutinePhaseCode, RoutineTierCode
from backend.app.modules.routines.ports import (
    RoutineCandidate,
    RoutineCreationContext,
    RoutineDayValues,
    RoutineItemValues,
    RoutineRepositoryPort,
)
from backend.app.modules.routines.schemas import RoutineCreateRequest, RoutineResponse


class RoutineError(Exception):
    """Base class for safe routine creation failures."""


class IdempotencyKeyReusedError(RoutineError):
    """The same key was used with a different request."""


class ApprovedCatalogUnavailableError(RoutineError):
    """No production-approved active catalog can support the use case."""


class RoutineContentUnavailableError(RoutineError):
    """Approved content cannot form all required routine phases."""


class RoutineDurationUnavailableError(RoutineError):
    """Approved prescriptions cannot exactly preserve the requested duration."""


class RoutineNotFoundError(RoutineError):
    """No active routine exists in the authenticated user's scope."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(request: RoutineCreateRequest) -> str:
    raw = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _candidate_duration(candidate: RoutineCandidate) -> PlanItemDuration:
    if candidate.reps is not None:
        if candidate.seconds_per_rep is None:
            raise RoutineContentUnavailableError
        work_per_set = candidate.reps * candidate.seconds_per_rep
    else:
        if candidate.work_seconds_per_set is None:
            raise RoutineContentUnavailableError
        work_per_set = candidate.work_seconds_per_set
    return PlanItemDuration(
        work_seconds=candidate.sets * work_per_set,
        rest_seconds=max(candidate.sets - 1, 0) * candidate.rest_seconds_per_set,
        transition_seconds=candidate.transition_seconds,
    )


# A session is a workout, not an inventory. Filling the requested time by
# stacking ever more exercises produced 22-item plans that were mostly warmup
# and cooldown work, so the number of distinct exercises is bounded and the set
# count absorbs the rest. The bounds live in domain.rules.plan_shape because the
# V3 planner has to answer to the same shape; it did not, and shipped flat
# twelve-exercise plans with one warmup block.
MAX_PHASE_TYPES: Final[dict[str, int]] = {
    str(phase_code): cap for phase_code, cap in MAX_PHASE_EXERCISE_TYPES.items()
}
MAX_PLAN_TYPES: Final = MAX_PLAN_EXERCISE_TYPES
# One exercise may be split across blocks rather than run as a single long set
# run: four sets of push-ups, three of squats, then four more of push-ups is a
# session; eight straight sets of push-ups is not. Blocks of the same exercise
# are one type, so splitting does not consume the type budget.
MAX_SETS_PER_BLOCK: Final = 4
MAX_BLOCKS_PER_EXERCISE: Final = 2
_ONBOARDING_ROUTINE_IDEMPOTENCY_NAMESPACE: Final = UUID("8cfaa373-cf21-4e91-a583-893992d7da7b")


def _subset_rank(items: tuple[RoutineCandidate, ...]) -> tuple[int, int, int]:
    """Rank a candidate subset for the same total time.

    Goal fit first: CORE is what the goal's catalog review marked as driving it.
    Then variety, because splitting one exercise across blocks is a way to shape
    a session, not a licence to hand the user the same movement over and over.
    Compactness only breaks the remaining ties.
    """

    core = sum(item.tier_code == RoutineTierCode.CORE for item in items)
    repeated_blocks = len(items) - _distinct_types(items)
    return (-core, repeated_blocks, len(items))


def _distinct_types(items: tuple[RoutineCandidate, ...]) -> int:
    return len({item.exercise_id for item in items})


def _block_variants(candidate: RoutineCandidate) -> tuple[tuple[RoutineCandidate, ...], ...]:
    """Return every block layout the planner may use for one exercise.

    Warmup and cooldown keep their reviewed dosage as a single block: they
    prepare and settle the body rather than absorb leftover minutes.
    """

    if candidate.phase_code != RoutinePhaseCode.MAIN:
        return ((candidate,),)
    layouts: list[tuple[RoutineCandidate, ...]] = [
        (replace(candidate, sets=sets),) for sets in range(1, MAX_SETS_PER_BLOCK + 1)
    ]
    if MAX_BLOCKS_PER_EXERCISE > 1:
        layouts.extend(
            (replace(candidate, sets=first), replace(candidate, sets=second))
            for first in range(1, MAX_SETS_PER_BLOCK + 1)
            for second in range(1, MAX_SETS_PER_BLOCK + 1)
        )
    return tuple(layouts)


def _subsets(
    candidates: tuple[RoutineCandidate, ...],
    target_seconds: int,
    *,
    max_types: int,
) -> dict[tuple[int, bool], tuple[RoutineCandidate, ...]]:
    states: dict[tuple[int, bool], tuple[RoutineCandidate, ...]] = {(0, False): ()}
    for candidate in sorted(
        candidates, key=lambda item: (item.exercise_name, str(item.exercise_id))
    ):
        additions: dict[tuple[int, bool], tuple[RoutineCandidate, ...]] = {}
        for blocks in _block_variants(candidate):
            seconds = sum(_candidate_duration(block).estimated_item_seconds for block in blocks)
            for (current, has_core), selected in states.items():
                total = current + seconds
                if total > target_seconds:
                    continue
                proposed = (*selected, *blocks)
                if _distinct_types(proposed) > max_types:
                    continue
                key = (total, has_core or candidate.tier_code == RoutineTierCode.CORE)
                existing = states.get(key) or additions.get(key)
                # Collapsing on length alone discarded the CORE-richer subset for
                # a given total, so preferring CORE later had nothing left to
                # choose from and a muscle-gain plan stayed mostly support work.
                if existing is None or _subset_rank(proposed) < _subset_rank(existing):
                    additions[key] = proposed
        states.update(additions)
    return states


def _select_exact_plan(
    context: RoutineCreationContext,
    requested_duration_minutes: int | None = None,
) -> tuple[int, tuple[RoutineCandidate, ...], DurationRequest]:
    # The profile value is a default, not a ceiling: when the user picks a
    # duration for this routine it becomes the target and the request is a
    # USER_OVERRIDE. The stored profile default is left untouched, and the
    # server never fabricates USER_OVERRIDE on the user's behalf.
    effective_minutes = requested_duration_minutes or context.profile_duration_minutes
    duration_request = validate_requested_duration(
        profile_duration_minutes=context.profile_duration_minutes,
        requested_duration_minutes=effective_minutes,
        adjustment_source_code=(
            "PROFILE" if effective_minutes == context.profile_duration_minutes else "USER_OVERRIDE"
        ),
    )
    target = duration_request.target_duration_seconds
    by_phase = {
        phase: tuple(item for item in context.candidates if item.phase_code == phase)
        for phase in RoutinePhaseCode
    }
    if any(not by_phase[phase] for phase in RoutinePhaseCode):
        raise RoutineContentUnavailableError

    warmup_cap = MAX_PHASE_TYPES[RoutinePhaseCode.WARMUP]
    cooldown_cap = MAX_PHASE_TYPES[RoutinePhaseCode.COOLDOWN]
    warmups = _subsets(by_phase[RoutinePhaseCode.WARMUP], min(target, 180), max_types=warmup_cap)
    mains = _subsets(
        by_phase[RoutinePhaseCode.MAIN],
        target + DURATION_TOLERANCE_SECONDS,
        max_types=MAX_PLAN_TYPES - warmup_cap - cooldown_cap,
    )
    cooldowns = _subsets(
        by_phase[RoutinePhaseCode.COOLDOWN], min(target, 120), max_types=cooldown_cap
    )
    matches: list[tuple[int, int, tuple[RoutineCandidate, ...]]] = []
    for (warmup_seconds, _), warmup_items in warmups.items():
        if not 60 <= warmup_seconds <= 180:
            continue
        for (main_seconds, has_core), main_items in mains.items():
            if not has_core or main_seconds <= 0:
                continue
            for (cooldown_seconds, _), cooldown_items in cooldowns.items():
                if not 45 <= cooldown_seconds <= 120:
                    continue
                content_seconds = warmup_seconds + main_seconds + cooldown_seconds
                # Setup still occupies at most a minute; it absorbs a shortfall
                # but never stretches to cover the whole tolerance.
                setup_seconds = min(max(target - content_seconds, 0), 60)
                deviation = abs(content_seconds + setup_seconds - target)
                if deviation <= DURATION_TOLERANCE_SECONDS:
                    selected = (*warmup_items, *main_items, *cooldown_items)
                    matches.append((deviation, setup_seconds, selected))
    if not matches:
        raise RoutineDurationUnavailableError
    matches.sort(
        key=lambda match: (
            # Closest to the requested duration wins; the tolerance is a
            # fallback, not a licence to drift.
            match[0],
            sum(item.tier_code == RoutineTierCode.OPTIONAL for item in match[2]),
            # Goal fit: CORE work is what the goal's catalog review marked as
            # driving it, so prefer the plan that carries more of it. Requiring
            # only one CORE let a muscle-gain session fill up with support work.
            -sum(
                item.tier_code == RoutineTierCode.CORE and item.phase_code == RoutinePhaseCode.MAIN
                for item in match[2]
            ),
            len(match[2]),
            tuple(
                (item.phase_code, item.exercise_name, str(item.exercise_id)) for item in match[2]
            ),
        )
    )
    return matches[0][1], matches[0][2], duration_request


def _build_days(
    context: RoutineCreationContext,
    requested_duration_minutes: int | None = None,
    recent_performed_body_focus_codes: tuple[str, ...] = (),
) -> tuple[RoutineDayValues, ...]:
    previous_body_focus_code = next(iter(recent_performed_body_focus_codes), None)
    days: list[RoutineDayValues] = []
    for sequence in range(1, context.weekly_target_sessions + 1):
        rotated_context = context
        if previous_body_focus_code is not None:
            rotated_candidates = tuple(
                item
                for item in context.candidates
                if item.phase_code != RoutinePhaseCode.MAIN
                or item.body_focus_code != previous_body_focus_code
            )
            # Rotation is preference-based, never a fixed focus order.  Use the
            # previous focus only when an alternative MAIN focus actually exists.
            if any(item.phase_code == RoutinePhaseCode.MAIN for item in rotated_candidates):
                rotated_context = replace(context, candidates=rotated_candidates)
        try:
            day = _build_day(
                rotated_context,
                sequence=sequence,
                requested_duration_minutes=requested_duration_minutes,
            )
        except (RoutineContentUnavailableError, RoutineDurationUnavailableError):
            # A catalog may not satisfy the duration target with a different focus.
            # Keep the validated plan instead of shortening it or hard-coding an order.
            if rotated_context is context:
                raise
            day = _build_day(
                context,
                sequence=sequence,
                requested_duration_minutes=requested_duration_minutes,
            )
        days.append(day)
        previous_body_focus_code = day.body_focus_code
    return tuple(days)


def _build_day(
    context: RoutineCreationContext,
    *,
    sequence: int,
    requested_duration_minutes: int | None,
) -> RoutineDayValues:
    setup_seconds, selected, duration_request = _select_exact_plan(
        context, requested_duration_minutes
    )
    warmup_seconds = sum(
        _candidate_duration(item).estimated_item_seconds
        for item in selected
        if item.phase_code == RoutinePhaseCode.WARMUP
    )
    cooldown_seconds = sum(
        _candidate_duration(item).estimated_item_seconds
        for item in selected
        if item.phase_code == RoutinePhaseCode.COOLDOWN
    )
    main_durations = tuple(
        _candidate_duration(item) for item in selected if item.phase_code == RoutinePhaseCode.MAIN
    )
    try:
        assessment = require_exact_duration(
            duration_request,
            DurationPlan(
                setup_seconds=setup_seconds,
                warmup_seconds=warmup_seconds,
                items=main_durations,
                cooldown_seconds=cooldown_seconds,
            ),
            tolerance_seconds=DURATION_TOLERANCE_SECONDS,
        )
    except DurationTargetMismatchError:
        raise RoutineDurationUnavailableError from None
    items = tuple(
        RoutineItemValues(
            exercise_id=item.exercise_id,
            sequence=sequence,
            phase_code=item.phase_code,
            tier_code=(
                item.tier_code
                if item.phase_code == RoutinePhaseCode.MAIN
                else RoutineTierCode.SUPPORT
            ),
            sets=item.sets,
            reps=item.reps,
            work_seconds_per_set=item.work_seconds_per_set,
            rest_seconds_per_set=item.rest_seconds_per_set,
            intensity_code=item.intensity_code,
        )
        for sequence, item in enumerate(selected, start=1)
    )
    main = next(item for item in selected if item.phase_code == RoutinePhaseCode.MAIN)
    return RoutineDayValues(
        sequence=sequence,
        title=f"루틴 {sequence}",
        training_type_code=main.training_type_code,
        body_focus_code=main.body_focus_code,
        requested_duration_minutes=duration_request.requested_duration_minutes,
        estimated_duration_seconds=assessment.estimated_duration_seconds,
        setup_seconds=setup_seconds,
        items=items,
    )


class RoutineService:
    def __init__(
        self,
        repository: RoutineRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def create(
        self,
        session: Session,
        user_id: UUID,
        request: RoutineCreateRequest,
        idempotency_key: UUID,
    ) -> RoutineResponse:
        with session.begin():
            self._repository.acquire_creation_lock(session, user_id)
            return self._create_locked(session, user_id, request, idempotency_key)

    def ensure_initial_routine(
        self,
        session: Session,
        user_id: UUID,
        request: RoutineCreateRequest,
    ) -> RoutineResponse | None:
        """Provision the initial base routine inside an existing transaction."""

        self._repository.acquire_creation_lock(session, user_id)
        if self._repository.has_any_routine(session, user_id):
            return None
        idempotency_key = uuid5(_ONBOARDING_ROUTINE_IDEMPOTENCY_NAMESPACE, str(user_id))
        return self._create_locked(session, user_id, request, idempotency_key)

    def _create_locked(
        self,
        session: Session,
        user_id: UUID,
        request: RoutineCreateRequest,
        idempotency_key: UUID,
    ) -> RoutineResponse:
        request_hash = _request_hash(request)
        now = self._clock()
        existing = self._repository.get_idempotency_record(session, user_id, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyKeyReusedError
            return RoutineResponse.model_validate(existing.response_payload)
        context = self._repository.get_creation_context(session, user_id, request.goal_code)
        if context is None:
            raise ApprovedCatalogUnavailableError
        recent_performed_body_focus_codes = self._repository.get_recent_performed_body_focus_codes(
            session,
            user_id,
            request.effective_from,
        )
        days = _build_days(
            context,
            request.requested_duration_minutes,
            recent_performed_body_focus_codes,
        )
        routine_id = self._repository.create_routine(
            session,
            user_id,
            request.goal_code,
            request.effective_from,
            context.catalog_version_id,
            days,
            now,
        )
        payload = self._repository.get_routine_response_payload(session, user_id, routine_id)
        if payload is None:
            raise RuntimeError("created routine could not be reloaded")
        response = RoutineResponse.model_validate(payload)
        self._repository.save_idempotency_record(
            session,
            user_id,
            idempotency_key,
            request_hash,
            response.model_dump(mode="json"),
            now,
        )
        return response

    def get_current(self, session: Session, user_id: UUID, local_date: date) -> RoutineResponse:
        payload = self._repository.get_current_routine_payload(session, user_id, local_date)
        if payload is None:
            raise RoutineNotFoundError
        return RoutineResponse.model_validate(payload)


__all__ = [
    "ApprovedCatalogUnavailableError",
    "IdempotencyKeyReusedError",
    "RoutineContentUnavailableError",
    "RoutineDurationUnavailableError",
    "RoutineNotFoundError",
    "RoutineService",
]
