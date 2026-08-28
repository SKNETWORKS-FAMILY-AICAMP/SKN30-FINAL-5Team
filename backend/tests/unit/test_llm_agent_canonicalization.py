"""Provider output reaches the domain contracts in canonical code order."""

from backend.app.integrations.llm_agents.canonicalization import (
    canonical_plan_values,
    canonical_proposal_values,
)


def test_adjustment_codes_are_sorted_the_way_the_contract_requires() -> None:
    # The observed staging failure: RECOVERY answered with codes in the order it
    # reasoned about them and every proposal was rejected for the ordering
    # alone. The order carries no meaning, so the server establishes it.
    values = canonical_proposal_values(
        {
            "adjustment_codes": [
                "RECOVERY_ELIGIBLE_ONLY",
                "INTENSITY_REDUCED",
                "ALLOW_ADDITIONAL_REST",
            ]
        }
    )

    assert values["adjustment_codes"] == (
        "ALLOW_ADDITIONAL_REST",
        "INTENSITY_REDUCED",
        "RECOVERY_ELIGIBLE_ONLY",
    )


def test_every_proposal_code_field_is_normalized() -> None:
    values = canonical_proposal_values(
        {
            "adjustment_codes": ["B_CODE", "A_CODE"],
            "hard_constraint_codes": ["D_CODE", "C_CODE"],
            "reason_codes": ["F_CODE", "E_CODE"],
            "evidence_reference_codes": ["H_CODE", "G_CODE"],
        }
    )

    assert values["adjustment_codes"] == ("A_CODE", "B_CODE")
    assert values["hard_constraint_codes"] == ("C_CODE", "D_CODE")
    assert values["reason_codes"] == ("E_CODE", "F_CODE")
    assert values["evidence_reference_codes"] == ("G_CODE", "H_CODE")


def test_repeated_codes_are_reduced_to_one() -> None:
    # The contract rejects duplicates. A repeated code says nothing beyond the
    # code itself, so it is the same normalization rather than a new decision.
    values = canonical_proposal_values({"reason_codes": ["A_CODE", "A_CODE", "B_CODE"]})

    assert values["reason_codes"] == ("A_CODE", "B_CODE")


def test_equipment_codes_inside_prescriptions_are_normalized() -> None:
    values = canonical_proposal_values(
        {
            "exercise_prescriptions": [
                {"sequence": 1, "equipment_codes": ["MAT", "BODYWEIGHT"]},
                {"sequence": 2, "equipment_codes": ["RESISTANCE_BAND", "MAT"]},
            ]
        }
    )

    prescriptions = values["exercise_prescriptions"]
    assert isinstance(prescriptions, tuple)
    assert prescriptions[0]["equipment_codes"] == ("BODYWEIGHT", "MAT")
    assert prescriptions[1]["equipment_codes"] == ("MAT", "RESISTANCE_BAND")
    assert prescriptions[0]["sequence"] == 1


def test_plan_decision_codes_are_normalized() -> None:
    values = canonical_plan_values({"decision_codes": ["Z_CODE", "A_CODE"]})

    assert values["decision_codes"] == ("A_CODE", "Z_CODE")


def test_fields_that_are_not_code_lists_are_left_alone() -> None:
    values = canonical_proposal_values(
        {
            "agent_type_code": "RECOVERY",
            "proposal_status_code": "READY",
            "requested_duration_minutes": 30,
            "public_summary_code": None,
        }
    )

    assert values == {
        "agent_type_code": "RECOVERY",
        "proposal_status_code": "READY",
        "requested_duration_minutes": 30,
        "public_summary_code": None,
    }


def test_malformed_code_values_are_passed_through_to_fail_validation() -> None:
    # Reshaping a wrong type into something sortable would hide provider output
    # the contract should reject.
    values = canonical_proposal_values(
        {"adjustment_codes": "NOT_A_LIST", "reason_codes": [1, 2], "hard_constraint_codes": None}
    )

    assert values["adjustment_codes"] == "NOT_A_LIST"
    assert values["reason_codes"] == [1, 2]
    assert values["hard_constraint_codes"] is None


def test_malformed_prescriptions_are_passed_through_to_fail_validation() -> None:
    values = canonical_proposal_values({"exercise_prescriptions": ["not-an-object"]})

    assert values["exercise_prescriptions"] == ["not-an-object"]
