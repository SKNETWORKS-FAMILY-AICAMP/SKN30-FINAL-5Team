from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.weekly_reports.ports import (
    IdempotencyRecord,
    ReportValues,
    StoredReport,
    WeeklyReportNarration,
    WeeklyReportNarrationAgentPort,
    WeeklyReportNarrationInput,
    WeeklySessionEvidence,
    WeekProfile,
    WeekRecord,
)
from backend.app.modules.weekly_reports.schemas import (
    WeeklyReportAcknowledgementRequest,
    WeeklyReportCreateRequest,
)
from backend.app.modules.weekly_reports.service import (
    IdempotencyKeyReusedError,
    InvalidWeekStartError,
    ReportInputChangedError,
    WeeklyReportService,
    WeekNotClosedError,
    WeekOutcomesIncompleteError,
)

WEEK_START = date(2026, 8, 3)
WEEK_END = date(2026, 8, 9)
CLOSED_NOW = datetime(2026, 8, 9, 15, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> Any:
        return nullcontext()


class FakeWeeklyReportRepository:
    def __init__(self) -> None:
        self.profile = WeekProfile("Asia/Seoul", 4, False)
        self.weeks: dict[date, WeekRecord] = {}
        self.evidence: tuple[WeeklySessionEvidence, ...] = ()
        self.reports_by_week: dict[UUID, StoredReport] = {}
        self.report_week_ids: dict[UUID, UUID] = {}
        self.idempotency: dict[tuple[str, UUID], IdempotencyRecord] = {}
        self.created_report_count = 0
        self.last_report_values: ReportValues | None = None

    def acquire_week_lock(self, *args: Any) -> None:
        pass

    def acquire_idempotency_lock(self, *args: Any) -> None:
        pass

    def get_idempotency_record(
        self, session: Any, user_id: UUID, endpoint_code: str, key: UUID
    ) -> IdempotencyRecord | None:
        return self.idempotency.get((endpoint_code, key))

    def save_idempotency_record(self, session: Any, **values: Any) -> None:
        self.idempotency[(values["endpoint_code"], values["key"])] = IdempotencyRecord(
            values["request_hash"], values["response_payload"]
        )

    def get_week_profile(self, session: Any, user_id: UUID, week_start: date) -> WeekProfile | None:
        return self.profile

    def get_week(self, session: Any, user_id: UUID, week_start: date) -> WeekRecord | None:
        return self.weeks.get(week_start)

    def create_week(self, session: Any, **values: Any) -> WeekRecord:
        week = WeekRecord(
            week_id=values["week_id"],
            user_id=values["user_id"],
            week_start=values["week_start"],
            week_end=values["week_end"],
            timezone=values["timezone"],
            target_workout_count=values["target_workout_count"],
            plan_origin_code=values["plan_origin_code"],
            cold_start_applied=values["cold_start_applied"],
            status_code=values["status_code"],
            closed_at=values["closed_at"],
            report_id=None,
            report_status_code=None,
        )
        self.weeks[week.week_start] = week
        return week

    def close_week(self, session: Any, week_id: UUID, closed_at: datetime) -> WeekRecord:
        week = next(value for value in self.weeks.values() if value.week_id == week_id)
        closed = WeekRecord(
            week.week_id,
            week.user_id,
            week.week_start,
            week.week_end,
            week.timezone,
            week.target_workout_count,
            week.plan_origin_code,
            week.cold_start_applied,
            "CLOSED",
            closed_at,
            week.report_id,
            week.report_status_code,
        )
        self.weeks[week.week_start] = closed
        return closed

    def get_week_evidence(
        self, session: Any, user_id: UUID, week_start: date, week_end: date
    ) -> tuple[WeeklySessionEvidence, ...]:
        return self.evidence

    def get_report_for_week(self, session: Any, week_id: UUID) -> StoredReport | None:
        return self.reports_by_week.get(week_id)

    def get_report_by_id(self, session: Any, user_id: UUID, report_id: UUID) -> StoredReport | None:
        week_id = self.report_week_ids.get(report_id)
        return None if week_id is None else self.reports_by_week[week_id]

    def create_report(
        self, session: Any, *, week: WeekRecord, values: ReportValues
    ) -> StoredReport:
        self.created_report_count += 1
        self.last_report_values = values
        payload = {
            "report_id": values.report_id,
            "week_start": week.week_start,
            "week_end": week.week_end,
            "status_code": "GENERATED",
            "counts": {
                "completed": values.completed_count,
                "partial": values.partial_count,
                "not_completed": values.not_completed_count,
                "stopped_for_safety": values.stopped_for_safety,
            },
            "primary_miss_reason_code": values.primary_miss_reason_code,
            "completion_rate": values.completion_rate,
            "persistence_rate": values.persistence_rate,
            "negotiation_success_rate": values.negotiation_success_rate,
            "weekday_failure_summary": values.weekday_failure_summary,
            "pattern_summary": values.pattern_summary,
            "decision_summary": values.decision_summary,
            "adjustment_direction_code": values.adjustment_direction_code,
            "next_action": values.next_action,
            "agent_summaries": values.agent_summaries,
            "summary": values.summary,
            "acknowledged_at": None,
            "generated_at": values.generated_at,
        }
        stored = StoredReport(values.input_hash, payload)
        self.reports_by_week[week.week_id] = stored
        self.report_week_ids[values.report_id] = week.week_id
        self.weeks[week.week_start] = WeekRecord(
            week_id=week.week_id,
            user_id=week.user_id,
            week_start=week.week_start,
            week_end=week.week_end,
            timezone=week.timezone,
            target_workout_count=week.target_workout_count,
            plan_origin_code=week.plan_origin_code,
            cold_start_applied=week.cold_start_applied,
            status_code=week.status_code,
            closed_at=week.closed_at,
            report_id=values.report_id,
            report_status_code="GENERATED",
        )
        return stored

    def acknowledge_report(self, session: Any, **values: Any) -> StoredReport | None:
        report_id = values["report_id"]
        week_id = self.report_week_ids.get(report_id)
        if week_id is None:
            return None
        existing = self.reports_by_week[week_id]
        payload = {
            **existing.response_payload,
            "status_code": "ACKNOWLEDGED",
            "acknowledged_at": values["acknowledged_at"],
        }
        stored = StoredReport(existing.input_hash, payload)
        self.reports_by_week[week_id] = stored
        return stored


def _service(
    repository: FakeWeeklyReportRepository,
    now: datetime = CLOSED_NOW,
    narration_agent: WeeklyReportNarrationAgentPort | None = None,
) -> WeeklyReportService:
    return WeeklyReportService(
        repository,
        clock=lambda: now,
        narration_agent=narration_agent,
    )


def _request() -> WeeklyReportCreateRequest:
    return WeeklyReportCreateRequest(expected_week_status_code="CLOSED")


def _evidence() -> tuple[WeeklySessionEvidence, ...]:
    return (
        WeeklySessionEvidence(
            WEEK_START,
            "COMPLETED",
            ("COMPLETED", "COMPLETED"),
            False,
            None,
            "KEEP",
            "APPROPRIATE",
            False,
        ),
        WeeklySessionEvidence(
            WEEK_START + timedelta(days=1),
            "PARTIAL",
            ("COMPLETED", "PENDING"),
            False,
            None,
            "DOWNSHIFT",
            "HARD",
            False,
        ),
        WeeklySessionEvidence(
            WEEK_START + timedelta(days=2),
            "NOT_COMPLETED",
            ("PENDING", "PENDING"),
            False,
            "TIME_SHORTAGE",
            "KEEP",
            None,
            False,
        ),
        WeeklySessionEvidence(
            WEEK_START + timedelta(days=3),
            "STOPPED_FOR_SAFETY",
            ("COMPLETED", "PENDING"),
            True,
            None,
            "RECOVERY",
            None,
            True,
        ),
    )


def test_user_timezone_keeps_sunday_open_and_closes_at_local_monday() -> None:
    open_repository = FakeWeeklyReportRepository()
    open_now = datetime(2026, 8, 9, 14, 59, 59, tzinfo=UTC)
    opened = _service(open_repository, open_now).get_week(
        FakeSession(),
        uuid4(),
        WEEK_START,  # type: ignore[arg-type]
    )
    assert opened.status_code == "OPEN"
    assert opened.closed_at is None

    closed_repository = FakeWeeklyReportRepository()
    closed = _service(closed_repository).get_week(
        FakeSession(),
        uuid4(),
        WEEK_START,  # type: ignore[arg-type]
    )
    assert closed.status_code == "CLOSED"
    assert closed.closed_at == CLOSED_NOW


def test_dst_week_closes_at_next_local_monday_midnight() -> None:
    week_start = date(2026, 3, 2)
    repository = FakeWeeklyReportRepository()
    repository.profile = WeekProfile("America/New_York", 4, False)

    opened = _service(repository, datetime(2026, 3, 9, 3, 59, 59, tzinfo=UTC)).get_week(
        FakeSession(), uuid4(), week_start
    )  # type: ignore[arg-type]
    assert opened.status_code == "OPEN"

    closed = _service(repository, datetime(2026, 3, 9, 4, 0, tzinfo=UTC)).get_week(
        FakeSession(),
        uuid4(),
        week_start,  # type: ignore[arg-type]
    )
    assert closed.status_code == "CLOSED"
    assert closed.closed_at == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)


def test_non_monday_week_start_is_rejected() -> None:
    with pytest.raises(InvalidWeekStartError):
        _service(FakeWeeklyReportRepository()).get_week(
            FakeSession(),
            uuid4(),
            WEEK_START + timedelta(days=1),  # type: ignore[arg-type]
        )


def test_open_week_cannot_generate_final_report() -> None:
    repository = FakeWeeklyReportRepository()
    service = _service(repository, datetime(2026, 8, 7, 0, 0, tzinfo=UTC))
    with pytest.raises(WeekNotClosedError):
        service.create_report(
            FakeSession(),
            uuid4(),
            WEEK_START,
            _request(),
            uuid4(),  # type: ignore[arg-type]
        )


def test_report_uses_block_evidence_and_builds_non_penalty_aggregate() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = _evidence()
    response = _service(repository).create_report(
        FakeSession(),
        uuid4(),
        WEEK_START,
        _request(),
        uuid4(),  # type: ignore[arg-type]
    )
    assert response.counts.model_dump() == {
        "completed": 1,
        "partial": 1,
        "not_completed": 1,
        "stopped_for_safety": 1,
    }
    assert response.primary_miss_reason_code == "TIME_SHORTAGE"
    assert response.completion_rate == 0.25
    assert response.persistence_rate == 0.5
    assert response.negotiation_success_rate == 0.5
    assert response.adjustment_direction_code == "MIXED"
    assert "벌점" not in response.summary
    assert repository.last_report_values is not None
    snapshot = repository.last_report_values.input_snapshot
    assert snapshot["feedback_summary"] == {
        "difficulty_counts": {"APPROPRIATE": 1, "HARD": 1},
        "pain_report_count": 1,
    }
    assert "user_id" not in snapshot
    assert "session_id" not in snapshot


class RecordingNarrationAgent:
    def __init__(self) -> None:
        self.inputs: list[WeeklyReportNarrationInput] = []

    def interpret(self, report: WeeklyReportNarrationInput) -> WeeklyReportNarration:
        self.inputs.append(report)
        return WeeklyReportNarration(
            summary="주간 기록의 흐름을 살펴보고 다음 주에도 부담 없이 이어가 보세요.",
            decision_summary="조정된 루틴의 수행 결과와 미완료 사유를 함께 반영했습니다.",
            next_action="다음 주에는 가능한 시간에 맞춰 한 번의 운동부터 시작해 보세요.",
            source_code="LLM",
            model_code="test-model",
            prompt_version="weekly-report-narration-prompt-v1",
        )


class FailingNarrationAgent:
    def interpret(self, report: WeeklyReportNarrationInput) -> WeeklyReportNarration:
        del report
        raise TimeoutError


def test_agent_receives_deterministic_aggregate_and_only_replaces_narration() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = _evidence()
    agent = RecordingNarrationAgent()

    response = _service(repository, narration_agent=agent).create_report(
        FakeSession(), uuid4(), WEEK_START, _request(), uuid4()  # type: ignore[arg-type]
    )

    assert len(agent.inputs) == 1
    received = agent.inputs[0]
    assert repository.last_report_values is not None
    assert received.input_snapshot == repository.last_report_values.input_snapshot
    assert received.objective_metrics == {
        "counts": {
            "completed": 1,
            "partial": 1,
            "not_completed": 1,
            "stopped_for_safety": 1,
        },
        "completion_rate": 0.25,
        "persistence_rate": 0.5,
        "negotiation_success_rate": 0.5,
        "primary_miss_reason_code": "TIME_SHORTAGE",
        "adjustment_direction_code": "MIXED",
    }
    assert response.summary == "주간 기록의 흐름을 살펴보고 다음 주에도 부담 없이 이어가 보세요."
    assert response.counts.model_dump() == {
        "completed": 1,
        "partial": 1,
        "not_completed": 1,
        "stopped_for_safety": 1,
    }
    assert response.completion_rate == 0.25
    assert response.persistence_rate == 0.5
    assert response.agent_summaries == {
        "WEEKLY_REPORT_INTERPRETER": {
            "agent_type_code": "WEEKLY_REPORT_INTERPRETER",
            "source_code": "LLM",
            "model_code": "test-model",
            "prompt_version": "weekly-report-narration-prompt-v1",
            "fallback_reason_code": None,
            "input_schema_version": "weekly-report-input-v1",
            "input_hash": repository.last_report_values.input_hash,
        }
    }


def test_agent_failure_falls_back_without_changing_deterministic_statistics() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = _evidence()

    response = _service(repository, narration_agent=FailingNarrationAgent()).create_report(
        FakeSession(), uuid4(), WEEK_START, _request(), uuid4()  # type: ignore[arg-type]
    )

    assert response.counts.model_dump() == {
        "completed": 1,
        "partial": 1,
        "not_completed": 1,
        "stopped_for_safety": 1,
    }
    assert response.completion_rate == 0.25
    assert response.persistence_rate == 0.5
    assert response.negotiation_success_rate == 0.5
    assert response.agent_summaries is not None
    assert response.agent_summaries["WEEKLY_REPORT_INTERPRETER"]["source_code"] == "TEMPLATE"
    assert (
        response.agent_summaries["WEEKLY_REPORT_INTERPRETER"]["fallback_reason_code"]
        == "AGENT_FAILED"
    )


def test_same_closed_week_and_input_hash_returns_same_report_across_keys() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = _evidence()
    service = _service(repository)
    user_id = uuid4()
    first = service.create_report(
        FakeSession(),
        user_id,
        WEEK_START,
        _request(),
        uuid4(),  # type: ignore[arg-type]
    )
    retry = service.create_report(
        FakeSession(),
        user_id,
        WEEK_START,
        _request(),
        uuid4(),  # type: ignore[arg-type]
    )
    assert retry == first
    assert repository.created_report_count == 1

    repository.evidence = repository.evidence[:-1]
    with pytest.raises(ReportInputChangedError):
        service.create_report(
            FakeSession(),
            user_id,
            WEEK_START,
            _request(),
            uuid4(),  # type: ignore[arg-type]
        )


def test_unresolved_session_blocks_report_generation() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = (
        WeeklySessionEvidence(
            WEEK_START, "IN_PROGRESS", ("COMPLETED", "PENDING"), False, None, "KEEP"
        ),
    )
    with pytest.raises(WeekOutcomesIncompleteError):
        _service(repository).create_report(
            FakeSession(),
            uuid4(),
            WEEK_START,
            _request(),
            uuid4(),  # type: ignore[arg-type]
        )


def test_acknowledgement_is_explicit_idempotent_and_does_not_rewrite_time() -> None:
    repository = FakeWeeklyReportRepository()
    service = _service(repository)
    user_id = uuid4()
    report = service.create_report(
        FakeSession(),
        user_id,
        WEEK_START,
        _request(),
        uuid4(),  # type: ignore[arg-type]
    )
    first_time = CLOSED_NOW + timedelta(minutes=1)
    first = service.acknowledge_report(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        report.report_id,
        WeeklyReportAcknowledgementRequest(acknowledged_at=first_time),
        uuid4(),
    )
    retry = service.acknowledge_report(
        FakeSession(),  # type: ignore[arg-type]
        user_id,
        report.report_id,
        WeeklyReportAcknowledgementRequest(acknowledged_at=first_time + timedelta(minutes=2)),
        uuid4(),
    )
    assert first.status_code == "ACKNOWLEDGED"
    assert retry.acknowledged_at == first_time


def test_same_idempotency_key_with_changed_acknowledgement_is_rejected() -> None:
    repository = FakeWeeklyReportRepository()
    service = _service(repository)
    user_id = uuid4()
    report = service.create_report(
        FakeSession(),
        user_id,
        WEEK_START,
        _request(),
        uuid4(),  # type: ignore[arg-type]
    )
    key = uuid4()
    service.acknowledge_report(
        FakeSession(),
        user_id,
        report.report_id,
        WeeklyReportAcknowledgementRequest(acknowledged_at=CLOSED_NOW + timedelta(minutes=1)),
        key,  # type: ignore[arg-type]
    )
    with pytest.raises(IdempotencyKeyReusedError):
        service.acknowledge_report(
            FakeSession(),
            user_id,
            report.report_id,
            WeeklyReportAcknowledgementRequest(acknowledged_at=CLOSED_NOW + timedelta(minutes=2)),
            key,  # type: ignore[arg-type]
        )
