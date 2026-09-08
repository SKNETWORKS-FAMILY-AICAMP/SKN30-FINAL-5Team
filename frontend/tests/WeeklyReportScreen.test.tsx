import { describe, expect, it, jest } from '@jest/globals';
import { useState } from 'react';
import {
  fireEvent,
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
        } as unknown as Api
      }
      weekStart={report.week_start}
      onBack={jest.fn()}
    />,
  );
}

describe('WeeklyReportScreen selected week', () => {
  it('loads an existing report without creating or acknowledging it', async () => {
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
    const acknowledgeWeeklyReport = jest.fn<Api['acknowledgeWeeklyReport']>();

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
      await screen.findByText('선택한 주의 저장된 리포트입니다.'),
    ).toBeOnTheScreen();
    expect(getWeek).toHaveBeenCalledWith('2026-08-03', expect.anything());
    expect(getWeeklyReport).toHaveBeenCalledWith(
      REPORT.report_id,
      expect.anything(),
    );
    expect(screen.getByText('수행 결과에 맞춰 조정')).toBeOnTheScreen();
    expect(createWeeklyReport).not.toHaveBeenCalled();
    expect(acknowledgeWeeklyReport).not.toHaveBeenCalled();
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

    expect(within(notCompleted).getByText('미수행')).toBeOnTheScreen();
    expect(within(notCompleted).getByText('1')).toBeOnTheScreen();
    expect(
      within(safetyStopped).getByText('운동 중 안전 중단'),
    ).toBeOnTheScreen();
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
    // take over the heading; the week summary still leads the card.
    expect(await screen.findByText(REPORT.summary)).toBeOnTheScreen();
    expect(
      screen.queryByText('안전 중단 기록을 먼저 확인해 주세요'),
    ).toBeNull();
    // The stop is still reported, once, in the record summary below.
    const safetyStopped = screen.getByTestId(
      'weekly-report-safety-stopped-count',
    );
    expect(within(safetyStopped).getByText('1')).toBeOnTheScreen();
  });

  it('breaks the mascot speech bubble across two lines', async () => {
    renderExistingReport();

    expect(await screen.findByText('이번 주도\n수고했어요!')).toBeOnTheScreen();
    expect(screen.getByLabelText('응원하는 끼끼')).toBeOnTheScreen();
  });

  it('renders the six report blocks from server-provided aggregates', async () => {
    renderExistingReport();

    expect(await screen.findByText('목표 달성 현황')).toBeOnTheScreen();
    expect(screen.getByText('운동 기록 요약')).toBeOnTheScreen();
    expect(screen.getByText('이런 점이 좋았어요')).toBeOnTheScreen();
    expect(screen.getByText('이런 점은 조금 아쉬웠어요')).toBeOnTheScreen();
    expect(screen.getByText('이번 주 컨디션과 조정')).toBeOnTheScreen();
    expect(screen.getByText('헬끼의 한 줄 코치')).toBeOnTheScreen();
    expect(screen.getByText('목표 4회 중 완료 3회')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-report-delta')).toHaveTextContent(
      '지난주보다 +1회',
    );
    expect(screen.getByText('1시간 5분')).toBeOnTheScreen();
    expect(screen.getByText('245.5 kcal')).toBeOnTheScreen();
    expect(screen.getByText('보통')).toBeOnTheScreen();
    expect(screen.getByText('근력')).toBeOnTheScreen();
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
    expect(screen.getAllByText('확인되지 않은 항목')).toHaveLength(2);
  }, 15_000);

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

    function StatefulReport() {
      const [planRevision, setPlanRevision] =
        useState<WeeklyPlanRevisionResponse | null>(null);
      return (
        <WeeklyReportScreen
          api={
            {
              getWeek,
              getWeeklyReport,
              createWeeklyReport,
              acknowledgeWeeklyReport,
              createInitialWeeklyPlan,
            } as unknown as Api
          }
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
      await screen.findByText('선택한 주의 저장된 리포트입니다.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('75%')).toBeOnTheScreen();
    expect(getWeeklyReport).not.toHaveBeenCalled();

    fireEvent.press(screen.getByRole('button', { name: '리포트 확인했어요' }));
    await waitFor(() =>
      expect(acknowledgeWeeklyReport).toHaveBeenCalledWith(
        REPORT.report_id,
        expect.any(String),
      ),
    );
    expect(await screen.findByText('리포트를 확인했어요')).toBeOnTheScreen();
    await waitFor(() =>
      expect(createInitialWeeklyPlan).toHaveBeenCalledWith('2026-08-10'),
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

    function StatefulAcknowledgedReport() {
      const [planRevision, setPlanRevision] =
        useState<WeeklyPlanRevisionResponse | null>(null);
      return (
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
          onPlanRevisionChange={setPlanRevision}
          planRevision={planRevision}
          timeZone="Asia/Seoul"
        />
      );
    }

    await render(<StatefulAcknowledgedReport />);
    fireEvent.press(
      await screen.findByRole('button', {
        name: '다음 주 계획 반영하기',
      }),
    );

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

    await screen.findByText(REPORT.summary);
    const tree = JSON.stringify(view.toJSON());
    const headings = [
      '목표 달성 현황',
      '운동 기록 요약',
      '이런 점이 좋았어요',
      '이런 점은 조금 아쉬웠어요',
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

    await screen.findByText(REPORT.summary);
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

    await screen.findByText(REPORT.summary);
    expect(screen.queryByText('AI 조정 합의율')).toBeNull();
  });

  it('hides high-completion patterns when every pattern list is empty', async () => {
    renderExistingReport();

    await screen.findByText(REPORT.summary);
    expect(screen.queryByText('잘 이어진 조건')).toBeNull();
  });

  it('does not use penalty language in the report', async () => {
    const view = renderExistingReport();

    await screen.findByText(REPORT.summary);
    expect(JSON.stringify(view.toJSON())).not.toContain('벌점');
  });
});
