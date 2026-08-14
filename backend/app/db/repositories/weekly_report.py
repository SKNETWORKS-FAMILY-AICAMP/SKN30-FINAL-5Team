from datetime import date, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.profile import MutationIdempotencyRecord, UserProfile
from backend.app.db.models.weekly_report import UserWeek, WeeklyReport
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutFeedback,
    WorkoutSession,
    WorkoutSkipFeedback,
)
from backend.app.modules.weekly_reports.codes import WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION
from backend.app.modules.weekly_reports.ports import (
    IdempotencyRecord,
    ReportValues,
    StoredReport,
    WeeklySessionEvidence,
    WeekProfile,
    WeekRecord,
)


class WeeklyReportRepository:
    def acquire_week_lock(self, session: Session, user_id: UUID, week_start: date) -> None:
        lock_key = int.from_bytes(
            sha256(f"weekly-report:{user_id}:{week_start.isoformat()}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def acquire_idempotency_lock(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> None:
        lock_key = int.from_bytes(
            sha256(f"{user_id}:{endpoint_code}:{key}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_idempotency_record(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> IdempotencyRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == endpoint_code,
                MutationIdempotencyRecord.idempotency_key == key,
            )
        )
        if row is None:
            return None
        return IdempotencyRecord(row.request_hash, row.response_payload)

    def save_idempotency_record(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None:
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=endpoint_code,
                idempotency_key=key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )
        session.flush()

    def get_week_profile(
        self, session: Session, user_id: UUID, week_start: date
    ) -> WeekProfile | None:
        profile = session.get(UserProfile, user_id)
        if profile is None:
            return None
        has_prior_week = (
            session.scalar(
                select(UserWeek.id)
                .where(
                    UserWeek.user_id == user_id,
                    UserWeek.week_start_local_date < week_start,
                )
                .limit(1)
            )
            is not None
        )
        return WeekProfile(
            timezone=profile.timezone,
            target_workout_count=profile.desired_weekly_workout_count,
            has_prior_week=has_prior_week,
        )

    def get_week(self, session: Session, user_id: UUID, week_start: date) -> WeekRecord | None:
        row = session.scalar(
            select(UserWeek)
            .options(selectinload(UserWeek.report))
            .where(
                UserWeek.user_id == user_id,
                UserWeek.week_start_local_date == week_start,
            )
        )
        return None if row is None else self._week_record(row)

    def create_week(
        self,
        session: Session,
        *,
        week_id: UUID,
        user_id: UUID,
        week_start: date,
        week_end: date,
        timezone: str,
        target_workout_count: int,
        plan_origin_code: str,
        cold_start_applied: bool,
        status_code: str,
        closed_at: datetime | None,
        now: datetime,
    ) -> WeekRecord:
        session.add(
            UserWeek(
                id=week_id,
                user_id=user_id,
                week_start_local_date=week_start,
                week_end_local_date=week_end,
                timezone=timezone,
                target_workout_count=target_workout_count,
                plan_origin_code=plan_origin_code,
                cold_start_applied=cold_start_applied,
                status_code=status_code,
                closed_at=closed_at,
                created_at=now,
            )
        )
        session.flush()
        row = self.get_week(session, user_id, week_start)
        if row is None:
            raise LookupError("created user week could not be reloaded")
        return row

    def close_week(self, session: Session, week_id: UUID, closed_at: datetime) -> WeekRecord:
        row = session.scalar(select(UserWeek).where(UserWeek.id == week_id).with_for_update())
        if row is None:
            raise LookupError("locked user week disappeared")
        row.status_code = "CLOSED"
        row.closed_at = closed_at
        session.flush()
        reloaded = self.get_week(session, row.user_id, row.week_start_local_date)
        if reloaded is None:
            raise LookupError("closed user week could not be reloaded")
        return reloaded

    def get_week_evidence(
        self, session: Session, user_id: UUID, week_start: date, week_end: date
    ) -> tuple[WeeklySessionEvidence, ...]:
        rows = session.execute(
            select(
                WorkoutSession,
                DecisionRun.local_date,
                DecisionSelection.selected_action_code,
                WorkoutSkipFeedback.reason_code,
                WorkoutFeedback.difficulty_code,
                WorkoutFeedback.pain_occurred,
            )
            .options(
                selectinload(WorkoutSession.items),
                selectinload(WorkoutSession.safety_events),
            )
            .join(
                DecisionSelection,
                DecisionSelection.id == WorkoutSession.decision_selection_id,
            )
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .outerjoin(
                WorkoutSkipFeedback,
                WorkoutSkipFeedback.workout_session_id == WorkoutSession.id,
            )
            .outerjoin(
                WorkoutFeedback,
                WorkoutFeedback.workout_session_id == WorkoutSession.id,
            )
            .where(
                WorkoutSession.user_id == user_id,
                DecisionRun.local_date >= week_start,
                DecisionRun.local_date <= week_end,
            )
            .order_by(DecisionRun.local_date, WorkoutSession.id)
        ).all()
        return tuple(
            WeeklySessionEvidence(
                local_date=local_date,
                stored_status_code=workout.status_code,
                block_status_codes=tuple(sorted(item.status_code for item in workout.items)),
                safety_stopped=any(
                    event.resulting_action_code in {"REST", "STOP_AND_SEEK_HELP"}
                    for event in workout.safety_events
                ),
                not_completed_reason_code=reason_code,
                selected_action_code=selected_action_code,
                feedback_difficulty_code=difficulty_code,
                pain_occurred=pain_occurred,
            )
            for (
                workout,
                local_date,
                selected_action_code,
                reason_code,
                difficulty_code,
                pain_occurred,
            ) in rows
        )

    def get_report_for_week(self, session: Session, week_id: UUID) -> StoredReport | None:
        report = session.scalar(select(WeeklyReport).where(WeeklyReport.user_week_id == week_id))
        if report is None:
            return None
        week = session.get(UserWeek, week_id)
        if week is None:
            raise LookupError("weekly report references a missing user week")
        return self._stored_report(report, week)

    def get_report_by_id(
        self, session: Session, user_id: UUID, report_id: UUID
    ) -> StoredReport | None:
        result = session.execute(
            select(WeeklyReport, UserWeek)
            .join(UserWeek, UserWeek.id == WeeklyReport.user_week_id)
            .where(WeeklyReport.id == report_id, UserWeek.user_id == user_id)
        ).one_or_none()
        if result is None:
            return None
        report, week = result
        return self._stored_report(report, week)

    def create_report(
        self, session: Session, *, week: WeekRecord, values: ReportValues
    ) -> StoredReport:
        report = WeeklyReport(
            id=values.report_id,
            user_week_id=week.week_id,
            status_code="GENERATED",
            input_schema_version=values.input_schema_version,
            input_snapshot=values.input_snapshot,
            input_hash=values.input_hash,
            completed_count=values.completed_count,
            partial_count=values.partial_count,
            not_completed_count=values.not_completed_count,
            stopped_for_safety=values.stopped_for_safety,
            primary_miss_reason_code=values.primary_miss_reason_code,
            completion_rate=values.completion_rate,
            persistence_rate=values.persistence_rate,
            negotiation_success_rate=values.negotiation_success_rate,
            weekday_failure_summary=values.weekday_failure_summary,
            high_completion_windows=values.high_completion_windows,
            pattern_summary=values.pattern_summary,
            decision_summary=values.decision_summary,
            adjustment_direction_code=values.adjustment_direction_code,
            next_action=values.next_action,
            agent_summaries=values.agent_summaries,
            summary=values.summary,
            report_policy_version=values.report_policy_version,
            generated_at=values.generated_at,
            acknowledged_at=None,
        )
        session.add(report)
        session.flush()
        return self._stored_report(report, self._week_model(session, week.week_id))

    def acknowledge_report(
        self,
        session: Session,
        *,
        user_id: UUID,
        report_id: UUID,
        acknowledged_at: datetime,
    ) -> StoredReport | None:
        result = session.execute(
            select(WeeklyReport, UserWeek)
            .join(UserWeek, UserWeek.id == WeeklyReport.user_week_id)
            .where(WeeklyReport.id == report_id, UserWeek.user_id == user_id)
            .with_for_update()
        ).one_or_none()
        if result is None:
            return None
        report, week = result
        if report.status_code == "GENERATED":
            report.status_code = "ACKNOWLEDGED"
            report.acknowledged_at = acknowledged_at
            session.flush()
        return self._stored_report(report, week)

    @staticmethod
    def _week_record(row: UserWeek) -> WeekRecord:
        return WeekRecord(
            week_id=row.id,
            user_id=row.user_id,
            week_start=row.week_start_local_date,
            week_end=row.week_end_local_date,
            timezone=row.timezone,
            target_workout_count=row.target_workout_count,
            plan_origin_code=row.plan_origin_code,
            cold_start_applied=row.cold_start_applied,
            status_code=row.status_code,
            closed_at=row.closed_at,
            report_id=None if row.report is None else row.report.id,
            report_status_code=None if row.report is None else row.report.status_code,
        )

    @staticmethod
    def _week_model(session: Session, week_id: UUID) -> UserWeek:
        week = session.get(UserWeek, week_id)
        if week is None:
            raise LookupError("weekly report references a missing user week")
        return week

    @staticmethod
    def _stored_report(report: WeeklyReport, week: UserWeek) -> StoredReport:
        return StoredReport(
            input_hash=report.input_hash,
            response_payload={
                "report_id": report.id,
                "week_start": week.week_start_local_date,
                "week_end": week.week_end_local_date,
                "status_code": report.status_code,
                "counts": {
                    "completed": report.completed_count,
                    "partial": report.partial_count,
                    "not_completed": report.not_completed_count,
                    "stopped_for_safety": report.stopped_for_safety,
                },
                "primary_miss_reason_code": report.primary_miss_reason_code,
                "completion_rate": report.completion_rate,
                "persistence_rate": report.persistence_rate,
                "negotiation_success_rate": report.negotiation_success_rate,
                "weekday_failure_summary": report.weekday_failure_summary,
                "pattern_summary": report.pattern_summary,
                "decision_summary": report.decision_summary,
                "adjustment_direction_code": report.adjustment_direction_code,
                "next_action": report.next_action,
                "agent_summaries": report.agent_summaries,
                "summary": report.summary,
                "acknowledged_at": report.acknowledged_at,
                "generated_at": report.generated_at,
            },
        )


__all__ = ["WeeklyReportRepository"]
