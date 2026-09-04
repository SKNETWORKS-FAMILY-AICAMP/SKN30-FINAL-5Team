"""Application service for the two user edits of the day's plan.

Transactions, locking, idempotency and the optimistic-concurrency check live here. The
rules that decide whether an edit is legal live in `plan_revision.py` and stay pure.

Neither edit consumes the day's re-recommendation budget. Changing a set count is the
user rewriting their own plan, not asking the system for a different one, so it has
nothing to do with the regeneration limit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.modules.decisions.plan_revision import (
    PLAN_REVISION_POLICY_VERSION,
    PlanRevisionError,
    PlanRevisionFailureCode,
    PlanRevisionItem,
    apply_order_edit,
    apply_set_repetition_edit,
    plan_estimated_duration_seconds,
)
from backend.app.modules.decisions.ports import (
    PlanRevisionRepositoryPort,
    PlanRevisionSource,
    PlanRevisionWrite,
)
from backend.app.modules.decisions.schemas import (
    DecisionPlan,
    PlanItemOrderRequest,
    PlanItemSetRepetitionRequest,
    PlanRevisionResponse,
)

PLAN_ITEM_ENDPOINT_CODE = "PATCH_DECISION_PLAN_ITEM"
PLAN_ITEM_ORDER_ENDPOINT_CODE = "PUT_DECISION_PLAN_ITEM_ORDER"


class PlanNotFoundError(Exception):
    """No completed decision with a selected plan exists in the user's scope."""


class PlanRevisionStaleError(Exception):
    """The plan or its revision moved on since the client last read it."""


class PlanRevisionIdempotencyKeyReusedError(Exception):
    """The same key was presented with a different request."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(decision_id: UUID, request: BaseModel) -> str:
    payload = {"decision_id": str(decision_id), "request": request.model_dump(mode="json")}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class PlanRevisionService:
    def __init__(
        self,
        repository: PlanRevisionRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def edit_sets_and_repetitions(
        self,
        session: Session,
        user_id: UUID,
        decision_id: UUID,
        plan_item_id: UUID,
        request: PlanItemSetRepetitionRequest,
        idempotency_key: UUID,
    ) -> PlanRevisionResponse:
        def revise(source: PlanRevisionSource) -> tuple[PlanRevisionItem, ...]:
            if plan_item_id in source.completed_plan_item_ids:
                # Rewriting a block the user already performed would change what the
                # record says they did, so it is refused the same way a reorder is.
                raise PlanRevisionError(PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE)
            return apply_set_repetition_edit(
                source.items,
                plan_item_id=plan_item_id,
                sets=request.sets,
                reps=request.reps,
            )

        return self._revise(
            session,
            user_id=user_id,
            decision_id=decision_id,
            request=request,
            idempotency_key=idempotency_key,
            endpoint_code=PLAN_ITEM_ENDPOINT_CODE,
            expected_plan_id=request.expected_plan_id,
            expected_plan_revision=request.expected_plan_revision,
            revise=revise,
        )

    def edit_order(
        self,
        session: Session,
        user_id: UUID,
        decision_id: UUID,
        request: PlanItemOrderRequest,
        idempotency_key: UUID,
    ) -> PlanRevisionResponse:
        def revise(source: PlanRevisionSource) -> tuple[PlanRevisionItem, ...]:
            return apply_order_edit(
                source.items,
                ordered_plan_item_ids=request.ordered_plan_item_ids,
                completed_plan_item_ids=source.completed_plan_item_ids,
            )

        return self._revise(
            session,
            user_id=user_id,
            decision_id=decision_id,
            request=request,
            idempotency_key=idempotency_key,
            endpoint_code=PLAN_ITEM_ORDER_ENDPOINT_CODE,
            expected_plan_id=request.expected_plan_id,
            expected_plan_revision=request.expected_plan_revision,
            revise=revise,
        )

    def _revise(
        self,
        session: Session,
        *,
        user_id: UUID,
        decision_id: UUID,
        request: BaseModel,
        idempotency_key: UUID,
        endpoint_code: str,
        expected_plan_id: UUID,
        expected_plan_revision: int,
        revise: Callable[[PlanRevisionSource], tuple[PlanRevisionItem, ...]],
    ) -> PlanRevisionResponse:
        request_hash = _request_hash(decision_id, request)
        with session.begin():
            self._repository.acquire_endpoint_lock(
                session, user_id, endpoint_code, idempotency_key
            )
            prior = self._repository.get_endpoint_idempotency(
                session, user_id, endpoint_code, idempotency_key
            )
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise PlanRevisionIdempotencyKeyReusedError
                return PlanRevisionResponse.model_validate(prior.response_payload)

            source = self._repository.lock_plan_for_revision(session, user_id, decision_id)
            if source is None:
                raise PlanNotFoundError
            if (
                source.plan_id != expected_plan_id
                or source.user_revision_sequence != expected_plan_revision
            ):
                # A regeneration replaces the plan and another edit moves the counter.
                # Either way the client is editing something it can no longer see.
                raise PlanRevisionStaleError
            if not source.editable:
                raise PlanRevisionError(PlanRevisionFailureCode.PLAN_NOT_EDITABLE)

            revised = revise(source)
            estimated = plan_estimated_duration_seconds(
                revised,
                setup_seconds=source.setup_seconds,
                warmup_seconds=source.warmup_seconds,
                cooldown_seconds=source.cooldown_seconds,
            )
            revision = self._repository.save_plan_revision(
                session,
                plan_id=source.plan_id,
                writes=tuple(
                    PlanRevisionWrite(
                        plan_item_id=item.plan_item_id,
                        sequence=item.sequence,
                        sets=item.sets,
                        reps=item.reps,
                        work_seconds_per_set=item.work_seconds_per_set,
                        work_seconds=item.work_seconds,
                        rest_seconds=item.rest_seconds,
                    )
                    for item in revised
                ),
                estimated_duration_seconds=estimated,
                policy_version=PLAN_REVISION_POLICY_VERSION,
                now=self._clock(),
            )
            stored = self._repository.get_response(session, user_id, decision_id)
            if stored is None or stored.get("final_plan") is None:
                raise PlanNotFoundError
            response = PlanRevisionResponse(
                decision_id=decision_id,
                plan_revision=revision,
                final_plan=DecisionPlan.model_validate(stored["final_plan"]),
            )
            self._repository.save_endpoint_idempotency(
                session,
                user_id=user_id,
                endpoint_code=endpoint_code,
                key=idempotency_key,
                request_hash=request_hash,
                payload=response.model_dump(mode="json"),
                now=self._clock(),
            )
        return response


__all__ = [
    "PLAN_ITEM_ENDPOINT_CODE",
    "PLAN_ITEM_ORDER_ENDPOINT_CODE",
    "PlanNotFoundError",
    "PlanRevisionIdempotencyKeyReusedError",
    "PlanRevisionService",
    "PlanRevisionStaleError",
]
