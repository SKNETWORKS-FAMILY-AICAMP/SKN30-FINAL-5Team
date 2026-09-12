"""Constraint checks: duration, location, equipment, pool membership, volume.

These are the promises a plan makes to the person performing it.  Each is
checked against the frozen envelope rather than against the model's own claim,
because a plan that asserts its duration and a plan that costs it are different
things (`v3_duration.py`).
"""

from __future__ import annotations

from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.tests.evaluation.evaluators.findings import DefectClass, Finding, Severity
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult


def evaluate(run: CaseRunResult) -> tuple[Finding, ...]:
    plan = run.compiled_plan
    if plan is None:
        return ()

    case = run.case
    envelope = run.scenario.constraint_envelope
    pool_ids = {str(record.exercise_id) for record in run.scenario.exercise_pool.exercises}
    findings: list[Finding] = []

    # 1. Requested duration. The compiled value is measured from the catalog
    #    timing basis, so this compares cost against request, not claim against
    #    claim. Section 7 allows five minutes either way and nothing more.
    target = envelope.requested_duration_minutes * SECONDS_PER_MINUTE
    delta = plan.estimated_duration_seconds - target
    tolerance = case.expected_constraints.duration_tolerance_seconds or DURATION_TOLERANCE_SECONDS
    if abs(delta) > tolerance:
        findings.append(
            Finding(
                check_code="REQUESTED_DURATION_NOT_PRESERVED",
                severity=Severity.MAJOR,
                expected=f"within {tolerance}s of {target}s",
                observed=f"{plan.estimated_duration_seconds}s ({delta:+d}s)",
                defect_class=DefectClass.SERVICE,
            )
        )
    if plan.requested_duration_minutes != envelope.requested_duration_minutes:
        findings.append(
            Finding(
                check_code="REQUESTED_DURATION_REWRITTEN",
                severity=Severity.CRITICAL,
                expected=f"requested duration stays {envelope.requested_duration_minutes} minutes",
                observed=f"plan claims {plan.requested_duration_minutes} minutes",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 2. Every prescribed exercise must come from the supplied pool. An agent
    #    that invents catalog content has left the reviewed data entirely.
    escaped = sorted(set(run.prescribed_exercise_ids) - pool_ids)
    if escaped:
        findings.append(
            Finding(
                check_code="EXERCISE_OUTSIDE_POOL",
                severity=Severity.CRITICAL,
                expected="every prescribed exercise comes from the supplied pool",
                observed=f"exercises outside the pool: {escaped}",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 3. Mandatory exercises may not be dropped.
    mandatory = {str(value) for value in envelope.mandatory_exercise_ids}
    missing = sorted(mandatory - set(run.prescribed_exercise_ids))
    if missing:
        findings.append(
            Finding(
                check_code="MANDATORY_EXERCISE_MISSING",
                severity=Severity.MAJOR,
                expected="every mandatory exercise appears in the plan",
                observed=f"missing: {missing}",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 4. Location. Both the envelope allowlist and the catalog record have to
    #    permit where the movement is performed.
    for item in plan.exercises:
        prescription = item.prescription
        if prescription.location_code not in envelope.allowed_location_codes:
            findings.append(
                Finding(
                    check_code="LOCATION_NOT_ALLOWED",
                    severity=Severity.MAJOR,
                    expected=f"location within {sorted(envelope.allowed_location_codes)}",
                    observed=f"{item.catalog_record.stable_code} at {prescription.location_code}",
                    defect_class=DefectClass.SERVICE,
                )
            )
        if prescription.location_code not in item.catalog_record.location_codes:
            findings.append(
                Finding(
                    check_code="LOCATION_NOT_SUPPORTED_BY_CATALOG",
                    severity=Severity.MAJOR,
                    expected="the catalog record supports the prescribed location",
                    observed=f"{item.catalog_record.stable_code} at {prescription.location_code}",
                    defect_class=DefectClass.SERVICE,
                )
            )

    findings.extend(_equipment_findings(run))
    findings.extend(_volume_findings(run))
    return tuple(findings)


def _equipment_findings(run: CaseRunResult) -> list[Finding]:
    """Compare the plan's equipment against what the case says the user has.

    Equipment is deliberately not a gate inside the service: the 2026-08-27
    approval removed it from onboarding, so a real envelope carries an empty
    allowlist and the integrity validator only checks the plan against the
    catalog record (`v3_validation.py`).  Eligibility by equipment is settled
    upstream, when PostgreSQL composes the pool.

    So this reports at two different levels on purpose.  When the case declares
    an equipment allowlist, exceeding it is a real failure.  When it declares
    none, a plan naming equipment is recorded as an observation, because the
    service never promised to constrain it.
    """

    plan = run.compiled_plan
    assert plan is not None
    envelope = run.scenario.constraint_envelope
    allowed = set(envelope.allowed_equipment_codes)
    prohibited = set(run.case.prohibited_actions.equipment_codes)
    findings: list[Finding] = []

    for item in plan.exercises:
        required = set(item.catalog_record.equipment_codes) - {"BODYWEIGHT"}
        if not required:
            continue
        if prohibited & required:
            findings.append(
                Finding(
                    check_code="PROHIBITED_EQUIPMENT_REQUIRED",
                    severity=Severity.MAJOR,
                    expected=f"no exercise requiring {sorted(prohibited)}",
                    observed=(f"{item.catalog_record.stable_code} requires {sorted(required)}"),
                    defect_class=DefectClass.SERVICE,
                )
            )
        elif allowed and not required.issubset(allowed):
            findings.append(
                Finding(
                    check_code="EQUIPMENT_NOT_AVAILABLE_TO_USER",
                    severity=Severity.MAJOR,
                    expected=f"equipment within {sorted(allowed)}",
                    observed=(f"{item.catalog_record.stable_code} requires {sorted(required)}"),
                    defect_class=DefectClass.SERVICE,
                )
            )
        elif not allowed:
            findings.append(
                Finding(
                    check_code="EQUIPMENT_UNCONSTRAINED_BY_ENVELOPE",
                    severity=Severity.INFO,
                    expected="equipment is settled upstream during pool composition",
                    observed=(
                        f"{item.catalog_record.stable_code} requires {sorted(required)} "
                        "with an empty envelope allowlist"
                    ),
                    defect_class=DefectClass.NOT_A_DEFECT,
                )
            )
    return findings


def _volume_findings(run: CaseRunResult) -> list[Finding]:
    """Check prescribed volume against the Recovery ceiling and the FITT range."""

    plan = run.compiled_plan
    assert plan is not None
    ceiling = run.scenario.constraint_envelope.recovery_ceiling
    findings: list[Finding] = []
    sets_by_exercise: dict[str, int] = {}

    for item in plan.exercises:
        prescription = item.prescription
        record = item.catalog_record
        key = str(prescription.exercise_id)
        sets_by_exercise[key] = sets_by_exercise.get(key, 0) + prescription.sets

        if (
            ceiling.allowed_intensity_codes
            and prescription.intensity_code not in ceiling.allowed_intensity_codes
        ):
            findings.append(
                Finding(
                    check_code="RECOVERY_INTENSITY_CEILING_EXCEEDED",
                    severity=Severity.MAJOR,
                    expected=f"intensity within {sorted(ceiling.allowed_intensity_codes)}",
                    observed=f"{record.stable_code} at {prescription.intensity_code}",
                    defect_class=DefectClass.SERVICE,
                )
            )
        if (
            ceiling.maximum_repetitions_per_set is not None
            and prescription.repetitions_per_set is not None
            and prescription.repetitions_per_set > ceiling.maximum_repetitions_per_set
        ):
            findings.append(
                Finding(
                    check_code="RECOVERY_REPETITION_CEILING_EXCEEDED",
                    severity=Severity.MAJOR,
                    expected=f"at most {ceiling.maximum_repetitions_per_set} repetitions",
                    observed=f"{record.stable_code} at {prescription.repetitions_per_set}",
                    defect_class=DefectClass.SERVICE,
                )
            )
        if (
            ceiling.minimum_rest_seconds_between_sets is not None
            and prescription.rest_seconds_between_sets < ceiling.minimum_rest_seconds_between_sets
        ):
            findings.append(
                Finding(
                    check_code="RECOVERY_REST_FLOOR_BREACHED",
                    severity=Severity.MAJOR,
                    expected=f"at least {ceiling.minimum_rest_seconds_between_sets}s rest",
                    observed=f"{record.stable_code} at {prescription.rest_seconds_between_sets}s",
                    defect_class=DefectClass.SERVICE,
                )
            )

        volume = record.approved_fitt_volume()
        if volume is not None and prescription.repetitions_per_set is not None:
            within = (
                volume.min_sets <= prescription.sets <= volume.max_sets
                and volume.min_reps <= prescription.repetitions_per_set <= volume.max_reps
            )
            if not within:
                findings.append(
                    Finding(
                        check_code="FITT_RANGE_EXCEEDED",
                        severity=Severity.MAJOR,
                        expected=(
                            f"{record.stable_code} within sets "
                            f"{volume.min_sets}-{volume.max_sets} and reps "
                            f"{volume.min_reps}-{volume.max_reps}"
                        ),
                        observed=(
                            f"{prescription.sets} sets x {prescription.repetitions_per_set} reps"
                        ),
                        defect_class=DefectClass.SERVICE,
                    )
                )

    if ceiling.maximum_sets_per_exercise is not None:
        for exercise_id, total in sorted(sets_by_exercise.items()):
            if total > ceiling.maximum_sets_per_exercise:
                findings.append(
                    Finding(
                        check_code="RECOVERY_SETS_CEILING_EXCEEDED",
                        severity=Severity.MAJOR,
                        expected=f"at most {ceiling.maximum_sets_per_exercise} sets per exercise",
                        observed=f"{exercise_id} totalled {total} sets",
                        defect_class=DefectClass.SERVICE,
                    )
                )
    return findings


__all__ = ["evaluate"]
