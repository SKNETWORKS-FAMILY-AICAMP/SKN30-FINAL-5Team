from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime

import pytest

from backend.app.domain.rules.weekly_report import (
    WEEKLY_AGGREGATE_SCHEMA_VERSION,
    WEEKLY_REPORT_POLICY_VERSION,
    InvalidAcknowledgementTransitionError,
    UserWeekStatusCode,
    WeeklyLearningSignalCode,
    WeeklyReportReasonCode,
    WeeklyReportStatusCode,
    WeekNotClosedError,
    acknowledge_weekly_report,
    build_closed_week_aggregate,
    evaluate_report_eligibility,
    evaluate_week_status,
    weekly_boundary_for,
)


def test_week_runs_from_local_monday_through_sunday() -> None:
    boundary = weekly_boundary_for(
        local_date=date(2026, 8, 9),
        timezone_name="Asia/Seoul",
    )

    assert boundary.week_start_local_date == date(2026, 8, 3)
    assert boundary.week_end_local_date == date(2026, 8, 9)
    assert boundary.starts_at.isoformat() == "2026-08-03T00:00:00+09:00"
    assert boundary.closes_at.isoformat() == "2026-08-10T00:00:00+09:00"


def test_week_status_uses_user_timezone_at_the_same_instant() -> None:
    requested_at = datetime(2026, 8, 9, 15, 30, tzinfo=UTC)
    seoul_week = weekly_boundary_for(local_date=date(2026, 8, 9), timezone_name="Asia/Seoul")
    los_angeles_week = weekly_boundary_for(
        local_date=date(2026, 8, 9), timezone_name="America/Los_Angeles"
    )

    assert (
        evaluate_week_status(boundary=seoul_week, requested_at=requested_at)
        is UserWeekStatusCode.CLOSED
    )
    assert (
        evaluate_week_status(boundary=los_angeles_week, requested_at=requested_at)
        is UserWeekStatusCode.OPEN
    )


def test_week_boundary_preserves_local_midnight_across_dst_change() -> None:
    boundary = weekly_boundary_for(local_date=date(2026, 11, 1), timezone_name="America/New_York")

    assert boundary.starts_at.isoformat() == "2026-10-26T00:00:00-04:00"
    assert boundary.closes_at.isoformat() == "2026-11-02T00:00:00-05:00"


def test_open_week_blocks_final_report_generation() -> None:
    boundary = weekly_boundary_for(local_date=date(2026, 8, 3), timezone_name="Asia/Seoul")
    requested_at = datetime.fromisoformat("2026-08-09T23:59:59+09:00")

    eligibility = evaluate_report_eligibility(boundary=boundary, requested_at=requested_at)

    assert eligibility.week_status_code is UserWeekStatusCode.OPEN
    assert eligibility.report_allowed is False
    assert eligibility.reason_code is WeeklyReportReasonCode.WEEK_NOT_CLOSED
    with pytest.raises(WeekNotClosedError, match="WEEK_NOT_CLOSED"):
        build_closed_week_aggregate(
            boundary=boundary,
            requested_at=requested_at,
            completed_count=1,
            partial_count=0,
            not_completed_count=0,
            stopped_for_safety_count=0,
        )


def test_closed_week_allows_immutable_minimal_aggregate() -> None:
    boundary = weekly_boundary_for(local_date=date(2026, 8, 3), timezone_name="Asia/Seoul")

    aggregate = build_closed_week_aggregate(
        boundary=boundary,
        requested_at=datetime.fromisoformat("2026-08-10T00:00:00+09:00"),
        completed_count=2,
        partial_count=1,
        not_completed_count=1,
        stopped_for_safety_count=1,
        primary_miss_reason_code="TIME_SHORTAGE",
    )

    assert aggregate.learning_signal_codes == (WeeklyLearningSignalCode.NOT_COMPLETED,)
    assert aggregate.week_status_code is UserWeekStatusCode.CLOSED
    assert aggregate.penalty_applied is False
    assert aggregate.aggregate_schema_version == WEEKLY_AGGREGATE_SCHEMA_VERSION
    assert aggregate.report_policy_version == WEEKLY_REPORT_POLICY_VERSION
    field_names = {field.name for field in fields(aggregate)}
    assert not field_names & {
        "raw_health_data",
        "raw_checkins",
        "raw_wearable_samples",
        "calendar_text",
    }
    with pytest.raises(FrozenInstanceError):
        aggregate.completed_count = 3  # type: ignore[misc]


def test_acknowledgement_is_explicit_and_idempotent() -> None:
    assert (
        acknowledge_weekly_report(WeeklyReportStatusCode.GENERATED)
        is WeeklyReportStatusCode.ACKNOWLEDGED
    )
    assert (
        acknowledge_weekly_report(WeeklyReportStatusCode.ACKNOWLEDGED)
        is WeeklyReportStatusCode.ACKNOWLEDGED
    )
    with pytest.raises(InvalidAcknowledgementTransitionError):
        acknowledge_weekly_report(WeeklyReportStatusCode.FAILED)
