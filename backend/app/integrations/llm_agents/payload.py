"""Explicit, privacy-minimized projections of the approved V3 domain contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import CoordinatorInput, SpecialistAgentInput
from backend.app.domain.rules.safety import BodyAreaCode

_MACHINE_VALUE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_FORBIDDEN_FIELD_NAMES: Final = frozenset(
    {
        "user_id",
        "email",
        "name",
        "birthdate",
        "date",
        "created_at",
        "check_in_text",
        "checkin_text",
        "free_text",
        "pain",
        "pain_area",
        "pain_body_area",
        "pain_intensity",
        "pain_severity",
        "severity",
        "intensity_score",
        "health",
        "health_data",
        "raw_health",
        "wearable",
        "wearable_data",
        "raw_wearable",
        "calendar",
        "calendar_data",
        "calendar_text",
        "raw_calendar",
        "retrieval_metadata",
        "similarity_score",
        "similarity_scores",
        "vector_ranked_exercise_ids",
    }
)
_SENSITIVE_MACHINE_VALUE_FRAGMENTS: Final = (
    "CALENDAR_TEXT",
    "CHECK_IN",
    "DISCOMFORT",
    "EMAIL",
    "HEALTH",
    "INTENSITY_SCORE",
    "PAIN",
    "SEVERITY",
    "USER_ID",
    "WEARABLE",
)
_BODY_AREA_CODES: Final = frozenset(
    code.value
    for code in BodyAreaCode
    if code not in {BodyAreaCode.GENERALIZED, BodyAreaCode.OTHER}
)

_CONSTRAINT_ENVELOPE_FIELDS: Final = (
    "schema_version",
    "requested_duration_minutes",
    "primary_goal_code",
    "allowed_location_codes",
    "allowed_equipment_codes",
    "excluded_exercise_ids",
    "mandatory_exercise_ids",
    "recovery_ceiling",
    "plan_generation_allowed",
    "safety_required_action_code",
    "policy_version",
    "catalog_version",
    "safety_rule_version",
    "envelope_hash",
)
_REGENERATION_CONTEXT_FIELDS: Final = (
    "schema_version",
    "generation_sequence",
    "previous_plan_hash",
    "previous_exercise_ids",
    "variation_codes",
    "exact_duplicate_forbidden",
)
_SPECIALIST_PROPOSAL_FIELDS: Final = (
    "schema_version",
    "agent_type_code",
    "proposal_status_code",
    "envelope_hash",
    "pool_hash",
    "requested_duration_minutes",
    "estimated_duration_seconds",
    "exercise_prescriptions",
    "adjustment_codes",
    "hard_constraint_codes",
    "reason_codes",
    "evidence_reference_codes",
    "public_summary_code",
    "proposal_hash",
)
_POOL_EXERCISE_FIELDS: Final = (
    "exercise_id",
    "stable_code",
    "training_type_code",
    "body_focus_code",
    "movement_pattern_codes",
    "difficulty_code",
    "timing_mode_code",
    "recovery_eligible",
    "goal_codes",
    "equipment_codes",
    "location_codes",
    "prescription_reference_codes",
)


def _validate_private_machine_payload(value: object, *, path: str = "input") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            if key.lower() in _FORBIDDEN_FIELD_NAMES:
                raise ValueError("payload contains a forbidden field")
            _validate_private_machine_payload(nested, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _validate_private_machine_payload(nested, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        if not _MACHINE_VALUE_PATTERN.fullmatch(value):
            raise ValueError(f"{path} must contain a structured machine value")
        normalized = value.upper()
        if any(fragment in normalized for fragment in _SENSITIVE_MACHINE_VALUE_FRAGMENTS):
            raise ValueError(f"{path} contains a sensitive machine value")
        is_catalog_body_focus = ".exercise_pool.exercises[" in path and path.endswith(
            ".body_focus_code"
        )
        if normalized in _BODY_AREA_CODES and not is_catalog_body_focus:
            raise ValueError(f"{path} contains a health body-area value")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{path} contains an unsupported payload value")


def assert_private_machine_payload(payload: Mapping[str, object]) -> None:
    """Reject direct identifiers, raw health context, and unstructured strings."""

    _validate_private_machine_payload(payload)


def project_contract(
    contract: BaseModel,
    *,
    field_allowlist: Sequence[str],
) -> dict[str, object]:
    """Project an approved domain contract with an explicit field allowlist."""

    if not field_allowlist:
        raise ValueError("contract projection requires a non-empty field allowlist")
    fields = type(contract).model_fields
    if any(field not in fields for field in field_allowlist):
        raise ValueError("contract projection references an unknown field")
    projected = contract.model_dump(
        mode="json",
        include=set(field_allowlist),
        exclude_none=True,
    )
    assert_private_machine_payload(projected)
    return projected


def project_exercise_pool(pool: ExercisePoolSnapshot) -> dict[str, object]:
    """Exclude timestamps, vector ranking, similarity lineage, and source metadata."""

    exercise_rows = [
        project_contract(exercise, field_allowlist=_POOL_EXERCISE_FIELDS)
        for exercise in pool.exercises
    ]
    exercise_ids = [str(exercise.exercise_id) for exercise in pool.exercises]
    projected: dict[str, object] = {
        "schema_version": pool.schema_version,
        "catalog_version": pool.catalog_version,
        "constraint_envelope_hash": pool.constraint_envelope_hash,
        "pool_hash": pool.pool_hash,
        "exercise_id_allowlist": exercise_ids,
        "mandatory_exercise_ids": [str(value) for value in pool.mandatory_exercise_ids],
        "exercises": exercise_rows,
    }
    assert_private_machine_payload(projected)
    return projected


def specialist_payload(agent_input: SpecialistAgentInput) -> dict[str, object]:
    projected: dict[str, object] = {
        "schema_version": agent_input.schema_version,
        "agent_type_code": agent_input.agent_type_code.value,
        "envelope_hash": agent_input.envelope_hash,
        "pool_hash": agent_input.pool_hash,
        "constraint_envelope": project_contract(
            agent_input.constraint_envelope,
            field_allowlist=_CONSTRAINT_ENVELOPE_FIELDS,
        ),
        "exercise_pool": project_exercise_pool(agent_input.exercise_pool),
    }
    if agent_input.regeneration_context is not None:
        projected["regeneration_context"] = project_contract(
            agent_input.regeneration_context,
            field_allowlist=_REGENERATION_CONTEXT_FIELDS,
        )
    assert_private_machine_payload(projected)
    return projected


def coordinator_payload(coordinator_input: CoordinatorInput) -> dict[str, object]:
    projected: dict[str, object] = {
        "schema_version": coordinator_input.schema_version,
        "mode_code": "REPAIR" if coordinator_input.repair_attempt == 1 else "INITIAL",
        "repair_attempt": coordinator_input.repair_attempt,
        "repair_violation_codes": list(coordinator_input.repair_violation_codes),
        "constraint_envelope": project_contract(
            coordinator_input.constraint_envelope,
            field_allowlist=_CONSTRAINT_ENVELOPE_FIELDS,
        ),
        "exercise_pool": project_exercise_pool(coordinator_input.exercise_pool),
        "specialist_proposals": [
            project_contract(proposal, field_allowlist=_SPECIALIST_PROPOSAL_FIELDS)
            for proposal in coordinator_input.proposals
        ],
    }
    assert_private_machine_payload(projected)
    return projected


__all__ = [
    "assert_private_machine_payload",
    "coordinator_payload",
    "project_contract",
    "project_exercise_pool",
    "specialist_payload",
]
