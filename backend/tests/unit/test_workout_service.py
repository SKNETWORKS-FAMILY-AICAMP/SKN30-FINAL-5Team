from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.workouts.ports import IdempotencyRecord, SelectionSource, SessionState
from backend.app.modules.workouts.schemas import (
    DecisionSelectionRequest,
    WorkoutAdditionalActivityRequest,
    WorkoutSessionItemUpdateRequest,
    WorkoutSessionStartRequest,
    WorkoutTimerEventRequest,
)
from backend.app.modules.workouts.service import (
    IdempotencyKeyReusedError,
    OptionNotSelectableError,
    SessionEndedError,
    WorkoutService,
)

NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> Any:
        return nullcontext()


class FakeWorkoutRepository:
    def __init__(self, source: SelectionSource) -> None:
        self.source = source
        self.idempotency: dict[tuple[str, UUID], IdempotencyRecord] = {}
        self.user_id: UUID | None = None
        self.session_state: SessionState | None = None
        self.created_selection: dict[str, Any] | None = None
        self.timer_events: list[dict[str, Any]] = []
        self.additional_activities: list[dict[str, Any]] = []
        self.item_update_count = 0

    def acquire_idempotency_lock(self, *args: Any) -> None:
        pass

    def get_idempotency_record(
        self, session: Any, user_id: UUID, endpoint_code: str, key: UUID
    ) -> IdempotencyRecord | None:
        return self.idempotency.get((endpoint_code, key))

    def save_idempotency_record(self, session: Any, **values: Any) -> None:
        self.idempotency[(values["endpoint_code"], values["key"])] = IdempotencyRecord(
            values["request_hash"], values["response_payload"]
        )

    def get_selection_source(
        self, session: Any, user_id: UUID, decision_id: UUID, option_id: UUID
    ) -> SelectionSource | None:
        if decision_id != self.source.decision_id or option_id != self.source.option_id:
            return None
        return self.source

    def create_selection(self, session: Any, **values: Any) -> None:
        self.created_selection = values
        self.user_id = values["user_id"]
        workout_session_id = values["workout_session_id"]
        if workout_session_id is not None:
            self.session_state = SessionState(
                workout_session_id,
                "PLANNED",
                None,
                None,
                tuple((item_id, "PENDING", None) for item_id in self.source.plan_item_ids),
            )

    def get_session_state(
        self, session: Any, user_id: UUID, session_id: UUID
    ) -> SessionState | None:
        if self.user_id != user_id or self.session_state is None:
            return None
        return self.session_state if self.session_state.session_id == session_id else None

    def start_session(self, session: Any, session_id: UUID, started_at: datetime) -> SessionState:
        assert self.session_state is not None
        self.session_state = SessionState(
            session_id,
            "IN_PROGRESS",
            started_at,
            None,
            self.session_state.items,
        )
        return self.session_state

    def update_session_item(
        self,
        session: Any,
        session_id: UUID,
        plan_item_id: UUID,
        status_code: str,
        now: datetime,
    ) -> SessionState | None:
        assert self.session_state is not None
        self.item_update_count += 1
        items = tuple(
            (item_id, status_code, now if status_code == "COMPLETED" else None)
            if item_id == plan_item_id
            else (item_id, current_status, completed_at)
            for item_id, current_status, completed_at in self.session_state.items
        )
        self.session_state = SessionState(
            session_id,
            self.session_state.status_code,
            self.session_state.started_at,
            self.session_state.ended_at,
            items,
        )
        return self.session_state

    def create_timer_event(self, session: Any, **values: Any) -> None:
        self.timer_events.append(values)

    def create_additional_activity(self, session: Any, **values: Any) -> None:
        self.additional_activities.append(values)


def _source(*, option_code: str = "FINAL_ROUTINE", vetoed: bool = False) -> SelectionSource:
    decision_id = uuid4()
    option_id = uuid4()
    candidate_id = uuid4() if option_code == "FINAL_ROUTINE" else None
    action = "KEEP" if option_code == "FINAL_ROUTINE" else "REST"
    return SelectionSource(
        decision_id=decision_id,
        option_id=option_id,
        option_code=option_code,
        option_action_code=action,
        option_selectable=True,
        option_plan_candidate_id=candidate_id,
        decision_status_code="COMPLETED",
        decision_safety_status_code="PASS" if not vetoed else "BLOCKED",
        recommended_action_code=action,
        selected_candidate_id=candidate_id,
        selected_candidate_action_code=action if candidate_id else None,
        safety_candidate_id=candidate_id,
        safety_status_code="PASS" if not vetoed else "BLOCKED",
        safety_vetoed=vetoed,
        plan_item_ids=(uuid4(), uuid4()) if candidate_id else (),
        estimated_calories_burned=None,
        already_selected=False,
    )


def _select(
    repository: FakeWorkoutRepository, user_id: UUID, key: UUID | None = None
) -> tuple[WorkoutService, object]:
    service = WorkoutService(repository, clock=lambda: NOW)
    response = service.select_decision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        repository.source.decision_id,
        DecisionSelectionRequest(option_id=repository.source.option_id),
        key or uuid4(),
    )
    return service, response


def test_final_routine_selection_creates_one_planned_session_and_replays_retry() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    key = uuid4()
    service, first = _select(repository, user_id, key)
    retry = service.select_decision(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        repository.source.decision_id,
        DecisionSelectionRequest(option_id=repository.source.option_id),
        key,
    )
    assert retry == first
    assert retry.workout_session is not None
    assert retry.workout_session.status_code == "PLANNED"
    assert repository.session_state is not None
    assert all(status == "PENDING" for _, status, _ in repository.session_state.items)


def test_rest_selection_does_not_create_workout_session() -> None:
    repository = FakeWorkoutRepository(_source(option_code="REST"))
    _, response = _select(repository, uuid4())
    assert response.workout_session is None
    assert repository.session_state is None
    assert repository.created_selection["workout_session_id"] is None  # type: ignore[index]


def test_safety_vetoed_final_routine_is_not_selectable() -> None:
    repository = FakeWorkoutRepository(_source(vetoed=True))
    with pytest.raises(OptionNotSelectableError):
        _select(repository, uuid4())


def test_idempotency_key_reuse_with_different_payload_is_rejected() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    key = uuid4()
    service, _ = _select(repository, user_id, key)
    with pytest.raises(IdempotencyKeyReusedError):
        service.select_decision(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            repository.source.decision_id,
            DecisionSelectionRequest(option_id=uuid4()),
            key,
        )


def test_start_and_explicit_block_mutations_are_the_only_official_progress() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    service, selection = _select(repository, user_id)
    session_id = selection.workout_session.session_id
    started = service.start_session(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        WorkoutSessionStartRequest(started_at=NOW),
        uuid4(),
    )
    first_item_id = started.items[0].plan_item_id
    timer = service.record_timer_event(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        WorkoutTimerEventRequest(
            event_code="END", occurred_at=NOW + timedelta(minutes=30), client_recorded_at=NOW
        ),
        uuid4(),
    )
    activity = service.record_additional_activity(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        WorkoutAdditionalActivityRequest(
            activity_type_code="WALKING", duration_seconds=1800, intensity_code="LOW"
        ),
        uuid4(),
    )
    assert timer.session_status_code == "IN_PROGRESS"
    assert activity.session_status_code == "IN_PROGRESS"
    assert all(status == "PENDING" for _, status, _ in repository.session_state.items)

    completed = service.update_item(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        first_item_id,
        WorkoutSessionItemUpdateRequest(status_code="COMPLETED", client_recorded_at=NOW),
        uuid4(),
    )
    assert completed.completed_item_count == 1
    completed_at = completed.item.completed_at
    same_state = service.update_item(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        first_item_id,
        WorkoutSessionItemUpdateRequest(status_code="COMPLETED", client_recorded_at=NOW),
        uuid4(),
    )
    assert same_state.item.completed_at == completed_at
    assert repository.item_update_count == 1
    reverted = service.update_item(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        first_item_id,
        WorkoutSessionItemUpdateRequest(status_code="PENDING", client_recorded_at=NOW),
        uuid4(),
    )
    assert reverted.completed_item_count == 0
    assert reverted.item.completed_at is None


def test_timer_and_additional_activity_idempotency_create_one_record_each() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    service, selection = _select(repository, user_id)
    session_id = selection.workout_session.session_id
    service.start_session(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        session_id,
        WorkoutSessionStartRequest(started_at=NOW),
        uuid4(),
    )
    timer_request = WorkoutTimerEventRequest(
        event_code="START", occurred_at=NOW, client_recorded_at=NOW
    )
    timer_key = uuid4()
    first_timer = service.record_timer_event(
        FakeSession(),
        user_id,
        session_id,
        timer_request,
        timer_key,  # type: ignore[arg-type]
    )
    retry_timer = service.record_timer_event(
        FakeSession(),
        user_id,
        session_id,
        timer_request,
        timer_key,  # type: ignore[arg-type]
    )
    activity_request = WorkoutAdditionalActivityRequest(
        activity_type_code="CYCLING", duration_seconds=600
    )
    activity_key = uuid4()
    first_activity = service.record_additional_activity(
        FakeSession(),
        user_id,
        session_id,
        activity_request,
        activity_key,  # type: ignore[arg-type]
    )
    retry_activity = service.record_additional_activity(
        FakeSession(),
        user_id,
        session_id,
        activity_request,
        activity_key,  # type: ignore[arg-type]
    )
    assert retry_timer == first_timer
    assert retry_activity == first_activity
    assert len(repository.timer_events) == 1
    assert len(repository.additional_activities) == 1


def test_every_wave_7a_mutation_rejects_an_ended_session() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    service, selection = _select(repository, user_id)
    session_id = selection.workout_session.session_id
    repository.session_state = SessionState(
        session_id,
        "COMPLETED",
        NOW,
        NOW + timedelta(minutes=10),
        tuple((item_id, "COMPLETED", NOW) for item_id in repository.source.plan_item_ids),
    )
    calls = (
        lambda: service.start_session(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            session_id,
            WorkoutSessionStartRequest(started_at=NOW),
            uuid4(),
        ),
        lambda: service.update_item(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            session_id,
            repository.source.plan_item_ids[0],
            WorkoutSessionItemUpdateRequest(status_code="PENDING", client_recorded_at=NOW),
            uuid4(),
        ),
        lambda: service.record_timer_event(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            session_id,
            WorkoutTimerEventRequest(event_code="END", occurred_at=NOW, client_recorded_at=NOW),
            uuid4(),
        ),
        lambda: service.record_additional_activity(
            FakeSession(),  # type: ignore[arg-type]
            user_id,
            session_id,
            WorkoutAdditionalActivityRequest(activity_type_code="WALKING", duration_seconds=60),
            uuid4(),
        ),
    )
    for call in calls:
        with pytest.raises(SessionEndedError):
            call()
