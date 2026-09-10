import { describe, expect, it, jest } from '@jest/globals';
import { StrictMode, useState } from 'react';
import { Dimensions } from 'react-native';
import {
  fireEvent,
  act,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import type {
  WeeklyPlanRevisionResponse,
  WeeklyReportResponse,
} from '../src/api/types';
import { WeeklyReportScreen } from '../src/features/weekly/WeeklyReportScreen';
import { CALENDAR_DAY_VISUALS } from '../src/features/home/homeSecondaryModel';

const REPORT: WeeklyReportResponse = {
  report_id: 'report-1',
  week_start: '2026-08-03',
  week_end: '2026-08-09',
  status_code: 'GENERATED',
  counts: {
    completed: 3,
    partial: 1,
    not_completed: 1,
    stopped_for_safety: 0,
    safety_stopped_session_count: 0,
  },
  total_workout_seconds: 3900,
  total_estimated_calories_burned: 245.5,
  average_intensity_code: 'MODERATE',
  most_performed_training_type_code: 'STRENGTH',
  most_performed_exercise_name: '스쿼트',
  completed_count_change: 1,
  highlight_codes: ['COMPLETED_SESSION_RECORDED'],
  improvement_codes: ['MISSED_SESSION_PATTERN_RECORDED'],
  routine_difficulty_code: 'APPROPRIATE',
  condition_summary: {
    checkin_count: 4,
    fatigue_level_counts: { HIGH: 1, LOW: 1, MODERATE: 2 },
    fatigue_change_code: 'IMPROVED',
    pain_checkin_count: 1,
    workout_pain_or_safety_stop_count: 0,
  },
  outcome_reason_summary: {
    partial: { TIME_SHORTAGE: 1 },
    not_completed: { SCHEDULE_CHANGE: 1 },
  },
  recommendation_action_counts: { KEEP: 3, DOWNSHIFT: 2 },
  adjustment_summary:
    '컨디션과 수행 피드백을 반영해 실제 추천의 부담을 조정했어요.',
  next_week_recommendation: {
    intensity: '잘 맞았던 강도는 유지할게요.',
    volume: '완료 가능한 운동량을 우선할게요.',
    duration: '요청한 운동 시간을 기준으로 구성할게요.',
    pain_response: '통증 신호에는 안전 기준을 우선할게요.',
  },
  coach_message:
    '이번 주에는 가능한 만큼 꾸준히 움직였어요. 다음 주에도 무리 없이 이어가요.',
  weekday_failure_summary: {
    THURSDAY: {
      partial: 0,
      not_completed: 1,
      stopped_for_safety: 0,
    },
  },
  pattern_summary: {
    high_completion_windows: [],
    high_completion_exercise_types: [],
    high_completion_intensity_codes: [],
    blocker_reason_codes: ['SCHEDULE_CHANGE'],
  },
  agent_summaries: null,
  primary_miss_reason_code: 'SCHEDULE_CHANGE',
  completion_rate: 0.75,
  persistence_rate: 1,
  negotiation_success_rate: null,
  decision_summary: '저장된 결과를 집계했어요.',
  adjustment_direction_code: 'MIXED',
  next_action: '다음 주에도 이어가 보세요.',
  summary: '선택한 주의 저장된 리포트입니다.',
  acknowledged_at: null,
  generated_at: '2026-08-10T00:00:00+09:00',
};

const NEXT_PLAN: WeeklyPlanRevisionResponse = {
  revision_id: 'revision-next',
  week_start: '2026-08-10',
  week_end: '2026-08-16',
  revision_sequence: 1,
  ai_revision_count: 0,
  source_code: 'INITIAL',
  source_weekly_report_id: REPORT.report_id,
  safety_status_code: 'PASS',
  routine: {
    id: 'routine-next',
    version: 2,
    goal_code: 'GENERAL_FITNESS',
    status_code: 'ACTIVE',
    effective_from: '2026-08-10',
    catalog_version: 'catalog-v1',
    days: [
      {
        id: 'day-next',
        sequence: 1,
        title: '전신 운동',
        training_type_code: 'STRENGTH',
        body_focus_code: 'FULL_BODY',
        requested_duration_minutes: 30,
        estimated_duration_seconds: 1800,
        estimated_calories_burned: null,
        items: [],
      },
    ],
    created_at: '2026-08-10T09:03:00+09:00',
  },
  selected_location_code: 'HOME',
  finalized: true,
  finalized_at: '2026-08-10T09:03:00+09:00',
  revision_reason_codes: ['REVISION_ALLOWED'],
  finalization_reason_codes: ['FINALIZE_ALLOWED'],
  created_at: '2026-08-10T09:03:00+09:00',
};

function renderExistingReport(report: WeeklyReportResponse = REPORT) {
  return render(
    <WeeklyReportScreen
      api={
        {
          getWeek: async () => ({
            week_id: 'week-1',
            week_start: report.week_start,
            week_end: report.week_end,
            timezone: 'Asia/Seoul',
            target_workout_count: 4,
            plan_origin_code: 'WEEKLY_REPORT',
            cold_start_applied: false,
            status_code: 'CLOSED',
            closed_at: '2026-08-10T00:00:00+09:00',
            report_id: report.report_id,
            report_status_code: report.status_code,
          }),
          getWeeklyReport: async () => report,
          acknowledgeWeeklyReport: async () => ({
            ...report,
            status_code: 'ACKNOWLEDGED',
            acknowledged_at: '2026-08-10T09:02:00+09:00',
          }),
        } as unknown as Api
      }
      weekStart={report.week_start}
      onBack={jest.fn()}
    />,
  );
}

describe('WeeklyReportScreen selected week', () => {
  function automaticApi() {
    return {
      getWeek: jest.fn<Api['getWeek']>(async () => ({
        week_id: 'week-1',
        week_start: REPORT.week_start,
        week_end: REPORT.week_end,
        timezone: 'Asia/Seoul',
        target_workout_count: 4,
        plan_origin_code: 'WEEKLY_REPORT',
        cold_start_applied: false,
        status_code: 'CLOSED',
        closed_at: '2026-08-10T00:00:00+09:00',
        report_id: REPORT.report_id,
        report_status_code: 'GENERATED',
      })),
      getWeeklyReport: jest.fn<Api['getWeeklyReport']>(async () => REPORT),
      acknowledgeWeeklyReport: jest.fn<Api['acknowledgeWeeklyReport']>(
        async () => ({
          ...REPORT,
          status_code: 'ACKNOWLEDGED',
          acknowledged_at: '2026-08-10T09:02:00+09:00',
        }),
      ),
      createInitialWeeklyPlan: jest.fn<Api['createInitialWeeklyPlan']>(
        async () => NEXT_PLAN,
      ),
    };
  }

  function automaticScreen(
    api: ReturnType<typeof automaticApi>,
    onPlanRevisionChange = jest.fn(),
  ) {
    return (
      <WeeklyReportScreen
        api={api as unknown as Api}
        weekStart={REPORT.week_start}
        now={new Date('2026-08-10T10:00:00+09:00')}
        timeZone="Asia/Seoul"
        onBack={jest.fn()}
        onPlanRevisionChange={onPlanRevisionChange}
      />
    );
  }

  it('waits for acknowledgement before applying and does not duplicate under StrictMode or rerenders', async () => {
    const api = automaticApi();
    let resolveAck!: (report: WeeklyReportResponse) => void;
    api.acknowledgeWeeklyReport.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveAck = resolve;
        }),
    );
    const onChange = jest.fn();
    const view = render(
      <StrictMode>{automaticScreen(api, onChange)}</StrictMode>,
    );
    await screen.findByTestId('weekly-report-summary');
    expect(api.acknowledgeWeeklyReport).toHaveBeenCalledTimes(1);
    expect(api.createInitialWeeklyPlan).not.toHaveBeenCalled();
    expect(
      screen.queryByText(
        '내용을 확인했다면 다음 주 계획에 반영할 수 있도록 알려주세요.',
      ),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: '리포트 확인했어요' }),
    ).toBeNull();
    await act(async () =>
      resolveAck({
        ...REPORT,
        status_code: 'ACKNOWLEDGED',
        acknowledged_at: '2026-08-10T09:02:00+09:00',
      }),
    );
    await screen.findByText('다음 주 계획에 반영했어요');
    view.rerender(<StrictMode>{automaticScreen(api, onChange)}</StrictMode>);
    expect(api.acknowledgeWeeklyReport).toHaveBeenCalledTimes(1);
    expect(api.createInitialWeeklyPlan).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(NEXT_PLAN);
  });

  it('keeps the report readable after acknowledgement failure and retries the same request', async () => {
    const api = automaticApi();
    api.acknowledgeWeeklyReport.mockRejectedValueOnce(new Error('offline'));
    render(automaticScreen(api));
    const retry = await screen.findByRole('button', { name: '다시 반영하기' });
    expect(screen.getByTestId('weekly-report-summary')).toBeOnTheScreen();
    expect(api.createInitialWeeklyPlan).not.toHaveBeenCalled();
    fireEvent.press(retry);
    await screen.findByText('다음 주 계획에 반영했어요');
    expect(api.acknowledgeWeeklyReport.mock.calls[1]).toEqual(
      api.acknowledgeWeeklyReport.mock.calls[0],
    );
  });

  it('retries only plan application with the same key after an ambiguous plan failure', async () => {
    const api = automaticApi();
    api.createInitialWeeklyPlan.mockRejectedValueOnce(
      new Error('connection lost'),
    );
    render(automaticScreen(api));
    fireEvent.press(
      await screen.findByRole('button', { name: '다시 반영하기' }),
    );
    await screen.findByText('다음 주 계획에 반영했어요');
    expect(api.acknowledgeWeeklyReport).toHaveBeenCalledTimes(1);
    expect(api.createInitialWeeklyPlan).toHaveBeenCalledTimes(2);
    expect(api.createInitialWeeklyPlan.mock.calls[1]).toEqual(
      api.createInitialWeeklyPlan.mock.calls[0],
    );
  });

  it('does not start the next plan if the screen closes while acknowledgement is pending', async () => {
    const api = automaticApi();
    let resolveAck!: (report: WeeklyReportResponse) => void;
    api.acknowledgeWeeklyReport.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveAck = resolve;
        }),
    );
    const onChange = jest.fn();
    const view = render(automaticScreen(api, onChange));
    await screen.findByTestId('weekly-report-summary');
    view.unmount();
    await act(async () =>
      resolveAck({
        ...REPORT,
        status_code: 'ACKNOWLEDGED',
        acknowledged_at: '2026-08-10T09:02:00+09:00',
      }),
    );
    expect(api.createInitialWeeklyPlan).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('reuses the same initial-plan intent after leaving following a lost response', async () => {
    const api = automaticApi();
    api.createInitialWeeklyPlan.mockRejectedValueOnce(
      new Error('response lost'),
    );
    const view = render(automaticScreen(api));
    await screen.findByRole('button', { name: '다시 반영하기' });
    view.unmount();
    const week = await api.getWeek(REPORT.week_start);
    api.getWeek.mockResolvedValue({
      ...week,
      report_status_code: 'ACKNOWLEDGED',
    });
    api.getWeeklyReport.mockResolvedValue({
      ...REPORT,
      status_code: 'ACKNOWLEDGED',
      acknowledged_at: '2026-08-10T09:02:00+09:00',
    });
    render(automaticScreen(api));
    await screen.findByText('다음 주 계획에 반영했어요');
    expect(api.acknowledgeWeeklyReport).toHaveBeenCalledTimes(1);
    expect(api.createInitialWeeklyPlan.mock.calls[1]).toEqual(
      api.createInitialWeeklyPlan.mock.calls[0],
    );
  });

  it('preserves a server draft without claiming that the next plan was finalized', async () => {
    const api = automaticApi();
    api.createInitialWeeklyPlan.mockResolvedValue({
      ...NEXT_PLAN,
      finalized: false,
      finalized_at: null,
      routine: null,
      safety_status_code: 'NEEDS_INPUT',
    });
    render(automaticScreen(api));
    await screen.findByText('계획 초안은 저장됐지만 아직 확정되지 않았어요');
    expect(screen.queryByText('다음 주 계획에 반영했어요')).toBeNull();
    expect(screen.queryByRole('button', { name: '다시 반영하기' })).toBeNull();
  });

  it('rejects acknowledgement for a different report before plan application', async () => {
    const api = automaticApi();
    api.acknowledgeWeeklyReport.mockResolvedValueOnce({
      ...REPORT,
      report_id: 'another-report',
      status_code: 'ACKNOWLEDGED',
      acknowledged_at: '2026-08-10T09:02:00+09:00',
    });
    render(automaticScreen(api));
    await screen.findByRole('button', { name: '다시 반영하기' });
    expect(api.createInitialWeeklyPlan).not.toHaveBeenCalled();
  });

  it('does not create retroactive plans when opening an older report', async () => {
    const api = automaticApi();
    render(
      <WeeklyReportScreen
        api={api as unknown as Api}
        weekStart={REPORT.week_start}
        now={new Date('2026-09-08T10:00:00+09:00')}
        timeZone="Asia/Seoul"
        onBack={jest.fn()}
        onPlanRevisionChange={jest.fn()}
      />,
    );
    await screen.findByText('리포트 확인을 자동으로 저장했어요.');
    expect(api.acknowledgeWeeklyReport).toHaveBeenCalledTimes(1);
    expect(api.createInitialWeeklyPlan).not.toHaveBeenCalled();
  });

  it('automatically acknowledges an existing historical report without recreating it', async () => {
    const getWeek = jest.fn<Api['getWeek']>(async () => ({
      week_id: 'week-1',
      week_start: '2026-08-03',
      week_end: '2026-08-09',
      timezone: 'Asia/Seoul',
      target_workout_count: 4,
      plan_origin_code: 'WEEKLY_REPORT',
      cold_start_applied: false,
      status_code: 'CLOSED',
      closed_at: '2026-08-10T00:00:00+09:00',
      report_id: REPORT.report_id,
      report_status_code: 'GENERATED',
    }));
    const getWeeklyReport = jest.fn<Api['getWeeklyReport']>(async () => REPORT);
    const createWeeklyReport = jest.fn<Api['createWeeklyReport']>();
    const acknowledgeWeeklyReport = jest.fn<Api['acknowledgeWeeklyReport']>(
      async () => ({
        ...REPORT,
        status_code: 'ACKNOWLEDGED',
        acknowledged_at: '2026-08-10T09:02:00+09:00',
      }),
    );

    await render(
      <WeeklyReportScreen
        api={
          {
            getWeek,
            getWeeklyReport,
            createWeeklyReport,
            acknowledgeWeeklyReport,
          } as unknown as Api
        }
        weekStart="2026-08-03"
        onBack={jest.fn()}
      />,
    );

    expect(
      await screen.findByTestId('weekly-report-summary'),
    ).toBeOnTheScreen();
    expect(getWeek).toHaveBeenCalledWith('2026-08-03', expect.anything());
    expect(getWeeklyReport).toHaveBeenCalledWith(
      REPORT.report_id,
      expect.anything(),
    );
    expect(screen.getByText('수행 결과에 맞춰 조정')).toBeOnTheScreen();
    expect(createWeeklyReport).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(acknowledgeWeeklyReport).toHaveBeenCalledTimes(1),
    );
    expect(
      screen.queryByRole('button', { name: '리포트 생성하기' }),
    ).toBeNull();
    expect(
      screen.getByRole('tab', { name: '리포트' }).props.accessibilityState,
    ).toEqual({ selected: true });
  }, 15_000);

  it('shows safety-stopped sessions separately from ordinary non-completion', async () => {
    renderExistingReport({
      ...REPORT,
      counts: {
        ...REPORT.counts,
        not_completed: 1,
        stopped_for_safety: 2,
        safety_stopped_session_count: 2,
      },
    });

    const notCompleted = await screen.findByTestId(
      'weekly-report-not-completed-count',
    );
    const safetyStopped = screen.getByTestId(
      'weekly-report-safety-stopped-count',
    );

    expect(within(notCompleted).getByText('휴식')).toBeOnTheScreen();
    expect(within(notCompleted).getByText('1')).toBeOnTheScreen();
    expect(within(safetyStopped).getByText('안전 중단')).toBeOnTheScreen();
    expect(within(safetyStopped).getByText('2')).toBeOnTheScreen();
  });

  it('opens on the week itself on safety-stopped weeks', async () => {
    renderExistingReport({
      ...REPORT,
      counts: {
        ...REPORT.counts,
        stopped_for_safety: 1,
        safety_stopped_session_count: 1,
      },
    });

    // The report is written after the week closes, so a safety stop does not
    // take over the heading; the greeting still leads the masthead.
    expect(
      await screen.findByRole('header', { name: '이번 주도 수고했어요!' }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByText('안전 중단 기록을 먼저 확인해 주세요'),
    ).toBeNull();
    // The stop is still reported, once, in the record summary below.
    const safetyStopped = screen.getByTestId(
      'weekly-report-safety-stopped-count',
    );
    expect(within(safetyStopped).getByText('1')).toBeOnTheScreen();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-coach-mascot')).toBeOnTheScreen();
  });

  it('lets the main copy wrap naturally without a forced break or truncation', async () => {
    renderExistingReport();

    const headline = await screen.findByRole('header', {
      name: '이번 주도 수고했어요!',
    });
    expect(headline.props.numberOfLines).toBeUndefined();
    expect(headline.props.children).not.toContain('\n');
    expect(screen.queryByText('함께 봐요')).toBeNull();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
  });

  it('keeps the intro outside the first goal card and omits the redundant ready badge', async () => {
    renderExistingReport();
    const intro = await screen.findByTestId('weekly-report-intro');
    expect(
      within(intro).getByRole('header', { name: '이번 주도 수고했어요!' }),
    ).toBeOnTheScreen();
    // The greeting stands alone; the summary sentence was dropped from the detail view.
    expect(screen.queryByText(REPORT.summary)).toBeNull();
    const summary = screen.getByTestId('weekly-report-summary');
    expect(within(summary).getAllByRole('header')[0]).toHaveTextContent(
      '목표 달성 현황',
    );
    expect(screen.queryByText('리포트 준비됨')).toBeNull();
    const masthead = screen.getByTestId('weekly-report-masthead');
    expect(within(masthead).getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
    expect(within(masthead).getByText('8.3 – 8.9')).toBeOnTheScreen();
  });

  it('uses the calendar partial marker alongside the separate safety marker', async () => {
    renderExistingReport();
    const partial = await screen.findByTestId('weekly-report-partial-icon');
    expect(
      within(partial).getByText(CALENDAR_DAY_VISUALS.partial.glyph),
    ).toBeOnTheScreen();
    expect(partial).toHaveStyle({
      backgroundColor: CALENDAR_DAY_VISUALS.partial.backgroundColor,
    });
    expect(
      within(
        screen.getByTestId('weekly-report-safety-stopped-count'),
      ).getByTestId('weekly-report-icon-safety'),
    ).toBeOnTheScreen();
  });

  it('renders the six report blocks from server-provided aggregates', async () => {
    renderExistingReport();

    expect(await screen.findByText('목표 달성 현황')).toBeOnTheScreen();
    expect(screen.getByText('운동 기록 요약')).toBeOnTheScreen();
    expect(screen.getByText('헬끼가 확인한 점')).toBeOnTheScreen();
    expect(
      screen.getByText('이번 주 헬끼가 이렇게 조정했어요'),
    ).toBeOnTheScreen();
    expect(screen.getByText('다음 주에는 이렇게 추천할게요')).toBeOnTheScreen();
    expect(screen.getByText('헬끼의 한 줄 코치')).toBeOnTheScreen();
    expect(screen.getByText('목표 4회 중 완료 3회')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-delta')).toHaveTextContent(
      '지난주보다 +1회',
    );
    expect(screen.getByText('1시간 5분')).toBeOnTheScreen();
    expect(screen.getByText('스쿼트')).toBeOnTheScreen();
    expect(screen.getByText('적절함')).toBeOnTheScreen();
    expect(
      screen.getByText('주 초보다 피로도가 낮아졌어요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText(REPORT.coach_message!)).toBeOnTheScreen();
  });

  it('decorates the observation and adjustment cards with condition markers', async () => {
    renderExistingReport();

    expect(
      await screen.findAllByTestId('weekly-report-badge-condition'),
    ).toHaveLength(2);
    expect(
      screen.getByTestId('weekly-report-direction-icon'),
    ).toBeOnTheScreen();
  });

  it('shows recorded rest and partial reasons without inventing a cause', async () => {
    renderExistingReport({
      ...REPORT,
      outcome_reason_summary: {
        partial: { RESUME_LATER: 1 },
        not_completed: { TIME_SHORTAGE: 2 },
      },
    });

    expect(
      await screen.findByText('나중에 재개 1회, 시간이 부족했어요 2회'),
    ).toBeOnTheScreen();
  });

  it('states when no rest, partial, or stop reason was recorded', async () => {
    renderExistingReport({ ...REPORT, outcome_reason_summary: {} });
    expect(await screen.findByText('기록된 이유가 없어요.')).toBeOnTheScreen();
  });

  it('formats the server persistence rate independently of counts and completion rate', async () => {
    renderExistingReport({
      ...REPORT,
      completion_rate: 0.42,
      persistence_rate: 0.634,
      counts: { ...REPORT.counts, completed: 1, partial: 1 },
    });
    expect(
      await screen.findByTestId('weekly-report-persistence'),
    ).toHaveTextContent('부분 수행 1회 · 부분 수행까지 포함하면 63%');
    expect(screen.getByText('42%')).toBeOnTheScreen();
  });

  it('shows an explicit zero when no session was partially performed', async () => {
    renderExistingReport({
      ...REPORT,
      counts: { ...REPORT.counts, partial: 0 },
    });
    await screen.findByText('목표 달성 현황');
    expect(screen.getByTestId('weekly-report-persistence')).toHaveTextContent(
      '부분 수행 0회 · 부분 수행까지 포함하면 100%',
    );
  });

  it('keeps an insufficient condition trend explicit for legacy or sparse reports', async () => {
    renderExistingReport({
      ...REPORT,
      condition_summary: {
        ...REPORT.condition_summary!,
        checkin_count: 1,
        fatigue_change_code: 'INSUFFICIENT_DATA',
      },
    });
    expect(
      await screen.findByText('비교할 컨디션 기록이 충분하지 않아요.'),
    ).toBeOnTheScreen();
  });

  it('states safety-stop evidence seriously and keeps the server coach copy', async () => {
    const coachMessage =
      '통증 신호에 맞춰 안전하게 멈춘 점이 중요해요. 다음 주에도 몸 상태를 먼저 확인해요.';
    renderExistingReport({
      ...REPORT,
      counts: {
        ...REPORT.counts,
        stopped_for_safety: 1,
        safety_stopped_session_count: 1,
      },
      condition_summary: {
        ...REPORT.condition_summary!,
        workout_pain_or_safety_stop_count: 1,
      },
      outcome_reason_summary: {
        stopped_for_safety: { PAIN_OR_ABNORMAL_RESPONSE: 1 },
      },
      coach_message: coachMessage,
    });
    expect(
      await screen.findByText(
        '통증 체크인 1회, 운동 중 통증·안전 중단 1회가 기록됐어요.',
      ),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('weekly-report-coach')).getByText(coachMessage),
    ).toBeOnTheScreen();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
  });

  it('hides optional delta and calorie metrics for legacy reports', async () => {
    renderExistingReport({
      ...REPORT,
      completed_count_change: null,
      total_estimated_calories_burned: null,
    });

    await screen.findByText('목표 달성 현황');
    expect(screen.queryByTestId('weekly-report-delta')).toBeNull();
    expect(screen.queryByTestId('weekly-report-calories')).toBeNull();
  });

  it('does not expose unknown metric codes as user-facing copy', async () => {
    renderExistingReport({
      ...REPORT,
      average_intensity_code: 'FUTURE_INTENSITY',
      most_performed_training_type_code: 'FUTURE_TRAINING',
      most_performed_exercise_name: undefined,
    });

    await screen.findByText('운동 기록 요약', {}, { timeout: 10_000 });
    expect(screen.queryByText('FUTURE_INTENSITY')).toBeNull();
    expect(screen.queryByText('FUTURE_TRAINING')).toBeNull();
    expect(screen.getAllByText('확인되지 않은 항목')).toHaveLength(1);
  }, 15_000);

  it('uses the server rate and delta even when counts would suggest other values', async () => {
    renderExistingReport({
      ...REPORT,
      completion_rate: 0.42,
      completed_count_change: -2,
      total_workout_seconds: 7200,
    });

    expect(await screen.findByText('42%')).toBeOnTheScreen();
    expect(screen.queryByText('75%')).toBeNull();
    expect(screen.getByTestId('weekly-report-delta')).toHaveTextContent(
      '지난주보다 -2회',
    );
    expect(screen.getByText('2시간')).toBeOnTheScreen();
    expect(screen.getAllByText(REPORT.coach_message!)).toHaveLength(1);
  });

  it('preserves legacy safety counts and does not invent missing workout metrics', async () => {
    renderExistingReport({
      ...REPORT,
      counts: {
        ...REPORT.counts,
        stopped_for_safety: 2,
        safety_stopped_session_count: undefined,
      },
      total_workout_seconds: undefined,
      total_estimated_calories_burned: undefined,
      most_performed_training_type_code: undefined,
      most_performed_exercise_name: undefined,
      routine_difficulty_code: undefined,
      condition_summary: undefined,
      outcome_reason_summary: undefined,
      coach_message: undefined,
    });

    const safety = await screen.findByTestId(
      'weekly-report-safety-stopped-count',
    );
    expect(within(safety).getByText('2')).toBeOnTheScreen();
    expect(screen.queryByText('총 운동 시간')).toBeNull();
    expect(screen.queryByText('가장 많이 한 운동')).toBeNull();
    expect(
      screen.getByText('기록된 통증 정보를 확인할 수 없어요.'),
    ).toBeOnTheScreen();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-coach-mascot')).toBeOnTheScreen();
  });

  it('keeps the workout metrics horizontal at narrow and wide widths', async () => {
    const originalWindow = Dimensions.get('window');
    const originalScreen = Dimensions.get('screen');
    Dimensions.set({
      window: { width: 1024, height: 768, scale: 1, fontScale: 1 },
    });
    try {
      renderExistingReport();
      const summary = await screen.findByTestId('weekly-report-summary');

      fireEvent(summary, 'layout', {
        nativeEvent: { layout: { width: 320, height: 1400, x: 0, y: 0 } },
      });
      expect(screen.getByTestId('weekly-report-metrics')).toHaveStyle({
        flexDirection: 'row',
      });

      fireEvent(summary, 'layout', {
        nativeEvent: { layout: { width: 768, height: 1000, x: 0, y: 0 } },
      });
      await waitFor(() =>
        expect(screen.getByTestId('weekly-report-metrics')).toHaveStyle({
          flexDirection: 'row',
        }),
      );
      act(() =>
        Dimensions.set({
          window: {
            width: 1024,
            height: 768,
            scale: 1,
            fontScale: 2,
          },
        }),
      );
      fireEvent(summary, 'layout', {
        nativeEvent: { layout: { width: 769, height: 1400, x: 0, y: 0 } },
      });
      await waitFor(() =>
        expect(screen.getByTestId('weekly-report-metrics')).toHaveStyle({
          flexDirection: 'row',
        }),
      );
    } finally {
      act(() =>
        Dimensions.set({ window: originalWindow, screen: originalScreen }),
      );
    }
  });

  it('keeps calendar hierarchy while creating and acknowledging through the API', async () => {
    const onBack = jest.fn();
    const onNavigateTab = jest.fn();
    const getWeek = jest.fn<Api['getWeek']>(async () => ({
      week_id: 'week-1',
      week_start: '2026-08-03',
      week_end: '2026-08-09',
      timezone: 'Asia/Seoul',
      target_workout_count: 4,
      plan_origin_code: 'WEEKLY_REPORT',
      cold_start_applied: false,
      status_code: 'CLOSED',
      closed_at: '2026-08-10T00:00:00+09:00',
      report_id: null,
      report_status_code: null,
    }));
    const getWeeklyReport = jest.fn<Api['getWeeklyReport']>();
    const createWeeklyReport = jest.fn<Api['createWeeklyReport']>(
      async () => REPORT,
    );
    const acknowledgeWeeklyReport = jest.fn<Api['acknowledgeWeeklyReport']>(
      async () => ({
        ...REPORT,
        status_code: 'ACKNOWLEDGED',
        acknowledged_at: '2026-08-10T09:02:00+09:00',
      }),
    );
    const createInitialWeeklyPlan = jest.fn<Api['createInitialWeeklyPlan']>(
      async () => NEXT_PLAN,
    );
    const onPlanRevisionChange = jest.fn();

    const api = {
      getWeek,
      getWeeklyReport,
      createWeeklyReport,
      acknowledgeWeeklyReport,
      createInitialWeeklyPlan,
    } as unknown as Api;

    function StatefulReport() {
      const [planRevision, setPlanRevision] =
        useState<WeeklyPlanRevisionResponse | null>(null);
      return (
        <WeeklyReportScreen
          api={api}
          now={new Date('2026-08-10T00:00:00+09:00')}
          weekStart="2026-08-03"
          onBack={onBack}
          onNavigateTab={onNavigateTab}
          onPlanRevisionChange={(revision) => {
            onPlanRevisionChange(revision);
            setPlanRevision(revision);
          }}
          planRevision={planRevision}
          timeZone="Asia/Seoul"
        />
      );
    }

    await render(<StatefulReport />);

    expect(
      await screen.findByRole('header', { name: '주간 리포트' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('리포트 · 주간 상세')).toBeOnTheScreen();
    expect(screen.getByText('8.3 – 8.9')).toBeOnTheScreen();
    expect(screen.queryByText('리포트 만들기')).toBeNull();
    expect(
      screen.getByTestId('weekly-report-generate-gradient'),
    ).toBeOnTheScreen();

    fireEvent.press(
      screen.getByRole('button', { name: '운동 캘린더로 돌아가기' }),
    );
    expect(onBack).toHaveBeenCalledTimes(1);
    fireEvent.press(screen.getByRole('tab', { name: '홈' }));
    expect(onNavigateTab).toHaveBeenCalledWith('home');

    fireEvent.press(screen.getByRole('button', { name: '리포트 생성하기' }));
    await waitFor(() =>
      expect(createWeeklyReport).toHaveBeenCalledWith('2026-08-03'),
    );
    expect(
      await screen.findByTestId('weekly-report-summary'),
    ).toBeOnTheScreen();
    expect(screen.getByText('75%')).toBeOnTheScreen();
    expect(getWeeklyReport).not.toHaveBeenCalled();

    expect(
      screen.queryByRole('button', { name: '리포트 확인했어요' }),
    ).toBeNull();
    await waitFor(() =>
      expect(acknowledgeWeeklyReport).toHaveBeenCalledWith(
        REPORT.report_id,
        expect.any(String),
        expect.any(String),
      ),
    );
    await waitFor(() =>
      expect(createInitialWeeklyPlan).toHaveBeenCalledWith(
        '2026-08-10',
        REPORT.report_id,
      ),
    );
    expect(onPlanRevisionChange).toHaveBeenCalledWith(NEXT_PLAN);
    expect(
      await screen.findByText('다음 주 계획에 반영했어요'),
    ).toBeOnTheScreen();
    expect(
      screen.queryByRole('button', { name: '리포트 확인했어요' }),
    ).toBeNull();
  });

  it('reuses the applied next plan after leaving and returning in the app', async () => {
    const acknowledgedReport: WeeklyReportResponse = {
      ...REPORT,
      status_code: 'ACKNOWLEDGED',
      acknowledged_at: '2026-08-10T09:02:00+09:00',
    };
    const createInitialWeeklyPlan = jest.fn<Api['createInitialWeeklyPlan']>();

    await render(
      <WeeklyReportScreen
        api={
          {
            getWeek: async () => ({
              week_id: 'week-1',
              week_start: '2026-08-03',
              week_end: '2026-08-09',
              timezone: 'Asia/Seoul',
              target_workout_count: 4,
              plan_origin_code: 'WEEKLY_REPORT',
              cold_start_applied: false,
              status_code: 'CLOSED',
              closed_at: '2026-08-10T00:00:00+09:00',
              report_id: REPORT.report_id,
              report_status_code: 'ACKNOWLEDGED',
            }),
            getWeeklyReport: async () => acknowledgedReport,
            createInitialWeeklyPlan,
          } as unknown as Api
        }
        now={new Date('2026-08-10T00:00:00+09:00')}
        weekStart="2026-08-03"
        onBack={jest.fn()}
        onPlanRevisionChange={jest.fn()}
        planRevision={NEXT_PLAN}
        timeZone="Asia/Seoul"
      />,
    );

    expect(
      await screen.findByText('다음 주 계획에 반영했어요'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText(
        '8.10 – 8.16 · 홈에서 해당 주의 최종 루틴을 확인할 수 있어요.',
      ),
    ).toBeOnTheScreen();
    expect(createInitialWeeklyPlan).not.toHaveBeenCalled();
  });

  it('offers a retry when applying an acknowledged report fails', async () => {
    const acknowledgedReport: WeeklyReportResponse = {
      ...REPORT,
      status_code: 'ACKNOWLEDGED',
      acknowledged_at: '2026-08-10T09:02:00+09:00',
    };
    const createInitialWeeklyPlan = jest
      .fn<Api['createInitialWeeklyPlan']>()
      .mockRejectedValueOnce(new Error('계획을 준비하지 못했어요.'))
      .mockResolvedValueOnce(NEXT_PLAN);

    const api = {
      getWeek: async () => ({
        week_id: 'week-1',
        week_start: '2026-08-03',
        week_end: '2026-08-09',
        timezone: 'Asia/Seoul',
        target_workout_count: 4,
        plan_origin_code: 'WEEKLY_REPORT',
        cold_start_applied: false,
        status_code: 'CLOSED',
        closed_at: '2026-08-10T00:00:00+09:00',
        report_id: REPORT.report_id,
        report_status_code: 'ACKNOWLEDGED',
      }),
      getWeeklyReport: async () => acknowledgedReport,
      createInitialWeeklyPlan,
    } as unknown as Api;

    function StatefulAcknowledgedReport() {
      const [planRevision, setPlanRevision] =
        useState<WeeklyPlanRevisionResponse | null>(null);
      return (
        <WeeklyReportScreen
          api={api}
          now={new Date('2026-08-10T00:00:00+09:00')}
          weekStart="2026-08-03"
          onBack={jest.fn()}
          onPlanRevisionChange={setPlanRevision}
          planRevision={planRevision}
          timeZone="Asia/Seoul"
        />
      );
    }

    await render(<StatefulAcknowledgedReport />);
    expect(
      screen.queryByRole('button', { name: '다음 주 계획 반영하기' }),
    ).toBeNull();

    expect(
      await screen.findByText('요청을 처리하지 못했습니다.'),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '다시 반영하기' }));

    expect(
      await screen.findByText('다음 주 계획에 반영했어요'),
    ).toBeOnTheScreen();
    expect(createInitialWeeklyPlan).toHaveBeenCalledTimes(2);
  });

  it('does not expose report creation while the selected server week is open', async () => {
    const createWeeklyReport = jest.fn<Api['createWeeklyReport']>();

    await render(
      <WeeklyReportScreen
        api={
          {
            getWeek: async () => ({
              week_id: 'week-open',
              week_start: '2026-08-10',
              week_end: '2026-08-16',
              timezone: 'Asia/Seoul',
              target_workout_count: 4,
              plan_origin_code: 'WEEKLY_REPORT',
              cold_start_applied: false,
              status_code: 'OPEN',
              closed_at: null,
              report_id: null,
              report_status_code: null,
            }),
            createWeeklyReport,
          } as unknown as Api
        }
        weekStart="2026-08-10"
        onBack={jest.fn()}
      />,
    );

    expect(await screen.findByText('아직 진행 중인 주예요')).toBeOnTheScreen();
    expect(
      screen.queryByRole('button', { name: '리포트 생성하기' }),
    ).toBeNull();
    expect(createWeeklyReport).not.toHaveBeenCalled();
  });

  it('rejects a backend response for a different week than the selected week', async () => {
    await render(
      <WeeklyReportScreen
        api={
          {
            getWeek: async () => ({
              week_id: 'wrong-week',
              week_start: '2026-08-10',
              week_end: '2026-08-16',
              timezone: 'Asia/Seoul',
              target_workout_count: 4,
              plan_origin_code: 'WEEKLY_REPORT',
              cold_start_applied: false,
              status_code: 'OPEN',
              closed_at: null,
              report_id: null,
              report_status_code: null,
            }),
          } as unknown as Api
        }
        weekStart="2026-08-03"
        onBack={jest.fn()}
      />,
    );

    expect(
      await screen.findByText(
        '선택한 주의 리포트 정보가 일치하지 않습니다. 다시 불러와주세요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.queryByText('8.10 – 8.16')).toBeNull();
  });

  it('renders all six report blocks in their visible tree order', async () => {
    const view = renderExistingReport();

    await screen.findByTestId('weekly-report-summary');
    const tree = JSON.stringify(view.toJSON());
    const headings = [
      '목표 달성 현황',
      '운동 기록 요약',
      '헬끼가 확인한 점',
      '이번 주 헬끼가 이렇게 조정했어요',
      '다음 주에는 이렇게 추천할게요',
      '헬끼의 한 줄 코치',
    ];
    const positions = headings.map((heading) => tree.indexOf(heading));

    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('keeps server-provided recommendation axes in their approved order', async () => {
    const view = renderExistingReport({
      ...REPORT,
      next_week_recommendation: {
        intensity: '강도 문구',
        volume: '운동량 문구',
        duration: '시간 문구',
        pain_response: '통증 대응 문구',
      },
    });

    await screen.findByTestId('weekly-report-summary');
    const tree = JSON.stringify(view.toJSON());

    const copy = ['강도 문구', '운동량 문구', '시간 문구', '통증 대응 문구'];
    const positions = copy.map((value) => tree.indexOf(value));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('uses legacy narration fields when the additive LLM fields are absent', async () => {
    renderExistingReport({
      ...REPORT,
      adjustment_summary: undefined,
      next_week_recommendation: undefined,
      coach_message: undefined,
    });

    expect(await screen.findByText(REPORT.decision_summary)).toBeOnTheScreen();
    expect(screen.getAllByText(REPORT.next_action)).toHaveLength(2);
  });

  it('hides the negotiation rate when the server returns null', async () => {
    renderExistingReport({ ...REPORT, negotiation_success_rate: null });

    await screen.findByTestId('weekly-report-summary');
    expect(screen.queryByText('AI 조정 합의율')).toBeNull();
  });

  it('hides high-completion patterns when every pattern list is empty', async () => {
    renderExistingReport();

    await screen.findByTestId('weekly-report-summary');
    expect(screen.queryByText('잘 이어진 조건')).toBeNull();
  });

  it('does not use penalty language in the report', async () => {
    const view = renderExistingReport();

    await screen.findByTestId('weekly-report-summary');
    expect(JSON.stringify(view.toJSON())).not.toContain('벌점');
  });
});
