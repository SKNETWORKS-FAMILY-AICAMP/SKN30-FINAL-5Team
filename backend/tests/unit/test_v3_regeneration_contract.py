from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.v3_orchestration import RegenerationDifferenceCode
from backend.app.modules.decisions.v3_regeneration import (
    V3DecisionEngineCode,
    V3DecisionNotFoundError,
    V3EngineDisabledError,
    V3IdempotencyKeyReusedError,
    V3NoAlternativeAvailableError,
    V3RegenerationCommand,
    V3RegenerationContextStaleError,
    V3RegenerationDecisionFailedError,
    V3RegenerationFailureCode,
    V3RegenerationLimitReachedError,
    V3RegenerationNotAllowedError,
    V3RegenerationResult,
    V3StaleRegenerationError,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ROOT_ID = UUID("00000000-0000-0000-0000-000000000002")
FIRST_ID = UUID("00000000-0000-0000-0000-000000000003")
SECOND_ID = UUID("00000000-0000-0000-0000-000000000004")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000005")
KEY_ID = UUID("00000000-0000-0000-0000-000000000006")


def test_regeneration_command_is_strict_frozen_and_transport_independent() -> None:
    command = V3RegenerationCommand(
        user_id=USER_ID,
        decision_id=ROOT_ID,
        idempotency_key=KEY_ID,
        expected_plan_id=PLAN_ID,
        expected_regeneration_sequence=0,
    )

    assert command.expected_regeneration_sequence == 0
    assert "different" not in V3RegenerationCommand.model_fields
    with pytest.raises(ValidationError):
        V3RegenerationCommand.model_validate(
            {**command.model_dump(), "expected_regeneration_sequence": 2}
        )
    with pytest.raises(ValidationError):
        V3RegenerationCommand.model_validate({**command.model_dump(), "reason": "different"})
    with pytest.raises(ValidationError):
        command.expected_regeneration_sequence = 1  # type: ignore[misc]


def test_first_regeneration_result_requires_root_as_parent() -> None:
    result = V3RegenerationResult(
        decision_id=FIRST_ID,
        root_decision_id=ROOT_ID,
        parent_decision_id=ROOT_ID,
        regeneration_sequence=1,
        decision_engine_code=V3DecisionEngineCode.LLM_MULTI_AGENT,
        meaningful_difference_codes=(RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,),
    )

    assert result.generation_mode_code == "REGENERATED"
    with pytest.raises(ValidationError, match="first regeneration parent"):
        V3RegenerationResult.model_validate(
            {**result.model_dump(), "parent_decision_id": SECOND_ID}
        )


def test_second_regeneration_result_requires_first_regeneration_as_parent() -> None:
    result = V3RegenerationResult(
        decision_id=SECOND_ID,
        root_decision_id=ROOT_ID,
        parent_decision_id=FIRST_ID,
        regeneration_sequence=2,
        decision_engine_code=V3DecisionEngineCode.DETERMINISTIC_FALLBACK,
        meaningful_difference_codes=(
            RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
            RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
        ),
    )

    assert result.parent_decision_id == FIRST_ID
    with pytest.raises(ValidationError, match="second regeneration parent"):
        V3RegenerationResult.model_validate({**result.model_dump(), "parent_decision_id": ROOT_ID})


@pytest.mark.parametrize(
    "codes",
    [
        (RegenerationDifferenceCode.EXACT_DUPLICATE,),
        (RegenerationDifferenceCode.NO_MEANINGFUL_DIFFERENCE,),
        (
            RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
            RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
        ),
        (
            RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
            RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
        ),
    ],
)
def test_success_result_rejects_non_meaningful_or_noncanonical_codes(
    codes: tuple[RegenerationDifferenceCode, ...],
) -> None:
    with pytest.raises(ValidationError, match="unique and canonical"):
        V3RegenerationResult(
            decision_id=FIRST_ID,
            root_decision_id=ROOT_ID,
            parent_decision_id=ROOT_ID,
            regeneration_sequence=1,
            decision_engine_code=V3DecisionEngineCode.LLM_MULTI_AGENT,
            meaningful_difference_codes=codes,
        )


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (V3DecisionNotFoundError, V3RegenerationFailureCode.DECISION_NOT_FOUND),
        (V3IdempotencyKeyReusedError, V3RegenerationFailureCode.IDEMPOTENCY_KEY_REUSED),
        (V3StaleRegenerationError, V3RegenerationFailureCode.STALE_REGENERATION),
        (
            V3RegenerationContextStaleError,
            V3RegenerationFailureCode.REGENERATION_CONTEXT_STALE,
        ),
        (
            V3RegenerationLimitReachedError,
            V3RegenerationFailureCode.REGENERATION_LIMIT_REACHED,
        ),
        (
            V3RegenerationNotAllowedError,
            V3RegenerationFailureCode.REGENERATION_NOT_ALLOWED,
        ),
        (
            V3NoAlternativeAvailableError,
            V3RegenerationFailureCode.NO_ALTERNATIVE_AVAILABLE,
        ),
        (V3RegenerationDecisionFailedError, V3RegenerationFailureCode.DECISION_FAILED),
        (V3EngineDisabledError, V3RegenerationFailureCode.V3_ENGINE_DISABLED),
    ],
)
def test_regeneration_errors_expose_stable_machine_codes(
    error_type: type[RuntimeError], code: V3RegenerationFailureCode
) -> None:
    error = error_type()

    assert error.code is code
    assert str(error) == code.value
