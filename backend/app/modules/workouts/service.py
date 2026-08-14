import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.modules.workouts.codes import (
    ADDITIONAL_ACTIVITY_ENDPOINT_CODE,
    SELECTION_ENDPOINT_CODE,
    SESSION_ITEM_ENDPOINT_CODE,
    SESSION_START_ENDPOINT_CODE,
    TERMINAL_SESSION_STATUS_CODES,
    TIMER_EVENT_ENDPOINT_CODE,
)
from backend.app.modules.workouts.ports import SessionState, WorkoutRepositoryPort
from backend.app.modules.workouts.schemas import (
    DecisionSelectionRequest,
    DecisionSelectionResponse,
    WorkoutAdditionalActivityRequest,
    WorkoutAdditionalActivityResponse,
    WorkoutSessionItemResponse,
    WorkoutSessionItemUpdateRequest,
    WorkoutSessionItemUpdateResponse,
    WorkoutSessionStartRequest,
    WorkoutSessionStartResponse,
    WorkoutSessionSummary,
    WorkoutTimerEventRequest,
    WorkoutTimerEventResponse,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class WorkoutResourceNotFoundError(Exception):
    pass


class OptionNotSelectableError(Exception):
    pass


class DecisionAlreadySelectedError(Exception):
    pass


class InvalidSessionStateError(Exception):
    pass


class SessionEndedError(Exception):
    pass


class IdempotencyKeyReusedError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(resource: dict[str, object], request: BaseModel) -> str:
    value = {**resource, "body": request.model_dump(mode="json")}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class WorkoutService:
    def __init__(
        self,
        repository: WorkoutRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._uuid_factory = uuid_factory

    def _prior_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
        response_type: type[ResponseT],
    ) -> ResponseT | None:
        self._repository.acquire_idempotency_lock(session, user_id, endpoint_code, idempotency_key)
        prior = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if prior is None:
            return None
        if prior.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return response_type.model_validate(prior.response_payload)

    def _save_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
        response: BaseModel,
        now: datetime,
    ) -> None:
        self._repository.save_idempotency_record(
            session,
            user_id=user_id,
            endpoint_code=endpoint_code,
            key=idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json"),
            now=now,
        )

    def select_decision(
        self,
        session: Session,
        user_id: UUID,
        decision_id: UUID,
        request: DecisionSelectionRequest,
        idempotency_key: UUID,
    ) -> DecisionSelectionResponse:
        request_hash = _request_hash({"decision_id": str(decision_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SELECTION_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=DecisionSelectionResponse,
            )
            if prior is not None:
                return prior
            source = self._repository.get_selection_source(
                session, user_id, decision_id, request.option_id
            )
            if source is None or source.decision_status_code != "COMPLETED":
                raise WorkoutResourceNotFoundError
            if source.already_selected:
                raise DecisionAlreadySelectedError
            if not source.option_selectable:
                raise OptionNotSelectableError

            workout_session_id: UUID | None = None
            if source.option_code == "FINAL_ROUTINE":
                valid_final = (
                    source.decision_safety_status_code in {"PASS", "REVISE"}
                    and source.safety_status_code in {"PASS", "REVISE"}
                    and source.safety_vetoed is False
                    and source.selected_candidate_id is not None
                    and source.option_plan_candidate_id == source.selected_candidate_id
                    and source.safety_candidate_id == source.selected_candidate_id
                    and source.option_action_code == source.selected_candidate_action_code
                    and source.option_action_code == source.recommended_action_code
                    and bool(source.plan_item_ids)
                )
                if not valid_final:
                    raise OptionNotSelectableError
                workout_session_id = self._uuid_factory()
            elif source.option_code == "REST":
                if (
                    source.option_action_code != "REST"
                    or source.option_plan_candidate_id is not None
                ):
                    raise OptionNotSelectableError
            else:
                raise OptionNotSelectableError

            now = self._clock()
            selection_id = self._uuid_factory()
            self._repository.create_selection(
                session,
                source=source,
                user_id=user_id,
                selection_id=selection_id,
                workout_session_id=workout_session_id,
                idempotency_key=idempotency_key,
                now=now,
            )
            response = DecisionSelectionResponse(
                selection_id=selection_id,
                decision_id=decision_id,
                option_id=request.option_id,
                selected_action_code=cast(
                    Literal["KEEP", "DOWNSHIFT", "CHANGE", "RECOVERY", "REST"],
                    source.option_action_code,
                ),
                workout_session=None
                if workout_session_id is None
                else WorkoutSessionSummary(session_id=workout_session_id, status_code="PLANNED"),
                selected_at=now,
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SELECTION_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def start_session(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutSessionStartRequest,
        idempotency_key: UUID,
    ) -> WorkoutSessionStartResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_START_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSessionStartResponse,
            )
            if prior is not None:
                return prior
            state = self._required_state(session, user_id, session_id)
            self._reject_ended(state)
            if state.status_code != "PLANNED":
                raise InvalidSessionStateError
            state = self._repository.start_session(session, session_id, request.started_at)
            response = WorkoutSessionStartResponse(
                session_id=session_id,
                status_code="IN_PROGRESS",
                started_at=request.started_at,
                items=self._items(state),
                current_plan_item_id=next(
                    (
                        plan_item_id
                        for plan_item_id, status, _ in state.items
                        if status == "PENDING"
                    ),
                    None,
                ),
            )
            now = self._clock()
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_START_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def update_item(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        plan_item_id: UUID,
        request: WorkoutSessionItemUpdateRequest,
        idempotency_key: UUID,
    ) -> WorkoutSessionItemUpdateResponse:
        request_hash = _request_hash(
            {"session_id": str(session_id), "plan_item_id": str(plan_item_id)}, request
        )
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_ITEM_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSessionItemUpdateResponse,
            )
            if prior is not None:
                return prior
            state = self._required_in_progress(session, user_id, session_id)
            current_item = next((item for item in state.items if item[0] == plan_item_id), None)
            if current_item is None:
                raise WorkoutResourceNotFoundError
            now = self._clock()
            if current_item[1] != request.status_code:
                updated_state = self._repository.update_session_item(
                    session, session_id, plan_item_id, request.status_code, now
                )
                if updated_state is None:
                    raise WorkoutResourceNotFoundError
                state = updated_state
            item = next(value for value in self._items(state) if value.plan_item_id == plan_item_id)
            completed_count = sum(status == "COMPLETED" for _, status, _ in state.items)
            response = WorkoutSessionItemUpdateResponse(
                session_id=session_id,
                status_code="IN_PROGRESS",
                item=item,
                completed_item_count=completed_count,
                total_item_count=len(state.items),
                next_pending_plan_item_id=next(
                    (item_id for item_id, status, _ in state.items if status == "PENDING"), None
                ),
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_ITEM_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def record_timer_event(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutTimerEventRequest,
        idempotency_key: UUID,
    ) -> WorkoutTimerEventResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=TIMER_EVENT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutTimerEventResponse,
            )
            if prior is not None:
                return prior
            self._required_in_progress(session, user_id, session_id)
            now = self._clock()
            event_id = self._uuid_factory()
            self._repository.create_timer_event(
                session,
                event_id=event_id,
                session_id=session_id,
                event_code=request.event_code,
                occurred_at=request.occurred_at,
                client_recorded_at=request.client_recorded_at,
                now=now,
            )
            response = WorkoutTimerEventResponse(
                event_id=event_id,
                session_id=session_id,
                event_code=request.event_code,
                occurred_at=request.occurred_at,
                client_recorded_at=request.client_recorded_at,
                created_at=now,
                session_status_code="IN_PROGRESS",
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=TIMER_EVENT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def record_additional_activity(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutAdditionalActivityRequest,
        idempotency_key: UUID,
    ) -> WorkoutAdditionalActivityResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=ADDITIONAL_ACTIVITY_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutAdditionalActivityResponse,
            )
            if prior is not None:
                return prior
            self._required_in_progress(session, user_id, session_id)
            now = self._clock()
            activity_id = self._uuid_factory()
            self._repository.create_additional_activity(
                session,
                activity_id=activity_id,
                session_id=session_id,
                activity_type_code=request.activity_type_code,
                duration_seconds=request.duration_seconds,
                intensity_code=request.intensity_code,
                note=request.note,
                now=now,
            )
            response = WorkoutAdditionalActivityResponse(
                activity_id=activity_id,
                session_id=session_id,
                activity_type_code=request.activity_type_code,
                duration_seconds=request.duration_seconds,
                intensity_code=request.intensity_code,
                note=request.note,
                created_at=now,
                session_status_code="IN_PROGRESS",
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=ADDITIONAL_ACTIVITY_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def _required_state(self, session: Session, user_id: UUID, session_id: UUID) -> SessionState:
        state = self._repository.get_session_state(session, user_id, session_id)
        if state is None:
            raise WorkoutResourceNotFoundError
        return state

    def _required_in_progress(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> SessionState:
        state = self._required_state(session, user_id, session_id)
        self._reject_ended(state)
        if state.status_code != "IN_PROGRESS":
            raise InvalidSessionStateError
        return state

    @staticmethod
    def _reject_ended(state: SessionState) -> None:
        if state.ended_at is not None or state.status_code in TERMINAL_SESSION_STATUS_CODES:
            raise SessionEndedError

    @staticmethod
    def _items(state: SessionState) -> list[WorkoutSessionItemResponse]:
        return [
            WorkoutSessionItemResponse(
                plan_item_id=plan_item_id,
                status_code=cast(Literal["PENDING", "COMPLETED"], status_code),
                completed_at=completed_at,
            )
            for plan_item_id, status_code, completed_at in state.items
        ]


__all__ = [
    "DecisionAlreadySelectedError",
    "IdempotencyKeyReusedError",
    "InvalidSessionStateError",
    "OptionNotSelectableError",
    "SessionEndedError",
    "WorkoutResourceNotFoundError",
    "WorkoutService",
]
