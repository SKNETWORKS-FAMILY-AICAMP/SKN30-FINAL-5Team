import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal, TypeVar, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.domain.rules.workout_execution import (
    WorkoutBlockStatusCode,
    WorkoutCompletionEvidence,
    derive_official_session_status,
)
from backend.app.modules.weekly_reports.codes import (
    WEEKLY_REPORT_ACK_ENDPOINT_CODE,
    WEEKLY_REPORT_ENDPOINT_CODE,
    WEEKLY_REPORT_INPUT_SCHEMA_VERSION,
    WEEKLY_REPORT_POLICY_VERSION,
)
from backend.app.modules.weekly_reports.narration import apply_narration
from backend.app.modules.weekly_reports.ports import (
    ReportValues,
    WeeklyReportNarrationAgentPort,
    WeeklyReportRepositoryPort,
    WeeklySessionEvidence,
    WeekRecord,
)
from backend.app.modules.weekly_reports.schemas import (
    WeeklyReportAcknowledgementRequest,
    WeeklyReportCreateRequest,
    WeeklyReportResponse,
    WeekResponse,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)

_WEEKDAY_CODES = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)
_TERMINAL_STATUS_CODES = frozenset({"COMPLETED", "PARTIAL", "NOT_COMPLETED", "STOPPED_FOR_SAFETY"})
_ADJUSTED_ACTION_CODES = frozenset({"DOWNSHIFT", "CHANGE", "RECOVERY"})
_FATIGUE_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2}


class WeeklyReportError(Exception):
    pass


class InvalidWeekStartError(WeeklyReportError):
    pass


class InvalidWeekTimezoneError(WeeklyReportError):
    pass


class WeekProfileRequiredError(WeeklyReportError):
    pass


class WeekNotClosedError(WeeklyReportError):
    pass


class WeekOutcomesIncompleteError(WeeklyReportError):
    pass


class WeekOutcomeInconsistentError(WeeklyReportError):
    pass


class ReportInputChangedError(WeeklyReportError):
    pass


class WeeklyReportNotFoundError(WeeklyReportError):
    pass


class WeeklyReportUnavailableError(WeeklyReportError):
    pass


class InvalidAcknowledgementTimeError(WeeklyReportError):
    pass


class IdempotencyKeyReusedError(WeeklyReportError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _request_hash(resource: dict[str, object], request: BaseModel) -> str:
    return _hash_payload({**resource, "body": request.model_dump(mode="json")})


class WeeklyReportService:
    def __init__(
        self,
        repository: WeeklyReportRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
        narration_agent: WeeklyReportNarrationAgentPort | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._narration_agent = narration_agent

    def get_week(self, session: Session, user_id: UUID, week_start: date) -> WeekResponse:
        self._validate_week_start(week_start)
        now = self._clock()
        with session.begin():
            week = self._resolve_week(session, user_id, week_start, now)
            return self._week_response(week)

    def create_report(
        self,
        session: Session,
        user_id: UUID,
        week_start: date,
        request: WeeklyReportCreateRequest,
        idempotency_key: UUID,
    ) -> WeeklyReportResponse:
        self._validate_week_start(week_start)
        request_hash = _request_hash({"week_start": week_start.isoformat()}, request)
        now = self._clock()
        with session.begin():
            self._repository.acquire_week_lock(session, user_id, week_start)
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_REPORT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if prior is not None:
                return prior
            week = self._resolve_week(session, user_id, week_start, now, lock_acquired=True)
            if week.status_code != "CLOSED":
                raise WeekNotClosedError
            evidence = self._repository.get_week_evidence(
                session, user_id, week.week_start, week.week_end
            )
            values = self._build_report_values(session, week, evidence, now)
            values = apply_narration(values, self._narration_agent)
            existing = self._repository.get_report_for_week(session, week.week_id)
            if existing is not None:
                if existing.input_hash != values.input_hash:
                    raise ReportInputChangedError
                response = self._response(existing.response_payload)
            else:
                stored = self._repository.create_report(session, week=week, values=values)
                response = self._response(stored.response_payload)
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_REPORT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
            return response

    def get_report(self, session: Session, user_id: UUID, report_id: UUID) -> WeeklyReportResponse:
        stored = self._repository.get_report_by_id(session, user_id, report_id)
        if stored is None:
            raise WeeklyReportNotFoundError
        return self._response(stored.response_payload)

    def acknowledge_report(
        self,
        session: Session,
        user_id: UUID,
        report_id: UUID,
        request: WeeklyReportAcknowledgementRequest,
        idempotency_key: UUID,
    ) -> WeeklyReportResponse:
        request_hash = _request_hash({"report_id": str(report_id)}, request)
        now = self._clock()
        with session.begin():
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_REPORT_ACK_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if prior is not None:
                return prior
            existing = self._repository.get_report_by_id(session, user_id, report_id)
            if existing is None:
                raise WeeklyReportNotFoundError
            existing_response = self._response(existing.response_payload)
            if existing_response.status_code == "ACKNOWLEDGED":
                response = existing_response
            else:
                if request.acknowledged_at < existing_response.generated_at:
                    raise InvalidAcknowledgementTimeError
                stored = self._repository.acknowledge_report(
                    session,
                    user_id=user_id,
                    report_id=report_id,
                    acknowledged_at=request.acknowledged_at,
                )
                if stored is None:
                    raise WeeklyReportNotFoundError
                response = self._response(stored.response_payload)
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_REPORT_ACK_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
            return response

    def _resolve_week(
        self,
        session: Session,
        user_id: UUID,
        week_start: date,
        now: datetime,
        *,
        lock_acquired: bool = False,
    ) -> WeekRecord:
        if not lock_acquired:
            self._repository.acquire_week_lock(session, user_id, week_start)
        existing = self._repository.get_week(session, user_id, week_start)
        if existing is not None:
            local_date, _ = self._local_date(existing.timezone, now)
            if existing.status_code == "OPEN" and local_date > existing.week_end:
                return self._repository.close_week(
                    session,
                    existing.week_id,
                    self._logical_closed_at(existing.week_end, existing.timezone),
                )
            return existing
        profile = self._repository.get_week_profile(session, user_id, week_start)
        if profile is None:
            raise WeekProfileRequiredError
        local_date, _ = self._local_date(profile.timezone, now)
        week_end = week_start + timedelta(days=6)
        is_closed = local_date > week_end
        cold_start = not profile.has_prior_week
        return self._repository.create_week(
            session,
            week_id=self._uuid_factory(),
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            timezone=profile.timezone,
            target_workout_count=profile.target_workout_count,
            plan_origin_code="COLD_START" if cold_start else "WEEKLY_REPORT",
            cold_start_applied=cold_start,
            status_code="CLOSED" if is_closed else "OPEN",
            closed_at=(self._logical_closed_at(week_end, profile.timezone) if is_closed else None),
            now=now,
        )

    def _build_report_values(
        self,
        session: Session,
        week: WeekRecord,
        evidence_rows: tuple[WeeklySessionEvidence, ...],
        now: datetime,
    ) -> ReportValues:
        counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        weekday_failures: defaultdict[str, Counter[str]] = defaultdict(Counter)
        difficulty_counts: Counter[str] = Counter()
        fatigue_by_date: dict[date, str] = {}
        pain_checkin_dates: set[date] = set()
        pain_report_count = 0
        workout_pain_or_safety_stop_count = 0
        outcome_reason_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
        recommendation_action_counts: Counter[str] = Counter()
        recommendation_context_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
        adjusted_total = 0
        adjusted_success = 0
        total_workout_seconds = 0
        calorie_values: list[float] = []
        intensity_codes: list[str] = []
        training_type_codes: list[str] = []
        exercise_names: list[str] = []
        for row in evidence_rows:
            if not row.block_status_codes:
                raise WeekOutcomeInconsistentError
            # A session left open is not a reason to withhold the whole report.
            # The week is closed before this runs, so nothing in it can be
            # resumed any more, and the official status has always come from the
            # completed blocks rather than from the stored code -- that is what
            # the line below computes for every row, closed or not. The stored
            # code is only cross-checked when there is one to cross-check: a user
            # who stops mid-session and never returns leaves `IN_PROGRESS`
            # behind, and refusing the report there would also block the next
            # week's plan, which the report gates.
            official_status = derive_official_session_status(
                WorkoutCompletionEvidence(
                    block_status_codes=tuple(
                        WorkoutBlockStatusCode(code) for code in row.block_status_codes
                    ),
                    safety_stopped=row.safety_stopped,
                )
            ).value
            if (
                row.stored_status_code in _TERMINAL_STATUS_CODES
                and official_status != row.stored_status_code
            ):
                raise WeekOutcomeInconsistentError
            if official_status == "NOT_COMPLETED":
                if row.not_completed_reason_code is None:
                    raise WeekOutcomesIncompleteError
                reason_counts[row.not_completed_reason_code] += 1
            counts[official_status] += 1
            recommendation_action_counts[row.selected_action_code] += 1
            if row.fatigue_level_code is not None:
                recommendation_context_counts[row.selected_action_code][
                    f"{row.fatigue_level_code}_FATIGUE"
                ] += 1
            if row.daily_pain_present:
                recommendation_context_counts[row.selected_action_code]["PAIN_PRESENT"] += 1
            reason_code = row.not_completed_reason_code
            if (
                reason_code is None
                and official_status == "STOPPED_FOR_SAFETY"
                and row.stop_reason_code == "PAIN_OR_ABNORMAL_RESPONSE"
            ):
                # The safety-stop transition itself is canonical evidence. Other
                # stop codes are control-flow labels and must not be presented as
                # the user's feedback reason.
                reason_code = row.stop_reason_code
            if reason_code is not None and official_status != "COMPLETED":
                outcome_reason_counts[official_status][reason_code] += 1
            if official_status in {"PARTIAL", "NOT_COMPLETED", "STOPPED_FOR_SAFETY"}:
                weekday_failures[_WEEKDAY_CODES[row.local_date.weekday()]][official_status] += 1
            if row.selected_action_code in _ADJUSTED_ACTION_CODES:
                adjusted_total += 1
                if official_status in {"COMPLETED", "PARTIAL"}:
                    adjusted_success += 1
            if row.feedback_difficulty_code is not None:
                difficulty_counts[row.feedback_difficulty_code] += 1
            if row.fatigue_level_code in _FATIGUE_RANK:
                fatigue_by_date[row.local_date] = row.fatigue_level_code
            if row.daily_pain_present:
                pain_checkin_dates.add(row.local_date)
            if row.pain_occurred is True:
                pain_report_count += 1
            if row.pain_occurred is True or official_status == "STOPPED_FOR_SAFETY":
                workout_pain_or_safety_stop_count += 1
            total_workout_seconds += row.progress_seconds
            if row.estimated_calories_burned is not None:
                calorie_values.append(row.estimated_calories_burned)
            # These values come from completed exercise blocks only. A plan item
            # that was never checked off must not affect a performed-workout metric.
            intensity_codes.extend(row.intensity_codes)
            training_type_codes.extend(row.training_type_codes)
            exercise_names.extend(row.exercise_names)

        completed = counts["COMPLETED"]
        partial = counts["PARTIAL"]
        not_completed = counts["NOT_COMPLETED"]
        stopped = counts["STOPPED_FOR_SAFETY"]
        target = week.target_workout_count
        completion_rate = round(min(completed / target, 1.0), 6)
        persistence_rate = round(min((completed + partial) / target, 1.0), 6)
        negotiation_rate = (
            None if adjusted_total == 0 else round(adjusted_success / adjusted_total, 6)
        )
        primary_reason = (
            None
            if not reason_counts
            else min(reason_counts, key=lambda code: (-reason_counts[code], code))
        )
        weekday_summary = {
            code: {
                "partial": values["PARTIAL"],
                "not_completed": values["NOT_COMPLETED"],
                "stopped_for_safety": values["STOPPED_FOR_SAFETY"],
            }
            for code, values in sorted(weekday_failures.items())
        }
        blocker_codes = [
            code for code, _ in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        total_estimated_calories_burned = (
            None if not calorie_values else round(sum(calorie_values), 2)
        )
        fatigue_counts = Counter(fatigue_by_date.values())
        dated_fatigue = sorted(fatigue_by_date.items())
        pain_checkin_count = len(pain_checkin_dates)
        average_intensity_code = self._average_intensity_code(intensity_codes)
        most_performed_training_type_code = self._mode_code(training_type_codes)
        most_performed_exercise_name = self._mode_code(exercise_names)
        routine_difficulty_code = self._mode_code(list(difficulty_counts.elements()))
        fatigue_change_code = self._fatigue_change_code(dated_fatigue)
        prior_completed_count = self._repository.get_prior_week_completed_count(
            session, week.user_id, week.week_start
        )
        completed_count_change = (
            None if prior_completed_count is None else completed - prior_completed_count
        )
        highlight_codes = self._highlight_codes(
            completed=completed,
            partial=partial,
            adjusted_success=adjusted_success,
        )
        improvement_codes = self._improvement_codes(
            partial=partial,
            not_completed=not_completed,
            stopped=stopped,
        )
        count_snapshot = {
            "completed": completed,
            "partial": partial,
            "not_completed": not_completed,
            # Both names carry the same number this release. The legacy key stays so a
            # reader written against v1 keeps working while clients move over.
            "stopped_for_safety": stopped,
            "safety_stopped_session_count": stopped,
        }
        snapshot: dict[str, Any] = {
            "input_schema_version": WEEKLY_REPORT_INPUT_SCHEMA_VERSION,
            "report_policy_version": WEEKLY_REPORT_POLICY_VERSION,
            "week": {
                "week_start": week.week_start.isoformat(),
                "week_end": week.week_end.isoformat(),
                "timezone": week.timezone,
                "target_workout_count": target,
            },
            "official_outcome_counts": count_snapshot,
            "not_completed_reason_counts": dict(sorted(reason_counts.items())),
            "weekday_failure_summary": weekday_summary,
            "adjusted_selection_outcomes": {
                "total": adjusted_total,
                "completed_or_partial": adjusted_success,
            },
            "feedback_summary": {
                "difficulty_counts": dict(sorted(difficulty_counts.items())),
                "pain_report_count": pain_report_count,
            },
            "condition_summary": {
                "checkin_count": sum(fatigue_counts.values()),
                "fatigue_level_counts": dict(sorted(fatigue_counts.items())),
                "fatigue_change_code": fatigue_change_code,
                "pain_checkin_count": pain_checkin_count,
                "workout_pain_or_safety_stop_count": workout_pain_or_safety_stop_count,
            },
            "outcome_reason_summary": {
                status.lower(): dict(sorted(reasons.items()))
                for status, reasons in sorted(outcome_reason_counts.items())
            },
            "recommendation_action_counts": dict(sorted(recommendation_action_counts.items())),
            "recommendation_context_counts": {
                action: dict(sorted(contexts.items()))
                for action, contexts in sorted(recommendation_context_counts.items())
            },
            "weekly_metrics": {
                "total_workout_seconds": total_workout_seconds,
                "total_estimated_calories_burned": total_estimated_calories_burned,
                "average_intensity_code": average_intensity_code,
                "most_performed_training_type_code": most_performed_training_type_code,
                "most_performed_exercise_name": most_performed_exercise_name,
                "routine_difficulty_code": routine_difficulty_code,
                "completed_count_change": completed_count_change,
                "highlight_codes": highlight_codes,
                "improvement_codes": improvement_codes,
            },
        }
        pattern_summary = {
            "high_completion_windows": [],
            "high_completion_exercise_types": [],
            "high_completion_intensity_codes": [],
            "blocker_reason_codes": blocker_codes,
        }
        has_mixed_outcomes = partial > 0 or not_completed > 0 or stopped > 0
        direction = "MIXED" if has_mixed_outcomes else "MAINTAIN"
        if stopped:
            next_action = "다음 계획을 시작하기 전에 현재 상태를 다시 확인해주세요."
        elif not_completed:
            next_action = "다음 주에는 기록한 미수행 이유를 반영해 실행 가능한 계획을 확인해주세요."
        else:
            next_action = "다음 주에도 실행 가능한 시간에 첫 운동을 시작해보세요."
        decision_summary = (
            f"조정된 루틴 {adjusted_total}회 중 {adjusted_success}회에서 "
            "하나 이상의 계획 블록을 완료했습니다."
            if adjusted_total
            else "저장된 최종 루틴 수행 결과를 계획 블록 체크 기준으로 집계했습니다."
        )
        summary = (
            f"이번 주 목표 {target}회 중 {completed}회를 완료하고 "
            f"{partial}회는 일부 수행했으며, 미수행 {not_completed}회와 "
            f"안전 중단 {stopped}회를 기록했습니다."
        )
        next_week_recommendation = {
            "intensity": self._template_intensity_recommendation(routine_difficulty_code),
            "volume": self._template_volume_recommendation(partial, not_completed),
            "duration": self._template_duration_recommendation(reason_counts),
            "pain_response": self._template_pain_recommendation(
                pain_checkin_count=pain_checkin_count,
                workout_pain_or_safety_stop_count=workout_pain_or_safety_stop_count,
            ),
        }
        return ReportValues(
            report_id=self._uuid_factory(),
            input_schema_version=WEEKLY_REPORT_INPUT_SCHEMA_VERSION,
            input_snapshot=snapshot,
            input_hash=_hash_payload(snapshot),
            completed_count=completed,
            partial_count=partial,
            not_completed_count=not_completed,
            stopped_for_safety=stopped,
            safety_stopped_session_count=stopped,
            primary_miss_reason_code=primary_reason,
            completion_rate=completion_rate,
            persistence_rate=persistence_rate,
            negotiation_success_rate=negotiation_rate,
            weekday_failure_summary=weekday_summary,
            high_completion_windows=[],
            pattern_summary=pattern_summary,
            decision_summary=decision_summary,
            adjustment_direction_code=direction,
            next_action=next_action,
            agent_summaries=None,
            summary=summary,
            total_workout_seconds=total_workout_seconds,
            total_estimated_calories_burned=total_estimated_calories_burned,
            average_intensity_code=average_intensity_code,
            most_performed_training_type_code=most_performed_training_type_code,
            most_performed_exercise_name=most_performed_exercise_name,
            completed_count_change=completed_count_change,
            highlight_codes=highlight_codes,
            improvement_codes=improvement_codes,
            routine_difficulty_code=routine_difficulty_code,
            condition_summary=snapshot["condition_summary"],
            outcome_reason_summary=snapshot["outcome_reason_summary"],
            recommendation_action_counts=snapshot["recommendation_action_counts"],
            next_week_recommendation=next_week_recommendation,
            coach_message=summary,
            report_policy_version=WEEKLY_REPORT_POLICY_VERSION,
            generated_at=now,
        )

    @staticmethod
    def _mode_code(codes: list[str]) -> str | None:
        if not codes:
            return None
        counts = Counter(codes)
        return min(counts, key=lambda code: (-counts[code], code))

    @staticmethod
    def _fatigue_change_code(values: list[tuple[date, str]]) -> str:
        if len(values) < 2:
            return "INSUFFICIENT_DATA"
        ordered = sorted(values, key=lambda item: item[0])
        first_rank = _FATIGUE_RANK[ordered[0][1]]
        last_rank = _FATIGUE_RANK[ordered[-1][1]]
        if last_rank < first_rank:
            return "IMPROVED"
        if last_rank > first_rank:
            return "DECLINED"
        return "STABLE"

    @staticmethod
    def _template_intensity_recommendation(difficulty_code: str | None) -> str:
        if difficulty_code == "HARD":
            return "체감 난이도를 반영해 무리 없이 이어갈 수 있는 강도로 조정할게요."
        if difficulty_code == "EASY":
            return "쉬웠다는 피드백을 바탕으로 현재 상태에 맞는 강도를 다시 확인할게요."
        return "잘 맞았던 강도를 기준으로 다음 주 컨디션에 맞춰 조정할게요."

    @staticmethod
    def _template_volume_recommendation(partial: int, not_completed: int) -> str:
        if partial or not_completed:
            return "부분 수행과 휴식 기록을 반영해 끝까지 수행 가능한 운동량을 우선할게요."
        return "완료한 운동량을 기준으로 다음 주에도 안정적으로 이어가게 할게요."

    @staticmethod
    def _template_duration_recommendation(reason_counts: Counter[str]) -> str:
        if reason_counts["TIME_SHORTAGE"] or reason_counts["SCHEDULE_CHANGE"]:
            return "시간과 일정 사유를 반영하되 요청한 운동 시간 범위 안에서 구성할게요."
        return "기록된 수행 시간을 참고해 요청한 운동 시간을 유지할게요."

    @staticmethod
    def _template_pain_recommendation(
        *, pain_checkin_count: int, workout_pain_or_safety_stop_count: int
    ) -> str:
        if pain_checkin_count or workout_pain_or_safety_stop_count:
            return "통증이나 이상 반응이 기록된 부위의 부담을 피하고 안전 기준을 우선할게요."
        return "새로운 통증이나 이상 반응이 있으면 즉시 멈추고 다시 확인할게요."

    @staticmethod
    def _average_intensity_code(codes: list[str]) -> str | None:
        """Return the closest supported intensity code from completed blocks.

        The approved catalog currently exposes LOW and MODERATE. Unknown legacy
        codes are excluded rather than silently assigning them a load score.
        A midpoint rounds up, which makes the tie break explicit and reproducible.
        """

        scores = {"LOW": 1, "MODERATE": 2}
        values = [scores[code] for code in codes if code in scores]
        if not values:
            return None
        return "MODERATE" if sum(values) / len(values) >= 1.5 else "LOW"

    @staticmethod
    def _highlight_codes(*, completed: int, partial: int, adjusted_success: int) -> list[str]:
        codes: list[str] = []
        if completed:
            codes.append("COMPLETED_SESSION_RECORDED")
        if partial:
            codes.append("PARTIAL_SESSION_PROGRESS_RECORDED")
        if adjusted_success:
            codes.append("ADJUSTED_PLAN_PROGRESS_RECORDED")
        return codes

    @staticmethod
    def _improvement_codes(*, partial: int, not_completed: int, stopped: int) -> list[str]:
        codes: list[str] = []
        if stopped:
            codes.append("SAFETY_STOPPED_SESSION_RECORDED")
        if not_completed:
            codes.append("MISSED_SESSION_PATTERN_RECORDED")
        if partial:
            codes.append("PARTIAL_SESSION_PATTERN_RECORDED")
        return codes

    def _prior_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
    ) -> WeeklyReportResponse | None:
        self._repository.acquire_idempotency_lock(session, user_id, endpoint_code, idempotency_key)
        prior = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if prior is None:
            return None
        if prior.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return self._response(prior.response_payload)

    def _save_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
        response: WeeklyReportResponse,
        now: datetime,
    ) -> None:
        self._repository.save_idempotency_record(
            session,
            user_id=user_id,
            endpoint_code=endpoint_code,
            key=idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json"),
            now=now,
        )

    @staticmethod
    def _validate_week_start(week_start: date) -> None:
        if week_start.weekday() != 0:
            raise InvalidWeekStartError

    @staticmethod
    def _local_date(timezone_name: str, now: datetime) -> tuple[date, ZoneInfo]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        try:
            timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise InvalidWeekTimezoneError from exc
        return now.astimezone(timezone).date(), timezone

    @staticmethod
    def _logical_closed_at(week_end: date, timezone_name: str) -> datetime:
        try:
            timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise InvalidWeekTimezoneError from exc
        return datetime.combine(week_end + timedelta(days=1), time.min, timezone).astimezone(UTC)

    @staticmethod
    def _week_response(week: WeekRecord) -> WeekResponse:
        return WeekResponse(
            week_id=week.week_id,
            week_start=week.week_start,
            week_end=week.week_end,
            timezone=week.timezone,
            target_workout_count=week.target_workout_count,
            plan_origin_code=cast(Literal["COLD_START", "WEEKLY_REPORT"], week.plan_origin_code),
            cold_start_applied=week.cold_start_applied,
            status_code=cast(Literal["OPEN", "CLOSED"], week.status_code),
            closed_at=week.closed_at,
            report_id=week.report_id,
            report_status_code=cast(
                Literal["GENERATED", "ACKNOWLEDGED", "FAILED"] | None,
                week.report_status_code,
            ),
        )

    @staticmethod
    def _response(payload: dict[str, Any]) -> WeeklyReportResponse:
        if payload.get("status_code") == "FAILED":
            raise WeeklyReportUnavailableError
        return WeeklyReportResponse.model_validate(payload)


__all__ = [
    "IdempotencyKeyReusedError",
    "InvalidAcknowledgementTimeError",
    "InvalidWeekStartError",
    "InvalidWeekTimezoneError",
    "ReportInputChangedError",
    "WeekNotClosedError",
    "WeekOutcomeInconsistentError",
    "WeekOutcomesIncompleteError",
    "WeekProfileRequiredError",
    "WeeklyReportNotFoundError",
    "WeeklyReportService",
    "WeeklyReportUnavailableError",
]
