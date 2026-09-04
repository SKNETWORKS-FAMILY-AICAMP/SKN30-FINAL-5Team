from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.modules.decisions.plan_revision import (
    PlanRevisionError,
    PlanRevisionFailureCode,
    PlanRevisionItem,
    apply_order_edit,
    apply_set_repetition_edit,
)
from backend.app.modules.decisions.plan_revision_service import (
    PlanRevisionIdempotencyKeyReusedError,
    PlanRevisionService,
    PlanRevisionStaleError,
)
from backend.app.modules.decisions.ports import (
    PlanRevisionSource,
    PlanRevisionWrite,
    StoredIdempotency,
)
from backend.app.modules.decisions.schemas import PlanItemSetRepetitionRequest

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def _item(
    number: int,
    *,
    sequence: int | None = None,
    phase_code: str = "MAIN",
    reps: int | None = 10,
) -> PlanRevisionItem:
    return PlanRevisionItem(
        plan_item_id=UUID(int=number),
        sequence=sequence or number,
        phase_code=phase_code,
        sets=2,
        reps=reps,
        work_seconds_per_set=20 if reps is not None else 30,
        rest_seconds_per_set=10,
        transition_seconds=5,
        seconds_per_rep=2 if reps is not None else None,
        default_work_seconds=None if reps is not None else 30,
    )


def test_set_and_repetition_edit_recomputes_only_the_target() -> None:
    items = (_item(1), _item(2))

    revised = apply_set_repetition_edit(items, plan_item_id=UUID(int=1), sets=3, reps=12)

    assert revised[0].sets == 3
    assert revised[0].reps == 12
    assert revised[0].work_seconds_per_set == 24
    assert revised[1] == items[1]


def test_edit_transport_rejects_empty_nonpositive_and_location_values() -> None:
    base = {
        "expected_plan_id": str(uuid4()),
        "expected_plan_revision": 0,
        "sets": 2,
        "reps": 10,
    }
    for invalid in ({**base, "sets": 0}, {**base, "reps": -1}, {**base, "sets": None}):
        with pytest.raises(ValidationError):
            PlanItemSetRepetitionRequest.model_validate(invalid)
    with pytest.raises(ValidationError):
        PlanItemSetRepetitionRequest.model_validate({**base, "location_code": "GYM"})


def test_order_edit_requires_all_unfinished_items_and_preserves_completed_positions() -> None:
    items = (_item(1), _item(2), _item(3))

    revised = apply_order_edit(
        items,
        ordered_plan_item_ids=[UUID(int=3), UUID(int=2)],
        completed_plan_item_ids=frozenset({UUID(int=1)}),
    )

    assert [item.plan_item_id for item in revised] == [UUID(int=1), UUID(int=3), UUID(int=2)]
    assert [item.sequence for item in revised] == [1, 2, 3]

    with pytest.raises(PlanRevisionError) as failure:
        apply_order_edit(
            items,
            ordered_plan_item_ids=[UUID(int=1), UUID(int=3), UUID(int=2)],
            completed_plan_item_ids=frozenset({UUID(int=1)}),
        )
    assert failure.value.code is PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE


def test_order_edit_cannot_cross_a_phase_boundary() -> None:
    items = (_item(1, phase_code="WARMUP"), _item(2), _item(3))

    with pytest.raises(PlanRevisionError) as failure:
        apply_order_edit(
            items,
            ordered_plan_item_ids=[UUID(int=2), UUID(int=1), UUID(int=3)],
            completed_plan_item_ids=frozenset(),
        )
    assert failure.value.code is PlanRevisionFailureCode.ORDER_CROSSES_PHASE


class _Session:
    def begin(self):
        return nullcontext()


class _Repository:
    def __init__(self, *, completed: frozenset[UUID] = frozenset()) -> None:
        self.decision_id = uuid4()
        self.plan_id = uuid4()
        self.revision = 0
        self.items = (_item(1), _item(2))
        self.completed = completed
        self.idempotency: dict[tuple[str, UUID], StoredIdempotency] = {}
        self.save_count = 0

    def acquire_endpoint_lock(self, *args: Any) -> None:
        pass

    def get_endpoint_idempotency(
        self, session: Any, user_id: UUID, endpoint_code: str, key: UUID
    ) -> StoredIdempotency | None:
        return self.idempotency.get((endpoint_code, key))

    def save_endpoint_idempotency(self, session: Any, **values: Any) -> None:
        self.idempotency[(values["endpoint_code"], values["key"])] = StoredIdempotency(
            values["request_hash"], values["payload"]
        )

    def lock_plan_for_revision(
        self, session: Any, user_id: UUID, decision_id: UUID
    ) -> PlanRevisionSource | None:
        if decision_id != self.decision_id:
            return None
        return PlanRevisionSource(
            decision_id=self.decision_id,
            plan_id=self.plan_id,
            user_revision_sequence=self.revision,
            requested_duration_minutes=30,
            setup_seconds=0,
            warmup_seconds=0,
            cooldown_seconds=0,
            items=self.items,
            completed_plan_item_ids=self.completed,
            editable=True,
        )

    def save_plan_revision(
        self,
        session: Any,
        *,
        plan_id: UUID,
        writes: tuple[PlanRevisionWrite, ...],
        estimated_duration_seconds: int,
        policy_version: str,
        now: datetime,
    ) -> int:
        del session, plan_id, estimated_duration_seconds, policy_version, now
        self.items = tuple(
            PlanRevisionItem(
                plan_item_id=item.plan_item_id,
                sequence=item.sequence,
                phase_code=source.phase_code,
                sets=item.sets,
                reps=item.reps,
                work_seconds_per_set=item.work_seconds_per_set,
                rest_seconds_per_set=source.rest_seconds_per_set,
                transition_seconds=source.transition_seconds,
                seconds_per_rep=source.seconds_per_rep,
                default_work_seconds=source.default_work_seconds,
            )
            for item in writes
            for source in self.items
            if source.plan_item_id == item.plan_item_id
        )
        self.revision += 1
        self.save_count += 1
        return self.revision

    def get_response(self, session: Any, user_id: UUID, decision_id: UUID) -> dict[str, Any]:
        return {
            "final_plan": {
                "plan_id": self.plan_id,
                "plan_revision": self.revision,
                "action_code": "KEEP",
                "training_type_code": "STRENGTH",
                "body_focus_code": None,
                "requested_duration_minutes": 30,
                "estimated_duration_seconds": 100,
                "estimated_calories_burned": None,
                "setup_seconds": 0,
                "warmup_seconds": 0,
                "cooldown_seconds": 0,
                "items": [
                    {
                        "plan_item_id": item.plan_item_id,
                        "exercise_id": uuid4(),
                        "exercise_name": "exercise",
                        "sequence": item.sequence,
                        "phase_code": item.phase_code,
                        "tier_code": "CORE",
                        "sets": item.sets,
                        "reps": item.reps,
                        "work_seconds": item.work_seconds,
                        "rest_seconds": item.rest_seconds,
                        "transition_seconds": item.transition_seconds,
                        "estimated_item_seconds": item.estimated_item_seconds,
                        "instruction_available": True,
                    }
                    for item in self.items
                ],
            }
        }


def test_plan_revision_is_optimistic_and_idempotent() -> None:
    repository = _Repository()
    service = PlanRevisionService(repository, clock=lambda: NOW)
    user_id = uuid4()
    key = uuid4()
    request = PlanItemSetRepetitionRequest(
        expected_plan_id=repository.plan_id,
        expected_plan_revision=0,
        sets=3,
        reps=12,
    )

    first = service.edit_sets_and_repetitions(
        _Session(), user_id, repository.decision_id, UUID(int=1), request, key
    )
    replay = service.edit_sets_and_repetitions(
        _Session(), user_id, repository.decision_id, UUID(int=1), request, key
    )

    assert replay == first
    assert first.plan_revision == 1
    assert first.final_plan.items[0].sets == 3
    assert repository.save_count == 1

    with pytest.raises(PlanRevisionIdempotencyKeyReusedError):
        service.edit_sets_and_repetitions(
            _Session(),
            user_id,
            repository.decision_id,
            UUID(int=1),
            request.model_copy(update={"sets": 4}),
            key,
        )
    with pytest.raises(PlanRevisionStaleError):
        service.edit_sets_and_repetitions(
            _Session(), user_id, repository.decision_id, UUID(int=1), request, uuid4()
        )


def test_completed_item_content_cannot_be_changed() -> None:
    repository = _Repository(completed=frozenset({UUID(int=1)}))
    request = PlanItemSetRepetitionRequest(
        expected_plan_id=repository.plan_id,
        expected_plan_revision=0,
        sets=3,
        reps=12,
    )

    with pytest.raises(PlanRevisionError) as failure:
        PlanRevisionService(repository).edit_sets_and_repetitions(
            _Session(), uuid4(), repository.decision_id, UUID(int=1), request, uuid4()
        )
    assert failure.value.code is PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE
