import base64
import binascii
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Literal, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.domain.rules.safety import (
    AdverseReactionCode,
    BodyAreaCode,
    Discomfort,
    DiscomfortSeverityCode,
    SafetyContext,
)
from backend.app.domain.rules.workout_execution import (
    InvalidSessionTransitionError,
    NotCompletedReasonRequiredError,
    WorkoutBlockStatusCode,
    WorkoutCompletionEvidence,
    WorkoutExecutionStateCode,
    WorkoutSessionStatusCode,
    WorkoutStopReasonCode,
    classify_workout_safety_event,
    derive_completion_code,
    mark_session_not_completed,
    resume_execution,
    stop_execution,
)
from backend.app.domain.rules.workout_execution import (
    finish_session as derive_finished_status,
)
from backend.app.modules.workouts.codes import (
    ADDITIONAL_ACTIVITY_ENDPOINT_CODE,
    FEEDBACK_ENDPOINT_CODE,
    SAFETY_EVENT_ENDPOINT_CODE,
    SELECTION_ENDPOINT_CODE,
    SESSION_FINISH_ENDPOINT_CODE,
    SESSION_ITEM_ENDPOINT_CODE,
    SESSION_NOT_COMPLETED_ENDPOINT_CODE,
    SESSION_START_ENDPOINT_CODE,
    SESSION_STOP_ENDPOINT_CODE,
    TERMINAL_SESSION_STATUS_CODES,
    TIMER_EVENT_ENDPOINT_CODE,
)
from backend.app.modules.workouts.ports import (
    SessionState,
    WorkoutLogCursor,
    WorkoutRepositoryPort,
)
from backend.app.modules.workouts.schemas import (
    DecisionSelectionRequest,
    DecisionSelectionResponse,
    WorkoutAdditionalActivityRequest,
    WorkoutAdditionalActivityResponse,
    WorkoutDiscomfortInput,
    WorkoutFeedbackRequest,
    WorkoutFeedbackResponse,
    WorkoutFeedbackSummary,
    WorkoutSafetyEventRequest,
    WorkoutSafetyEventResponse,
    WorkoutSessionDetailResponse,
    WorkoutSessionFinishRequest,
    WorkoutSessionFinishResponse,
    WorkoutSessionItemResponse,
    WorkoutSessionItemResult,
    WorkoutSessionItemUpdateRequest,
    WorkoutSessionItemUpdateResponse,
    WorkoutSessionListResponse,
    WorkoutSessionLogSummary,
    WorkoutSessionNotCompletedRequest,
    WorkoutSessionNotCompletedResponse,
    WorkoutSessionStartRequest,
    WorkoutSessionStartResponse,
    WorkoutSessionStopRequest,
    WorkoutSessionStopResponse,
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


class NotCompletedReasonRequiredServiceError(Exception):
    pass


class InvalidSafetyEventInputError(Exception):
    pass


class FeedbackAlreadyExistsError(Exception):
    pass


class WorkoutLogNotFoundError(Exception):
    pass


class InvalidWorkoutLogQueryError(Exception):
    pass


_GUIDANCE: dict[str, str] = {
    "MILD_DISCOMFORT_CAUTION": "불편함이 계속되거나 심해지면 운동을 중단하세요.",
    "MODERATE_DISCOMFORT_CAUTION": (
        "현재 동작을 멈추고 상태를 확인하세요. 불편함이 계속되면 운동을 중단하세요."
    ),
    "SEVERE_OR_ACUTE_STOP": (
        "운동을 중단하고 휴식하세요. 증상이 지속되거나 악화되면 적절한 도움을 요청하세요."
    ),
    "SERIOUS_ADVERSE_REACTION_STOP": "운동을 즉시 중단하고 지역 응급의료 도움을 요청하세요.",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(resource: dict[str, object], request: BaseModel) -> str:
    value = {**resource, "body": request.model_dump(mode="json")}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _encode_log_cursor(cursor: WorkoutLogCursor) -> str:
    payload = json.dumps(
        {"date": cursor.local_date.isoformat(), "session_id": str(cursor.session_id), "version": 1},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_log_cursor(value: str) -> WorkoutLogCursor:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {"date", "session_id", "version"}:
            raise ValueError
        if payload["version"] != 1:
            raise ValueError
        cursor = WorkoutLogCursor(
            local_date=date.fromisoformat(payload["date"]),
            session_id=UUID(payload["session_id"]),
        )
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError):
        raise InvalidWorkoutLogQueryError from None
    if _encode_log_cursor(cursor) != value:
        raise InvalidWorkoutLogQueryError
    return cursor


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

    def list_workout_logs(
        self,
        session: Session,
        user_id: UUID,
        *,
        from_local_date: date | None,
        to_local_date: date | None,
        status_code: str | None,
        cursor: str | None,
        limit: int,
    ) -> WorkoutSessionListResponse:
        if (
            from_local_date is not None
            and to_local_date is not None
            and from_local_date > to_local_date
        ):
            raise InvalidWorkoutLogQueryError
        decoded_cursor = None if cursor is None else _decode_log_cursor(cursor)
        rows = self._repository.list_workout_logs(
            session,
            user_id,
            from_local_date=from_local_date,
            to_local_date=to_local_date,
            status_code=status_code,
            cursor=decoded_cursor,
            limit=limit + 1,
        )
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = _encode_log_cursor(
                WorkoutLogCursor(local_date=last.local_date, session_id=last.session_id)
            )
        return WorkoutSessionListResponse(
            items=[
                WorkoutSessionLogSummary.model_validate(row, from_attributes=True) for row in page
            ],
            next_cursor=next_cursor,
        )

    def get_workout_log_detail(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> WorkoutSessionDetailResponse:
        record = self._repository.get_workout_log_detail(session, user_id, session_id)
        if record is None:
            raise WorkoutLogNotFoundError
        items = [
            WorkoutSessionItemResult.model_validate(item, from_attributes=True)
            for item in record.items
        ]
        feedback = None
        if record.feedback is not None:
            feedback = WorkoutFeedbackSummary.model_validate(record.feedback, from_attributes=True)
        return WorkoutSessionDetailResponse(
            session_id=record.session_id,
            local_date=record.local_date,
            status_code=record.status_code,
            completed_item_count=sum(item.status_code == "COMPLETED" for item in record.items),
            total_item_count=len(record.items),
            requested_duration_minutes=record.requested_duration_minutes,
            items=items,
            feedback=feedback,
            not_completed_reason_code=record.not_completed_reason_code,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )

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
                else WorkoutSessionSummary(
                    session_id=workout_session_id,
                    status_code="PLANNED",
                    target_duration_seconds=source.target_duration_seconds,
                ),
                selected_at=now,
                pressure_notifications_allowed=source.option_action_code != "REST",
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
                execution_state_code="RUNNING",
                target_duration_seconds=state.target_duration_seconds or 0,
                accumulated_progress_seconds=state.accumulated_progress_seconds,
                accumulated_rest_seconds=state.accumulated_rest_seconds,
                accumulated_paused_seconds=state.accumulated_paused_seconds,
                is_resumable=False,
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
            state = self._required_in_progress(session, user_id, session_id)
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
            if request.event_code == "PAUSE":
                if (state.execution_state_code or "RUNNING") not in {"RUNNING", "RESTING"}:
                    raise InvalidSessionStateError
                state = self._repository.transition_execution_state(
                    session,
                    session_id=session_id,
                    execution_state_code="PAUSED",
                    occurred_at=request.occurred_at,
                    is_resumable=False,
                    stop_reason_code=None,
                )
            elif request.event_code == "RESUME":
                if (
                    state.execution_state_code == "STOPPED_RESUMABLE"
                    and state.local_date is not None
                    and request.occurred_at.date() != state.local_date
                ):
                    raise InvalidSessionStateError
                try:
                    execution_state = resume_execution(
                        WorkoutExecutionStateCode(state.execution_state_code or "RUNNING"),
                        is_resumable=state.is_resumable,
                    )
                except InvalidSessionTransitionError as exc:
                    raise InvalidSessionStateError from exc
                state = self._repository.transition_execution_state(
                    session,
                    session_id=session_id,
                    execution_state_code=execution_state.value,
                    occurred_at=request.occurred_at,
                    is_resumable=False,
                    stop_reason_code=None,
                )
            response = WorkoutTimerEventResponse(
                event_id=event_id,
                session_id=session_id,
                event_code=request.event_code,
                occurred_at=request.occurred_at,
                client_recorded_at=request.client_recorded_at,
                created_at=now,
                session_status_code="IN_PROGRESS",
                execution_state_code=cast(
                    Literal["RUNNING", "PAUSED"], state.execution_state_code or "RUNNING"
                ),
                accumulated_progress_seconds=state.accumulated_progress_seconds,
                accumulated_rest_seconds=state.accumulated_rest_seconds,
                accumulated_paused_seconds=state.accumulated_paused_seconds,
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

    def record_safety_event(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutSafetyEventRequest,
        idempotency_key: UUID,
    ) -> WorkoutSafetyEventResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SAFETY_EVENT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSafetyEventResponse,
            )
            if prior is not None:
                return prior
            state = self._required_in_progress(session, user_id, session_id)
            evidence = self._completion_evidence(state, 0)
            if evidence.completed_block_count == evidence.total_block_count:
                raise InvalidSessionStateError
            now = self._clock()
            event_id = self._uuid_factory()
            completion_code = derive_completion_code(evidence).value
            # Always SESSION_STOPPED. STOP_AND_SEEK_HELP needs to know the symptom,
            # and this flow deliberately does not ask for one; the reviewed stop
            # guidance already tells the user to seek emergency help if they have
            # chest pain, fainting or similar. The check-in Red Flag path is where
            # STOP_AND_SEEK_HELP is decided from evidence the user did give.
            result_code = "SESSION_STOPPED"
            self._repository.create_safety_event(
                session,
                event_id=event_id,
                session_id=session_id,
                occurred_at=now,
                result_code=result_code,
                completion_code=completion_code,
                rule_version="workout-safety-event-v2",
                now=now,
            )
            self._repository.transition_execution_state(
                session,
                session_id=session_id,
                execution_state_code="STOPPED_SAFETY",
                occurred_at=now,
                is_resumable=False,
                stop_reason_code=request.stop_reason_code,
                completion_code=completion_code,
                ended_at=now,
            )
            response = WorkoutSafetyEventResponse(
                event_id=event_id,
                result_code=cast(Literal["SESSION_STOPPED", "STOP_AND_SEEK_HELP"], result_code),
                execution_state_code="STOPPED_SAFETY",
                completion_code=cast(Literal["PARTIAL", "NOT_COMPLETED"], completion_code),
                is_resumable=False,
                guidance=(
                    _GUIDANCE["SERIOUS_ADVERSE_REACTION_STOP"]
                    if result_code == "STOP_AND_SEEK_HELP"
                    else _GUIDANCE["SEVERE_OR_ACUTE_STOP"]
                ),
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SAFETY_EVENT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def stop_session(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutSessionStopRequest,
        idempotency_key: UUID,
    ) -> WorkoutSessionStopResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_STOP_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSessionStopResponse,
            )
            if prior is not None:
                return prior
            state = self._required_in_progress(session, user_id, session_id)
            try:
                execution_state, is_resumable = stop_execution(
                    WorkoutExecutionStateCode(state.execution_state_code or "RUNNING"),
                    WorkoutStopReasonCode(request.stop_reason_code),
                )
            except InvalidSessionTransitionError as exc:
                raise InvalidSessionStateError from exc
            completion_code = (
                derive_completion_code(self._completion_evidence(state, 0)).value
                if execution_state is WorkoutExecutionStateCode.STOPPED_SAFETY
                else None
            )
            if execution_state is WorkoutExecutionStateCode.STOPPED_SAFETY:
                evidence = self._completion_evidence(state, 0)
                if evidence.completed_block_count == evidence.total_block_count:
                    raise InvalidSessionStateError
                # Always SESSION_STOPPED. STOP_AND_SEEK_HELP needs to know the symptom,
                # and this flow deliberately does not ask for one; the reviewed stop
                # guidance already tells the user to seek emergency help if they have
                # chest pain, fainting or similar. The check-in Red Flag path is where
                # STOP_AND_SEEK_HELP is decided from evidence the user did give.
                result_code = "SESSION_STOPPED"
                self._repository.create_safety_event(
                    session,
                    event_id=self._uuid_factory(),
                    session_id=session_id,
                    occurred_at=request.stopped_at,
                    result_code=result_code,
                    completion_code=cast(str, completion_code),
                    rule_version="workout-safety-event-v2",
                    now=self._clock(),
                )
            state = self._repository.transition_execution_state(
                session,
                session_id=session_id,
                execution_state_code=execution_state.value,
                occurred_at=request.stopped_at,
                is_resumable=is_resumable,
                stop_reason_code=request.stop_reason_code,
                completion_code=completion_code,
                ended_at=(request.stopped_at if not is_resumable else None),
            )
            response = WorkoutSessionStopResponse(
                session_id=session_id,
                completion_code=cast(Literal["PARTIAL", "NOT_COMPLETED"] | None, completion_code),
                execution_state_code=cast(
                    Literal["STOPPED_RESUMABLE", "STOPPED_SAFETY"], execution_state.value
                ),
                stop_reason_code=request.stop_reason_code,
                is_resumable=is_resumable,
                accumulated_progress_seconds=state.accumulated_progress_seconds,
                accumulated_rest_seconds=state.accumulated_rest_seconds,
                accumulated_paused_seconds=state.accumulated_paused_seconds,
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_STOP_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=self._clock(),
            )
        return response

    def finish_session(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutSessionFinishRequest,
        idempotency_key: UUID,
    ) -> WorkoutSessionFinishResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_FINISH_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSessionFinishResponse,
            )
            if prior is not None:
                return prior
            state = self._required_in_progress(session, user_id, session_id)
            evidence = self._completion_evidence(state, request.actual_elapsed_seconds)
            try:
                status = derive_finished_status(
                    WorkoutSessionStatusCode(state.status_code), evidence
                )
            except NotCompletedReasonRequiredError as exc:
                raise NotCompletedReasonRequiredServiceError from exc
            except InvalidSessionTransitionError as exc:
                raise InvalidSessionStateError from exc
            state = self._repository.transition_execution_state(
                session,
                session_id=session_id,
                execution_state_code="COMPLETED",
                occurred_at=request.finished_at,
                is_resumable=False,
                stop_reason_code=None,
                completion_code=status.value,
                ended_at=request.finished_at,
            )
            response = WorkoutSessionFinishResponse(
                session_id=session_id,
                status_code=cast(Literal["COMPLETED", "PARTIAL"], status.value),
                ended_at=request.finished_at,
                completed_item_count=evidence.completed_block_count,
                total_item_count=evidence.total_block_count,
                actual_elapsed_seconds=state.accumulated_progress_seconds,
                estimated_calories_burned=state.estimated_calories_burned,
                completion_code=cast(Literal["COMPLETED", "PARTIAL"], status.value),
                execution_state_code="COMPLETED",
            )
            now = self._clock()
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_FINISH_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def mark_not_completed(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutSessionNotCompletedRequest,
        idempotency_key: UUID,
    ) -> WorkoutSessionNotCompletedResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_NOT_COMPLETED_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutSessionNotCompletedResponse,
            )
            if prior is not None:
                return prior
            state = self._required_state(session, user_id, session_id)
            self._reject_ended(state)
            evidence = self._completion_evidence(state, 0)
            try:
                status = mark_session_not_completed(
                    WorkoutSessionStatusCode(state.status_code), evidence, request.reason_code
                )
            except InvalidSessionTransitionError as exc:
                raise InvalidSessionStateError from exc
            now = self._clock()
            self._repository.transition_execution_state(
                session,
                session_id=session_id,
                execution_state_code="COMPLETED",
                occurred_at=request.ended_at,
                is_resumable=False,
                stop_reason_code=None,
                completion_code=status.value,
                ended_at=request.ended_at,
            )
            self._repository.create_skip_feedback(
                session,
                session_id=session_id,
                reason_code=request.reason_code.value,
                now=now,
            )
            response = WorkoutSessionNotCompletedResponse(
                session_id=session_id,
                status_code="NOT_COMPLETED",
                ended_at=request.ended_at,
                reason_code=request.reason_code,
                completed_item_count=0,
                total_item_count=evidence.total_block_count,
                penalty_applied=False,
                completion_code="NOT_COMPLETED",
                execution_state_code="COMPLETED",
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=SESSION_NOT_COMPLETED_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
        return response

    def record_feedback(
        self,
        session: Session,
        user_id: UUID,
        session_id: UUID,
        request: WorkoutFeedbackRequest,
        idempotency_key: UUID,
    ) -> WorkoutFeedbackResponse:
        request_hash = _request_hash({"session_id": str(session_id)}, request)
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=FEEDBACK_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_type=WorkoutFeedbackResponse,
            )
            if prior is not None:
                return prior
            state = self._required_state(session, user_id, session_id)
            if state.status_code not in TERMINAL_SESSION_STATUS_CODES:
                raise InvalidSessionStateError
            if self._repository.feedback_exists(session, session_id):
                raise FeedbackAlreadyExistsError
            now = self._clock()
            self._repository.create_feedback(
                session,
                session_id=session_id,
                difficulty_code=request.difficulty_code,
                fatigue_code=request.fatigue_code,
                satisfaction_code=request.satisfaction_code,
                pain_occurred=request.pain_occurred,
                discomforts=tuple(
                    (item.body_area_code.value, item.severity_code.value)
                    for item in request.discomforts
                ),
                adverse_reaction_codes=tuple(code.value for code in request.adverse_reaction_codes),
                now=now,
            )
            guidance_code: str | None = None
            guidance: str | None = None
            pressure_allowed = True
            if request.discomforts or request.adverse_reaction_codes:
                context = self._safety_context(request.discomforts, request.adverse_reaction_codes)
                decision = classify_workout_safety_event(
                    WorkoutSessionStatusCode.IN_PROGRESS, context
                )
                guidance_code = decision.guidance_code.value
                guidance = _GUIDANCE[guidance_code]
                pressure_allowed = decision.resulting_action_code is None
            response = WorkoutFeedbackResponse(
                session_id=session_id,
                session_status_code=cast(
                    Literal["COMPLETED", "PARTIAL", "NOT_COMPLETED", "STOPPED_FOR_SAFETY"],
                    state.status_code,
                ),
                created_at=now,
                guidance_code=guidance_code,
                guidance=guidance,
                pressure_notifications_allowed=pressure_allowed,
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=FEEDBACK_ENDPOINT_CODE,
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

    @staticmethod
    def _completion_evidence(
        state: SessionState, actual_elapsed_seconds: int
    ) -> WorkoutCompletionEvidence:
        return WorkoutCompletionEvidence(
            block_status_codes=tuple(
                WorkoutBlockStatusCode(status_code) for _, status_code, _ in state.items
            ),
            actual_elapsed_seconds=actual_elapsed_seconds,
        )

    @staticmethod
    def _safety_context(
        discomforts: list[WorkoutDiscomfortInput],
        adverse_reaction_codes: list[AdverseReactionCode],
    ) -> SafetyContext:
        return SafetyContext(
            discomforts=tuple(
                Discomfort(
                    BodyAreaCode(item.body_area_code),
                    DiscomfortSeverityCode[item.severity_code.value],
                )
                for item in discomforts
            ),
            adverse_reaction_codes=tuple(
                AdverseReactionCode(code) for code in adverse_reaction_codes
            ),
        )


__all__ = [
    "DecisionAlreadySelectedError",
    "FeedbackAlreadyExistsError",
    "IdempotencyKeyReusedError",
    "InvalidSessionStateError",
    "InvalidSafetyEventInputError",
    "InvalidWorkoutLogQueryError",
    "NotCompletedReasonRequiredServiceError",
    "OptionNotSelectableError",
    "SessionEndedError",
    "WorkoutResourceNotFoundError",
    "WorkoutLogNotFoundError",
    "WorkoutService",
]
