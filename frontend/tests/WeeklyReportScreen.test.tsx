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
  completed_count_change: 1,
  highlight_codes: ['COMPLETED_SESSION_RECORDED'],
  improvement_codes: ['MISSED_SESSION_PATTERN_RECORDED'],
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
    expect(screen.getByText('이런 점이 좋았어요')).toBeOnTheScreen();
    expect(screen.getByText('다음 주에 살펴볼 점')).toBeOnTheScreen();
    expect(screen.getByText('이번 주 컨디션과 조정')).toBeOnTheScreen();
    expect(screen.getByText('헬끼의 한 줄 코치')).toBeOnTheScreen();
    expect(screen.getByText('목표 4회 중 완료 3회')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-delta')).toHaveTextContent(
      '지난주보다 +1회',
    );
    expect(screen.getByText('1시간 5분')).toBeOnTheScreen();
    expect(screen.getByText('245.5 kcal')).toBeOnTheScreen();
    expect(screen.queryByText('평균 강도')).toBeNull();
    expect(screen.queryByText('보통')).toBeNull();
    expect(screen.getByText('근력')).toBeOnTheScreen();
  });

  it('decorates the reflection and condition cards with tone badges and markers', async () => {
    renderExistingReport();

    expect(
      await screen.findByTestId('weekly-report-badge-good'),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-badge-watch')).toBeOnTheScreen();
    expect(
      screen.getByTestId('weekly-report-badge-condition'),
    ).toBeOnTheScreen();
    expect(
      screen.getByTestId('weekly-report-direction-icon'),
    ).toBeOnTheScreen();
  });

  it('shows the main missed reason as a separate note below the missed-pattern item', async () => {
    renderExistingReport({
      ...REPORT,
      primary_miss_reason_code: 'TIME_SHORTAGE',
      improvement_codes: [
        'PARTIAL_SESSION_PATTERN_RECORDED',
        'MISSED_SESSION_PATTERN_RECORDED',
      ],
    });

    const note = await screen.findByTestId('weekly-report-miss-reason');
    expect(note).toHaveTextContent('가장 잦은 이유: 시간이 부족했어요');
    const item = screen.getByText('휴식 이유를 다음 주 계획에 반영해요.');
    expect(item).not.toHaveTextContent('가장 잦은 이유');
    expect(screen.getAllByTestId('weekly-report-miss-reason')).toHaveLength(1);
  });

  it.each([
    { reason: null, codes: ['MISSED_SESSION_PATTERN_RECORDED'] },
    { reason: 'TIME_SHORTAGE', codes: ['PARTIAL_SESSION_PATTERN_RECORDED'] },
  ])(
    'hides the missed-reason note when its prerequisites are absent: %j',
    async ({ reason, codes }) => {
      renderExistingReport({
        ...REPORT,
        primary_miss_reason_code: reason,
        improvement_codes: codes,
      });
      await screen.findByText('다음 주에 살펴볼 점');
      expect(screen.queryByTestId('weekly-report-miss-reason')).toBeNull();
    },
  );

  it('formats the server persistence rate independently of counts and completion rate', async () => {
    renderExistingReport({
      ...REPORT,
      completion_rate: 0.42,
      persistence_rate: 0.634,
      counts: { ...REPORT.counts, completed: 1, partial: 1 },
    });
    expect(
      await screen.findByTestId('weekly-report-persistence'),
    ).toHaveTextContent('부분 수행까지 포함하면 63%');
    expect(screen.getByText('42%')).toBeOnTheScreen();
  });

  it('hides persistence when no session was partially performed', async () => {
    renderExistingReport({
      ...REPORT,
      counts: { ...REPORT.counts, partial: 0 },
    });
    await screen.findByText('목표 달성 현황');
    expect(screen.queryByTestId('weekly-report-persistence')).toBeNull();
  });

  it('selects the weekday with the largest sum of partial, missed and safety-stopped records', async () => {
    renderExistingReport({
      ...REPORT,
      weekday_failure_summary: {
        MONDAY: { partial: 0, not_completed: 3, stopped_for_safety: 0 },
        WEDNESDAY: { partial: 2, not_completed: 1, stopped_for_safety: 2 },
        SUNDAY: { partial: 4, not_completed: 0, stopped_for_safety: 0 },
      },
    });
    expect(
      await screen.findByTestId('weekly-report-weekday-focus'),
    ).toHaveTextContent('미완료 기록이 가장 많은 요일은 수요일이에요.');
  });

  it('breaks weekday ties in Monday-to-Sunday order regardless of API key order', async () => {
    renderExistingReport({
      ...REPORT,
      weekday_failure_summary: {
        SUNDAY: { partial: 0, not_completed: 0, stopped_for_safety: 3 },
        FRIDAY: { partial: 0, not_completed: 3, stopped_for_safety: 0 },
        MONDAY: { partial: 3, not_completed: 0, stopped_for_safety: 0 },
      },
    });
    expect(
      await screen.findByTestId('weekly-report-weekday-focus'),
    ).toHaveTextContent('미완료 기록이 가장 많은 요일은 월요일이에요.');
  });

  it.each<WeeklyReportResponse['weekday_failure_summary']>([
    {},
    { MONDAY: { partial: 0, not_completed: 0, stopped_for_safety: 0 } },
  ])(
    'hides the weekday focus when there are no positive totals: %j',
    async (summary) => {
      renderExistingReport({ ...REPORT, weekday_failure_summary: summary });
      await screen.findByText('운동 기록 요약');
      expect(screen.queryByTestId('weekly-report-weekday-focus')).toBeNull();
    },
  );

  it('states the safety-stop fact and leaves the server coaching action unchanged', async () => {
    const nextAction =
      '다음 계획을 시작하기 전에 현재 상태를 다시 확인해주세요.';
    renderExistingReport({
      ...REPORT,
      counts: {
        ...REPORT.counts,
        stopped_for_safety: 1,
        safety_stopped_session_count: 1,
      },
      improvement_codes: ['SAFETY_STOPPED_SESSION_RECORDED'],
      next_action: nextAction,
    });
    expect(
      await screen.findByText('안전 중단으로 마친 세션이 있어요.'),
    ).toBeOnTheScreen();
    expect(
      screen.queryByText('안전 중단 기록을 다음 계획 전에 다시 확인해요.'),
    ).toBeNull();
    expect(
      within(screen.getByTestId('weekly-report-coach')).getByText(nextAction),
    ).toBeOnTheScreen();
    expect(screen.getAllByText(nextAction)).toHaveLength(1);
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
      total_estimated_calories_burned: 0,
    });

    expect(await screen.findByText('42%')).toBeOnTheScreen();
    expect(screen.queryByText('75%')).toBeNull();
    expect(screen.getByTestId('weekly-report-delta')).toHaveTextContent(
      '지난주보다 -2회',
    );
    expect(screen.getByText('2시간')).toBeOnTheScreen();
    expect(screen.getByText('0 kcal')).toBeOnTheScreen();
    expect(screen.getAllByText(REPORT.next_action)).toHaveLength(1);
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
      improvement_codes: ['SAFETY_STOPPED_SESSION_RECORDED'],
    });

    const safety = await screen.findByTestId(
      'weekly-report-safety-stopped-count',
    );
    expect(within(safety).getByText('2')).toBeOnTheScreen();
    expect(screen.queryByText('총 운동 시간')).toBeNull();
    expect(screen.queryByText('예상 소모 칼로리')).toBeNull();
    expect(screen.queryByText('가장 많이 한 운동')).toBeNull();
    expect(
      screen.getByText('안전 중단으로 마친 세션이 있어요.'),
    ).toBeOnTheScreen();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-coach-mascot')).toBeOnTheScreen();
  });

  it('keeps the three metrics horizontal while reflection cards adapt to width and text size', async () => {
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
      expect(screen.getByTestId('weekly-report-reflections')).toHaveStyle({
        flexDirection: 'column',
      });

      fireEvent(summary, 'layout', {
        nativeEvent: { layout: { width: 768, height: 1000, x: 0, y: 0 } },
      });
      await waitFor(() =>
        expect(screen.getByTestId('weekly-report-metrics')).toHaveStyle({
          flexDirection: 'row',
        }),
      );
      expect(screen.getByTestId('weekly-report-reflections')).toHaveStyle({
        flexDirection: 'row',
      });
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
      expect(screen.getByTestId('weekly-report-reflections')).toHaveStyle({
        flexDirection: 'column',
      });
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
      '이런 점이 좋았어요',
      '다음 주에 살펴볼 점',
      '이번 주 컨디션과 조정',
      '헬끼의 한 줄 코치',
    ];
    const positions = headings.map((heading) => tree.indexOf(heading));

    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('keeps server-provided highlight order and ignores unknown codes', async () => {
    const view = renderExistingReport({
      ...REPORT,
      highlight_codes: [
        'PARTIAL_SESSION_PROGRESS_RECORDED',
        'UNKNOWN_FUTURE_CODE',
        'COMPLETED_SESSION_RECORDED',
      ],
    });

    await screen.findByTestId('weekly-report-summary');
    const tree = JSON.stringify(view.toJSON());

    expect(tree.indexOf('가능한 만큼 진행한 기록을 남겼어요.')).toBeLessThan(
      tree.indexOf('완료한 운동 기록을 남겼어요.'),
    );
    expect(tree).not.toContain('UNKNOWN_FUTURE_CODE');
  });

  it('uses neutral fallback copy when no strengths or improvements were aggregated', async () => {
    renderExistingReport({
      ...REPORT,
      highlight_codes: [],
      improvement_codes: [],
    });

    expect(
      await screen.findByText('이번 주 기록에서 이어갈 점을 확인했어요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('다음 주에도 실행 가능한 조건을 함께 찾아요.'),
    ).toBeOnTheScreen();
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
