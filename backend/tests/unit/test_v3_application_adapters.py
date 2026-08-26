from dataclasses import replace

from backend.app.modules.decisions.v3_application import (
    DeterministicV3SafetyPolicyAdapter,
    V3ApplicationContext,
)
from backend.app.modules.decisions.v3_creation import V3CreationSource
from backend.tests.unit.test_decision_service import FakeRepository, _context


def _source(*, emergency: bool = False) -> V3CreationSource:
    context = _context()
    if emergency:
        context = replace(context, adverse_reaction_codes=("CHEST_DISCOMFORT",))
    assembly = FakeRepository(context).assembly
    return V3CreationSource(
        local_date=context.local_date,
        context_version=context.context_version,
        normalized_values={
            "duration_adjustment_source_code": context.duration_adjustment_source_code,
            "experience_level_code": context.experience_level_code,
            "location_code": context.location_code,
        },
        application_context=V3ApplicationContext(assembly, ()),
    )


def test_application_context_is_excluded_from_serialized_source() -> None:
    source = _source()

    payload = source.model_dump(mode="json")

    assert "application_context" not in payload
    assert "daily_context_id" not in str(payload)


def test_deterministic_safety_veto_is_immutable_and_terminal() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(_source(emergency=True))

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "STOP_AND_SEEK_HELP"
