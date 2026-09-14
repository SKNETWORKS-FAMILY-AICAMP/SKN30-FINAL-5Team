"""A replayed decision must report the name it was given when it was decided.

`build_plan_name` decides the public routine name at decision time and the create
response carries it. Reading the day's decision back rebuilds the response from
the stored rows instead of replaying a saved payload, so anything the rebuild
forgets is silently lost -- and a client that reopens the plan then falls back to
composing its own title. That is how one routine showed two different names in a
single session just from leaving the screen and coming back.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from backend.app.db.repositories.decision import DecisionRepository


def _plan_item() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        exercise_id=uuid4(),
        display_name="바벨 굿모닝",
        sequence=1,
        user_sequence=None,
        phase_code="MAIN",
        tier_code="CORE",
        sets=2,
        user_sets=None,
        reps=10,
        user_reps=None,
        work_seconds=40,
        user_work_seconds=None,
        # Null on plans written before the resolved per-set figure was recorded, which
        # is the case this stub stands for; the payload derives it from the total.
        work_seconds_per_set=None,
        user_work_seconds_per_set=None,
        rest_seconds=60,
        user_rest_seconds=None,
        transition_seconds=10,
        instruction_content_version="test-v1",
    )


def _run(candidate: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        local_date=date(2026, 9, 9),
        status_code="COMPLETED",
        safety_status_code="PASS",
        recommended_action_code=candidate.action_code,
        input_snapshot={
            "requested_duration_minutes": 30,
            "duration_adjustment_source_code": "PROFILE",
        },
        candidates=[candidate],
        safety_reviews=[
            SimpleNamespace(
                public_guidance=None,
                safety_status_code="PASS",
                vetoed=False,
                reason_codes=[],
            )
        ],
        explanations=[],
        proposals=[],
        options=[],
        coordinator_result={"reason_codes": []},
        generation_mode_code="INITIAL",
        decision_engine_code="V3",
        root_decision_run_id=None,
        parent_decision_run_id=None,
        regeneration_sequence=0,
        created_at=SimpleNamespace(),
    )


def _candidate(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": uuid4(),
        "action_code": "DOWNSHIFT",
        "training_type_code": "STRENGTH",
        "body_focus_code": "BACK",
        "routine_name": "등 컨디션 조절 루틴",
        "routine_name_reason_codes": ["DOMINANT_FOCUS_BACK", "LOAD_ADJUSTED"],
        "routine_naming_rule_version": "1.0.0",
        "requested_duration_minutes": 30,
        "estimated_duration_seconds": 1800,
        "user_revised_estimated_duration_seconds": None,
        "user_revision_sequence": 0,
        "expected_duration_min_seconds": None,
        "expected_duration_max_seconds": None,
        "duration_estimation_policy_version": None,
        "estimated_calories_burned": None,
        "setup_seconds": 0,
        "warmup_seconds": 120,
        "cooldown_seconds": 120,
        "selected": True,
        "items": [_plan_item()],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _replay(candidate: SimpleNamespace) -> dict[str, Any]:
    run = _run(candidate)
    session = SimpleNamespace(scalar=lambda _: run)
    response = DecisionRepository().get_response(session, uuid4(), run.id)
    assert response is not None
    return response


def test_replayed_plan_keeps_the_name_the_decision_was_given() -> None:
    plan = _replay(_candidate())["final_plan"]

    assert plan["routine_name"] == "등 컨디션 조절 루틴"
    assert plan["routine_name_reason_codes"] == [
        "DOMINANT_FOCUS_BACK",
        "LOAD_ADJUSTED",
    ]
    assert plan["routine_naming_rule_version"] == "1.0.0"


def test_replayed_plan_reports_no_name_for_a_run_stored_before_the_column() -> None:
    """Older runs replay as null rather than dropping the field or inventing one."""

    plan = _replay(
        _candidate(
            routine_name=None,
            routine_name_reason_codes=None,
            routine_naming_rule_version=None,
        )
    )["final_plan"]

    assert plan["routine_name"] is None
    assert plan["routine_name_reason_codes"] is None
    assert plan["routine_naming_rule_version"] is None
