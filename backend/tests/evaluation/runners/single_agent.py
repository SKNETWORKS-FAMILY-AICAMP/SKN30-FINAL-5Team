"""PHASE 6 baselines: one agent doing in one call what the graph does in four.

The experiment is only worth running if the baseline is allowed to win.  Three
properties hold that open, and each one is enforced by construction here rather
than promised in a document:

1. **The same instructions.** `SINGLE_AGENT_INSTRUCTION` is assembled from the
   four shipped `ROLE_PROMPTS` texts, not written fresh.  Every planning rule the
   multi-agent path states -- phase coverage, the ten-exercise ceiling, FITT
   bounds, the five-minute duration window, the recovery ceiling, the pool
   allowlist -- reaches the single agent in the words the service already uses.
   The only sentences dropped are the role-separation ones ("you do not own an
   exercise plan", "coordinate exactly the three supplied proposals"), which
   describe a division of labour that does not exist here; `_DROPPED_CLAUSES`
   records them so a reviewer can check nothing substantive went with them.

2. **The same gate.** The draft is assembled into a real `PlanSpec`, checked by
   the real `PlanSpec.validate_against`, compiled by the real `compile_plan`, and
   judged by the real `validate_plan_integrity`.  Nothing downstream of the model
   is re-implemented, so a baseline plan is accepted on exactly the terms a
   coordinator plan is.

3. **The same provider boundary.** `StructuredChatInvoker` is the service's own,
   so temperature, the approved-model gate, native JSON-schema binding, the
   single bounded retry and the token audit are identical.

**What differs, and what that means.**

`SINGLE_LLM` (architecture A) and `SINGLE_AGENT_RAG` (architecture B) run the
same prompt and the same schema; they differ only in how much of the retrieved
pool the payload carries.  A gets the four fields the *output schema* cannot be
filled without -- the id, the stable code, whether the movement is measured in
reps or seconds, and where it may be performed.  B additionally gets everything
retrieval contributes: phases, role eligibility, FITT ranges, the timing basis,
goal codes, equipment.  That line is the measurement: A minus B is the value of
retrieval, B minus C is the value of the multi-agent decomposition.

**The proposal synthesis is a contract adapter, not a simulated agent.**
`PlanSpec` structurally requires three proposal references in canonical role
order, so a single-agent plan cannot enter the shipped compiler without them.
`synthesize_proposals` therefore wraps the agent's *own* prescriptions as the
TRAINING proposal and emits Recovery and Feasibility proposals carrying
`SINGLE_AGENT_NO_SPECIALIST_ADVICE` and nothing else.  No advice is invented; the
wrapper adds no information and makes no decision.  That `PlanSpec` cannot be
built without this is itself a PHASE 6 finding: the shipped output contract is
not architecture-neutral.

**No repair round.** The graph gives the coordinator one repair call; this path
has none, which favours the multi-agent side.  The asymmetry is recorded rather
than corrected because it had no measured effect: every one of the fourteen paid
multi-agent runs finished with `repair_attempts == 0`.  The deterministic
fallback *is* given to both, because it belongs to the service rather than to
either architecture, and `used_fallback` separates the two readings.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import CompiledPlan, DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    CoordinatorInput,
    ExercisePrescription,
    PlanActionCode,
    PlanSpec,
    ProposalReference,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    TrainingPlanFeasibilityCode,
    V3ProposalStatusCode,
)
from backend.app.domain.agents.v3_orchestration import FallbackRequest
from backend.app.integrations.langgraph.demo_runtime import V3DemoRuntimeVersions
from backend.app.integrations.langgraph.fallback import (
    DETERMINISTIC_FALLBACK_VERSION,
    DeterministicGraphFallbackProvider,
)
from backend.app.integrations.langgraph.shadow_runtime import (
    _Compiler,
    _ExecutionContext,
    _Fallback,
    _IntegrityValidator,
)
from backend.app.integrations.langgraph.state import (
    IntegrityValidation,
    InvocationAudit,
    V3GraphResult,
)
from backend.app.integrations.llm_agents.canonicalization import canonical_plan_values
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.payload import (
    _CONSTRAINT_ENVELOPE_FIELDS,
    assert_private_machine_payload,
    project_contract,
    project_exercise_pool,
)
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS, RolePrompt, messages_for
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.architectures import (
    ARCHITECTURE_SINGLE_AGENT_RAG,
    ARCHITECTURE_SINGLE_LLM,
)
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.runners.fake_chat import InvocationLog, Script
from backend.tests.evaluation.runners.openai_provider import ProviderContext
from backend.tests.evaluation.runners.run_multi_agent import EVAL_MODEL_CODE, CaseRunResult
from backend.tests.evaluation.scenario import Scenario, build_scenario

SINGLE_LLM_PROMPT_VERSION: Final = "eval-single-llm-prompt-v1"
SINGLE_AGENT_RAG_PROMPT_VERSION: Final = "eval-single-agent-rag-prompt-v1"

SINGLE_AGENT_DRAFT_SCHEMA_VERSION: Final = "eval-single-agent-plan-draft-v1"

# The advisory slots a single agent structurally cannot fill. Stated as one
# explicit code rather than left empty, because a READY specialist proposal that
# owns no plan must carry at least one adjustment code.
NO_SPECIALIST_ADVICE_CODE: Final = "SINGLE_AGENT_NO_SPECIALIST_ADVICE"

# Fields a plan cannot legally reference without: the id names the exercise, the
# stable code makes it recognisable, the timing mode decides whether repetitions
# are required at all, and the location codes decide which location is even
# permitted. Architecture A gets these and no more.
_SCHEMA_MINIMUM_POOL_FIELDS: Final[tuple[str, ...]] = (
    "exercise_id",
    "stable_code",
    "timing_mode_code",
    "location_codes",
)

# Sentences removed from the shipped role prompts when composing the single-agent
# instruction, with the reason each one cannot apply. Kept as data so a reviewer
# can confirm that only role-separation text was dropped, never a planning rule.
_DROPPED_CLAUSES: Final[tuple[tuple[str, str], ...]] = (
    (
        "You do not own an exercise plan: always leave exercise_prescriptions empty",
        "RECOVERY/FEASIBILITY role separation; a single agent owns the whole plan",
    ),
    (
        "Coordinate exactly the three supplied specialist proposals into one PlanSpec",
        "COORDINATOR; there are no separate proposals to coordinate",
    ),
    (
        "Use Training's exercise_prescriptions as the sole draft plan",
        "COORDINATOR; the draft and the final plan are the same answer here",
    ),
    (
        "A repair request is evidence for this single call",
        "COORDINATOR; this path has no repair round",
    ),
)


def _single_agent_instruction() -> str:
    """Compose one instruction from the four shipped role prompts.

    Built at import time from `ROLE_PROMPTS` rather than copied, so a change to a
    production prompt reaches the baseline too and the two cannot drift apart.
    """

    training = ROLE_PROMPTS[LlmAgentRoleCode.TRAINING].instruction
    return (
        "You are the single agent responsible for the whole exercise plan. "
        "Carry out the training, recovery, feasibility and coordination "
        "judgements yourself, in this one answer.\n\n"
        f"{training}\n\n"
        "Recovery perspective: apply recovery-oriented judgement inside the "
        "already approved constraint envelope. The deterministic recovery "
        "ceiling and the final integrity validation still bound you and are not "
        "replaced by your own judgement.\n\n"
        "Feasibility perspective: judge duration, equipment and location "
        "feasibility inside the already approved constraint envelope. Equipment "
        "is not a selection condition.\n\n"
        "Coordination: reconcile those perspectives into one plan without a "
        "fixed precedence between them. Do not weaken safety, duration, goal, "
        "location, or recovery constraints. The compiled plan is accepted only "
        "after deterministic integrity validation."
    )


SINGLE_AGENT_INSTRUCTION: Final = _single_agent_instruction()


class SingleAgentPlanDraft(BaseModel):
    """`PlanSpec` minus the two fields only a multi-agent run can supply.

    `proposal_references` and `repair_attempt` describe an orchestration this
    architecture does not have. Every other field, constraint and type is the
    coordinator's, so the JSON schema the provider is bound to is the same
    schema up to those two keys.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    envelope_hash: str
    pool_hash: str
    action_code: PlanActionCode
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int = Field(gt=0)
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    decision_codes: tuple[str, ...] = Field(min_length=1)
    public_summary_code: str | None = None

    @classmethod
    def create(cls, **values: object) -> SingleAgentPlanDraft:
        payload: dict[str, object] = {"public_summary_code": None, **values}
        return cls.model_validate(payload)


def single_agent_payload(
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    with_retrieved_detail: bool,
    fallback_version: str = DETERMINISTIC_FALLBACK_VERSION,
) -> dict[str, object]:
    """Project the case for a single agent, at one of two retrieval depths.

    `with_retrieved_detail` is the whole difference between architectures A and
    B. Both projections go through the service's own privacy allowlist, so
    neither can see more of the user than a shipped agent does.
    """

    if with_retrieved_detail:
        projected_pool = project_exercise_pool(pool)
    else:
        projected_pool = {
            "schema_version": pool.schema_version,
            "catalog_version": pool.catalog_version,
            "constraint_envelope_hash": pool.constraint_envelope_hash,
            "pool_hash": pool.pool_hash,
            "exercise_id_allowlist": [str(item.exercise_id) for item in pool.exercises],
            "mandatory_exercise_ids": [str(value) for value in pool.mandatory_exercise_ids],
            "exercises": [
                project_contract(exercise, field_allowlist=_SCHEMA_MINIMUM_POOL_FIELDS)
                for exercise in pool.exercises
            ],
        }
    fallback_provider = DeterministicGraphFallbackProvider(fallback_version=fallback_version)
    candidate = fallback_provider.generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=fallback_version,
        )
    )
    feasibility_code = (
        TrainingPlanFeasibilityCode.CANDIDATE_AVAILABLE
        if candidate is not None
        else TrainingPlanFeasibilityCode.UNPROVEN
    )
    projected: dict[str, object] = {
        "schema_version": SINGLE_AGENT_DRAFT_SCHEMA_VERSION,
        "mode_code": "INITIAL",
        "training_plan_feasibility_code": feasibility_code.value,
        "constraint_envelope": project_contract(
            envelope, field_allowlist=_CONSTRAINT_ENVELOPE_FIELDS
        ),
        "exercise_pool": projected_pool,
    }
    # The same closing guard `specialist_payload` applies to its own body.
    assert_private_machine_payload(projected)
    return projected


def synthesize_proposals(
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    prescriptions: tuple[ExercisePrescription, ...],
) -> tuple[SpecialistAgentProposal, ...]:
    """Wrap one agent's answer in the three-proposal shape the contract demands.

    This invents no advice. TRAINING carries the agent's own prescriptions
    unchanged; the advisory roles carry a single code that says, literally, that
    no specialist advice exists. The reason this function has to exist at all is
    recorded in the module docstring.
    """

    shared: dict[str, object] = {
        "envelope_hash": envelope.envelope_hash,
        "pool_hash": pool.pool_hash,
        "requested_duration_minutes": envelope.requested_duration_minutes,
        "proposal_status_code": V3ProposalStatusCode.READY,
        "reason_codes": ("SINGLE_AGENT_CONTRACT_ADAPTER",),
    }
    training = SpecialistAgentProposal.create(
        agent_type_code=SpecialistAgentTypeCode.TRAINING,
        exercise_prescriptions=prescriptions,
        **shared,
    )
    advisory = tuple(
        SpecialistAgentProposal.create(
            agent_type_code=agent_type,
            adjustment_codes=(NO_SPECIALIST_ADVICE_CODE,),
            **shared,
        )
        for agent_type in (SpecialistAgentTypeCode.RECOVERY, SpecialistAgentTypeCode.FEASIBILITY)
    )
    return (training, *advisory)


def assemble_plan_spec(
    draft: SingleAgentPlanDraft,
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
) -> tuple[PlanSpec, CoordinatorInput, tuple[SpecialistAgentProposal, ...]]:
    """Turn a draft into the exact objects the shipped compiler consumes.

    Raises whatever the domain contracts raise. That is deliberate: the caller
    uses this as the invoker's domain validator, so a draft that breaks a
    constraint fails in the same place, with the same code, as a coordinator
    plan that breaks it.
    """

    proposals = synthesize_proposals(
        envelope=envelope, pool=pool, prescriptions=draft.exercise_prescriptions
    )
    coordinator_input = CoordinatorInput(
        constraint_envelope=envelope,
        exercise_pool=pool,
        proposals=proposals,
        repair_attempt=0,
        repair_violation_codes=(),
    )
    plan_spec = PlanSpec.create(
        envelope_hash=draft.envelope_hash,
        pool_hash=draft.pool_hash,
        action_code=draft.action_code,
        requested_duration_minutes=draft.requested_duration_minutes,
        estimated_duration_seconds=draft.estimated_duration_seconds,
        exercise_prescriptions=draft.exercise_prescriptions,
        proposal_references=tuple(
            ProposalReference(
                agent_type_code=proposal.agent_type_code,
                proposal_hash=proposal.proposal_hash,
            )
            for proposal in proposals
        ),
        repair_attempt=0,
        decision_codes=draft.decision_codes,
        public_summary_code=draft.public_summary_code,
    )
    plan_spec.validate_against(coordinator_input)
    return plan_spec, coordinator_input, proposals


@dataclass(slots=True)
class _Validation:
    """The `IntegrityValidation` protocol, recorded for the result object.

    Mutable because the protocol declares plain attributes, which a frozen
    dataclass cannot satisfy.
    """

    passed: bool
    repairable: bool
    violation_codes: tuple[str, ...]


@dataclass(slots=True)
class SingleAgentRunner:
    """Run one case through one LLM call and the shipped downstream gate."""

    architecture_code: str = ARCHITECTURE_SINGLE_AGENT_RAG
    versions: V3DemoRuntimeVersions = field(default_factory=V3DemoRuntimeVersions)
    provider: ProviderContext | None = None
    chat_model: object | None = None
    """Offline stand-in. Ignored when `provider` is set."""

    model_code: str = EVAL_MODEL_CODE

    @property
    def with_retrieved_detail(self) -> bool:
        return self.architecture_code == ARCHITECTURE_SINGLE_AGENT_RAG

    @property
    def prompt_version(self) -> str:
        return (
            SINGLE_AGENT_RAG_PROMPT_VERSION
            if self.with_retrieved_detail
            else SINGLE_LLM_PROMPT_VERSION
        )

    @property
    def model_label(self) -> str:
        return self.provider.label if self.provider is not None else self.model_code

    def _invoker(self) -> StructuredChatInvoker:
        if self.provider is not None:
            return StructuredChatInvoker(
                chat_model=cast(Any, self.provider.chat_model),
                model_code=self.provider.model_code,
                max_attempts=self.provider.max_attempts,
                # Production binds the provider's native JSON-schema mode; a paid
                # baseline has to bind it the same way or the two architectures
                # are not using the same structured-output path.
                use_native_json_schema=True,
                tracing_enabled=self.provider.tracing_enabled,
            )
        return StructuredChatInvoker(
            chat_model=cast(Any, self.chat_model),
            model_code=self.model_code,
            max_attempts=1,
            use_native_json_schema=False,
        )

    async def run(self, case: EvaluationCase, script: Script | None = None) -> CaseRunResult:
        return await self.run_scenario(build_scenario(case), script or Script())

    async def run_scenario(self, scenario: Scenario, script: Script) -> CaseRunResult:
        envelope = scenario.constraint_envelope
        pool = scenario.exercise_pool
        started_ns = time.monotonic_ns()

        prompt = RolePrompt(
            role_code=LlmAgentRoleCode.COORDINATOR,
            version=self.prompt_version,
            instruction=SINGLE_AGENT_INSTRUCTION,
        )
        payload = single_agent_payload(
            envelope=envelope,
            pool=pool,
            with_retrieved_detail=self.with_retrieved_detail,
            fallback_version=self.versions.fallback_version,
        )

        def validate(output: SingleAgentPlanDraft) -> SingleAgentPlanDraft:
            assemble_plan_spec(output, envelope=envelope, pool=pool)
            return output

        result: StructuredAgentResult[SingleAgentPlanDraft] = await self._invoker().ainvoke(
            role_code=LlmAgentRoleCode.COORDINATOR,
            prompt_version=self.prompt_version,
            output_schema_version=SINGLE_AGENT_DRAFT_SCHEMA_VERSION,
            output_schema=SingleAgentPlanDraft,
            messages=messages_for(
                prompt,
                output_schema_version=SINGLE_AGENT_DRAFT_SCHEMA_VERSION,
                payload=payload,
            ),
            domain_validator=validate,
            canonical_factory=lambda values: SingleAgentPlanDraft.create(
                **canonical_plan_values(values)
            ),
        )

        graph_result = self._finalize(result, envelope=envelope, pool=pool)
        elapsed_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        return CaseRunResult(
            case=scenario.case,
            scenario=scenario,
            architecture_code=self.architecture_code,
            script=script,
            graph_result=graph_result,
            invocations=(
                InvocationLog(
                    role_code=LlmAgentRoleCode.COORDINATOR.value,
                    mode_code="INITIAL",
                    script_code=graph_result.invocation_audits[0].status_code
                    if graph_result.invocation_audits
                    else "FAILED",
                ),
            ),
            wall_clock_ms=elapsed_ms,
        )

    def _finalize(
        self,
        result: StructuredAgentResult[SingleAgentPlanDraft],
        *,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
    ) -> V3GraphResult:
        context = _ExecutionContext()
        compiler = _Compiler(envelope, pool, context, self.versions.compiler_version)
        validator = _IntegrityValidator(context, self.versions.validator_version)
        fallback = _Fallback(
            DeterministicGraphFallbackProvider(fallback_version=self.versions.fallback_version),
            self.versions.fallback_version,
        )

        audits = (_audit(result),)
        validations: list[IntegrityValidation] = []
        compiled_plans: list[object] = []
        failure_codes: list[str] = []

        plan_spec: PlanSpec | None = None
        proposals: tuple[SpecialistAgentProposal, ...] = ()
        compiled: CompiledPlan | None = None

        def gate(
            source: PlanSpec | DeterministicFallbackPlanSpec,
            *,
            with_proposals: tuple[SpecialistAgentProposal, ...],
        ) -> bool:
            """Compile and validate one candidate, exactly as the graph does.

            `nodes.compile_plan` and `nodes.validate_plan` each wrap their call
            in a bare `except` and record a stable failure code. Compilation is
            where an asserted duration becomes a measured one, so a plan whose
            real timing misses the window raises here rather than returning a
            violation -- and letting that escape would crash the run instead of
            failing it, which is not what the user would experience.
            """

            nonlocal compiled
            try:
                candidate = compiler.compile(source, proposals=with_proposals)
            except Exception:  # noqa: BLE001 -- mirrors nodes.compile_plan
                failure_codes.append("V3_COMPILATION_FAILED")
                return False
            try:
                report = validator.validate(
                    candidate, constraint_envelope=envelope, exercise_pool=pool
                )
            except Exception:  # noqa: BLE001 -- mirrors nodes.validate_plan
                failure_codes.append("V3_VALIDATION_FAILED")
                return False
            compiled_plans.append(candidate)
            validations.append(
                _Validation(report.passed, report.repairable, report.violation_codes)
            )
            if not report.passed:
                failure_codes.extend(report.violation_codes)
                return False
            compiled = candidate
            return True

        if result.output is not None:
            try:
                plan_spec, _, proposals = assemble_plan_spec(
                    result.output, envelope=envelope, pool=pool
                )
            except Exception:  # noqa: BLE001 -- a draft that cannot become a PlanSpec
                failure_codes.append("V3_PLAN_SPEC_MISSING")
            else:
                gate(plan_spec, with_proposals=proposals)
        elif result.failure is not None:
            failure_codes.append(result.failure.code.value)

        used_fallback = False
        if compiled is None:
            # The same deterministic fallback the graph reaches for. It belongs
            # to the service, not to an architecture, so withholding it here
            # would measure something the user would never experience.
            fallback_spec = fallback.build(
                constraint_envelope=envelope,
                exercise_pool=pool,
                failure_codes=tuple(failure_codes),
            )
            if fallback_spec is None:
                failure_codes.append("FALLBACK_PLAN_INVALID")
            else:
                used_fallback = gate(fallback_spec, with_proposals=())

        return V3GraphResult(
            status_code="SUCCEEDED" if compiled is not None else "FAILED",
            graph_version=f"{self.versions.graph_version}-{self.architecture_code.lower()}",
            plan_spec=plan_spec if not used_fallback else None,
            compiled_plan=compiled,
            failure_codes=tuple(dict.fromkeys(failure_codes)),
            used_fallback=used_fallback,
            repair_attempts=0,
            round_one_proposals=proposals,
            coordinator_agent_plan=plan_spec,
            integrity_validations=tuple(validations),
            compiled_plans=tuple(compiled_plans),
            invocation_audits=audits,
        )


def _audit(result: StructuredAgentResult[SingleAgentPlanDraft]) -> InvocationAudit:
    telemetry = result.telemetry
    if result.failure is None:
        status_code = "SUCCEEDED"
        failure_code = None
    else:
        status_code = {
            LlmAgentFailureCode.PROVIDER_TIMEOUT: "TIMEOUT",
            LlmAgentFailureCode.SCHEMA_INVALID: "INVALID_OUTPUT",
            LlmAgentFailureCode.DOMAIN_INVALID: "INVALID_OUTPUT",
        }.get(result.failure.code, "FAILED")
        failure_code = result.failure.code.value
    return InvocationAudit(
        role_code=LlmAgentRoleCode.COORDINATOR.value,
        phase_code="INITIAL",
        status_code=status_code,
        attempt_count=telemetry.attempt_count if telemetry else 0,
        latency_ms=telemetry.latency_ms if telemetry else 0,
        input_token_count=telemetry.input_token_count if telemetry else None,
        output_token_count=telemetry.output_token_count if telemetry else None,
        provider_usage_present=telemetry.provider_usage_present if telemetry else False,
        failure_code=failure_code,
    )


SINGLE_AGENT_ARCHITECTURES: Final[tuple[str, ...]] = (
    ARCHITECTURE_SINGLE_LLM,
    ARCHITECTURE_SINGLE_AGENT_RAG,
)


__all__ = [
    "ARCHITECTURE_SINGLE_AGENT_RAG",
    "ARCHITECTURE_SINGLE_LLM",
    "NO_SPECIALIST_ADVICE_CODE",
    "SINGLE_AGENT_ARCHITECTURES",
    "SINGLE_AGENT_DRAFT_SCHEMA_VERSION",
    "SINGLE_AGENT_INSTRUCTION",
    "SINGLE_AGENT_RAG_PROMPT_VERSION",
    "SINGLE_LLM_PROMPT_VERSION",
    "SingleAgentPlanDraft",
    "SingleAgentRunner",
    "assemble_plan_spec",
    "single_agent_payload",
    "synthesize_proposals",
]
