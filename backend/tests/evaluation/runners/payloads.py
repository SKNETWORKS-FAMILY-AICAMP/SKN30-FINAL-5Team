"""Build the answer body the scripted model returns for one role and script.

The builder works from the serialized payload the adapter sent, plus the case's
own envelope and pool.  It never reaches into graph state: a provider sees a
JSON request and answers with a JSON body, and so does this.

Every deliberately broken script here breaks exactly one rule.  A payload that
violated two would leave a test unable to say which gate caught it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ConstraintEnvelope,
    ExercisePrescription,
    SpecialistAgentTypeCode,
)
from backend.app.domain.rules.duration import SECONDS_PER_MINUTE
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.tests.evaluation.planner import (
    compose_prescriptions,
    prescriptions_duration_seconds,
    resequence,
)
from backend.tests.evaluation.runners.fake_chat import ModelRequest, ScriptCode

_UNKNOWN_EXERCISE_ID = uuid5(UUID("6f1d5f2e-0f4c-4a2b-9c3d-8e7a1b2c3d4e"), "NOT_IN_ANY_POOL")

_ROLE_TO_AGENT_TYPE = {
    LlmAgentRoleCode.TRAINING: SpecialistAgentTypeCode.TRAINING,
    LlmAgentRoleCode.RECOVERY: SpecialistAgentTypeCode.RECOVERY,
    LlmAgentRoleCode.FEASIBILITY: SpecialistAgentTypeCode.FEASIBILITY,
}

_ADJUSTMENT_CODES = {
    LlmAgentRoleCode.RECOVERY: ("RECOVERY_KEEP_INTENSITY_LOW", "RECOVERY_LENGTHEN_REST"),
    LlmAgentRoleCode.FEASIBILITY: ("FEASIBILITY_DURATION_ACHIEVABLE", "FEASIBILITY_HOME_ONLY"),
}


def _prescription_payload(item: ExercisePrescription) -> dict[str, Any]:
    body = item.model_dump(mode="json")
    return body


@dataclass(frozen=True, slots=True)
class PayloadBuilder:
    """Answer as the model would, for one case's envelope and pool."""

    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot
    action_code: str = "KEEP"
    """`PlanActionCode`. A downshift case sets DOWNSHIFT; the default keeps the routine."""

    def build(self, request: ModelRequest, script_code: ScriptCode) -> dict[str, object]:
        if request.role_code is LlmAgentRoleCode.COORDINATOR:
            return self._coordinator(request, script_code)
        return self._specialist(request, script_code)

    # -- specialists ----------------------------------------------------

    def _specialist(self, request: ModelRequest, script_code: ScriptCode) -> dict[str, object]:
        role = request.role_code
        agent_type = _ROLE_TO_AGENT_TYPE[role]
        base: dict[str, object] = {
            "schema_version": "specialist-agent-proposal-v1",
            "agent_type_code": agent_type.value,
            "proposal_status_code": "READY",
            "envelope_hash": self.envelope.envelope_hash,
            "pool_hash": self.pool.pool_hash,
            "requested_duration_minutes": self.envelope.requested_duration_minutes,
            "exercise_prescriptions": [],
            "adjustment_codes": [],
            "hard_constraint_codes": [],
            "reason_codes": ["EVAL_SCRIPTED_PROPOSAL"],
            "evidence_reference_codes": ["eval-review-v1"],
            "public_summary_code": "EVAL_SUMMARY",
        }

        if script_code is ScriptCode.SCHEMA_INVALID:
            # A status the enum does not define. The output schema rejects it,
            # which is the SCHEMA_INVALID path the adapter reports.
            base["proposal_status_code"] = "DEFINITELY_NOT_A_STATUS"
            return base
        if script_code is ScriptCode.NOT_READY:
            base["proposal_status_code"] = "NEEDS_INPUT"
            base["exercise_prescriptions"] = []
            return base

        if agent_type is SpecialistAgentTypeCode.TRAINING:
            base["exercise_prescriptions"] = self._training_prescriptions(script_code)
            return base

        base["adjustment_codes"] = sorted(_ADJUSTMENT_CODES[role])
        if script_code is ScriptCode.ROLE_VIOLATING:
            # ADR-0015: only TRAINING owns a plan. The contract must refuse this.
            base["exercise_prescriptions"] = self._training_prescriptions(ScriptCode.COMPLIANT)
        return base

    def _training_prescriptions(self, script_code: ScriptCode) -> list[dict[str, Any]]:
        compliant = compose_prescriptions(self.envelope, self.pool)

        if script_code is ScriptCode.SAFETY_VIOLATING:
            return [_prescription_payload(item) for item in self._with_excluded(compliant)]
        if script_code is ScriptCode.POOL_ESCAPE:
            escaped = compliant[:-1] + (
                compliant[-1].model_copy(update={"exercise_id": _UNKNOWN_EXERCISE_ID}),
            )
            return [_prescription_payload(item) for item in escaped]
        if script_code is ScriptCode.DURATION_VIOLATING:
            return [_prescription_payload(item) for item in self._overlong(compliant)]
        if script_code is ScriptCode.PHASE_MISSING:
            main_only = resequence(tuple(item for item in compliant if item.phase_code == "MAIN"))
            return [_prescription_payload(item) for item in main_only]
        return [_prescription_payload(item) for item in compliant]

    def _with_excluded(
        self, compliant: tuple[ExercisePrescription, ...]
    ) -> tuple[ExercisePrescription, ...]:
        """Swap one main block for an exercise Safety excluded.

        With no exclusion in the envelope there is nothing to violate, so the
        compliant plan is returned unchanged and the case's own expectation
        decides whether that is a pass.
        """

        excluded = self.envelope.excluded_exercise_ids
        if not excluded:
            return compliant
        target = excluded[0]
        swapped: list[ExercisePrescription] = []
        replaced = False
        for item in compliant:
            if not replaced and item.phase_code == "MAIN":
                swapped.append(item.model_copy(update={"exercise_id": target}))
                replaced = True
                continue
            swapped.append(item)
        return tuple(swapped)

    def _overlong(
        self, compliant: tuple[ExercisePrescription, ...]
    ) -> tuple[ExercisePrescription, ...]:
        """Repeat main work until the plan is well past the requested duration."""

        main = [item for item in compliant if item.phase_code == "MAIN"]
        if not main:
            return compliant
        target = self.envelope.requested_duration_minutes * SECONDS_PER_MINUTE
        blocks = list(compliant)
        # Alternate the two longest main blocks so the overrun is duration, not
        # a neighbouring repeat, which is a different violation.
        rotation = main if len(main) > 1 else main * 2
        index = 0
        while prescriptions_duration_seconds(tuple(blocks), self.pool) <= target * 3:
            source = rotation[index % len(rotation)]
            index += 1
            insert_at = len(blocks) - sum(1 for item in blocks if item.phase_code == "COOLDOWN")
            blocks.insert(insert_at, source.model_copy())
            if index > 60:
                break
        return resequence(tuple(blocks))

    # -- coordinator ----------------------------------------------------

    def _coordinator(self, request: ModelRequest, script_code: ScriptCode) -> dict[str, object]:
        proposals = request.payload["specialist_proposals"]
        by_role = {item["agent_type_code"]: item for item in proposals}
        training = by_role[SpecialistAgentTypeCode.TRAINING.value]

        if script_code is ScriptCode.COMPLIANT:
            prescriptions = [dict(item) for item in training["exercise_prescriptions"]]
        else:
            prescriptions = self._training_prescriptions(script_code)

        # The contracts are strict, so a JSON-shaped body has to re-enter them
        # through JSON mode, exactly as `StructuredChatInvoker` does.
        estimated = prescriptions_duration_seconds(
            tuple(
                ExercisePrescription.model_validate_json(json.dumps(item)) for item in prescriptions
            ),
            self.pool,
        )
        payload: dict[str, object] = {
            "schema_version": "plan-spec-v1",
            "envelope_hash": self.envelope.envelope_hash,
            "pool_hash": self.pool.pool_hash,
            "action_code": self.action_code,
            "requested_duration_minutes": self.envelope.requested_duration_minutes,
            "estimated_duration_seconds": estimated,
            "exercise_prescriptions": prescriptions,
            "proposal_references": [
                {
                    "agent_type_code": agent_type.value,
                    "proposal_hash": by_role[agent_type.value]["proposal_hash"],
                }
                for agent_type in SPECIALIST_AGENT_ORDER
            ],
            "repair_attempt": int(request.payload["repair_attempt"]),
            "decision_codes": ["EVAL_SCRIPTED_COORDINATION"],
            "public_summary_code": "EVAL_SUMMARY",
        }
        if script_code is ScriptCode.SCHEMA_INVALID:
            payload["action_code"] = "DEFINITELY_NOT_AN_ACTION"
        return payload


@dataclass(frozen=True, slots=True)
class SingleAgentPayloadBuilder:
    """Answer as a PHASE 6 baseline would, for one case's envelope and pool.

    The scripts are the same ones the multi-agent builder uses, so an offline
    comparison exercises both architectures against identical faults. Only the
    envelope of the answer differs: a baseline returns the plan draft directly
    rather than a proposal and then a coordinated plan.
    """

    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot
    action_code: str = "KEEP"

    def build(self, request: ModelRequest, script_code: ScriptCode) -> dict[str, object]:
        del request
        inner = PayloadBuilder(envelope=self.envelope, pool=self.pool, action_code=self.action_code)
        prescriptions = inner._training_prescriptions(script_code)
        estimated = prescriptions_duration_seconds(
            tuple(
                ExercisePrescription.model_validate_json(json.dumps(item)) for item in prescriptions
            ),
            self.pool,
        )
        payload: dict[str, object] = {
            "envelope_hash": self.envelope.envelope_hash,
            "pool_hash": self.pool.pool_hash,
            "action_code": self.action_code,
            "requested_duration_minutes": self.envelope.requested_duration_minutes,
            "estimated_duration_seconds": estimated,
            "exercise_prescriptions": prescriptions,
            "decision_codes": ["EVAL_SCRIPTED_SINGLE_AGENT"],
            "public_summary_code": "EVAL_SUMMARY",
        }
        if script_code is ScriptCode.SCHEMA_INVALID:
            payload["action_code"] = "DEFINITELY_NOT_AN_ACTION"
        if script_code is ScriptCode.NOT_READY:
            # A baseline has no status field to refuse with, so the only shape of
            # "I cannot answer" available to it is an empty plan.
            payload["exercise_prescriptions"] = []
        return payload


__all__ = ["PayloadBuilder", "SingleAgentPayloadBuilder"]
