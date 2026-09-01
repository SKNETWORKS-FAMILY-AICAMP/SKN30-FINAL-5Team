import { describe, expect, it, jest } from '@jest/globals';
import { useState } from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
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
  },
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

  it('renders all four report steps in their visible tree order', async () => {
    const view = renderExistingReport();

    await screen.findByText(REPORT.summary);
    const tree = JSON.stringify(view.toJSON());
    const headings = [
      '이번 주 수행 결과',
      '지속 방해 요인',
      'AI 조정 내역',
      '다음 주 반영 사항',
    ];
    const positions = headings.map((heading) => tree.indexOf(heading));

    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('keeps blocker details before the AI adjustment step', async () => {
    const view = renderExistingReport();

    await screen.findByText(REPORT.summary);
    const tree = JSON.stringify(view.toJSON());

    expect(tree.indexOf('지속 방해 요인')).toBeLessThan(
      tree.indexOf('AI 조정 내역'),
    );
  });

  it('shows every blocker reason in the server-provided order', async () => {
    const view = renderExistingReport({
      ...REPORT,
      primary_miss_reason_code: null,
      pattern_summary: {
        ...REPORT.pattern_summary,
        blocker_reason_codes: ['SCHEDULE_CHANGE', 'FATIGUE', 'WEATHER'],
      },
    });

    await screen.findByText(REPORT.summary);
    const tree = JSON.stringify(view.toJSON());
    const positions = [
      tree.indexOf('일정이 바뀌었어요'),
      tree.indexOf('피로가 컸어요'),
      tree.indexOf('날씨 때문이었어요'),
    ];

    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('shows only recorded weekdays with Korean labels in Monday-to-Sunday order', async () => {
    const view = renderExistingReport({
      ...REPORT,
      primary_miss_reason_code: null,
      weekday_failure_summary: {
        SUNDAY: {
          partial: 0,
          not_completed: 1,
          stopped_for_safety: 0,
        },
        TUESDAY: {
          partial: 1,
          not_completed: 0,
          stopped_for_safety: 0,
        },
      },
      pattern_summary: {
        ...REPORT.pattern_summary,
        blocker_reason_codes: [],
      },
    });

    await screen.findByText(REPORT.summary);
    const tree = JSON.stringify(view.toJSON());

    expect(screen.getByText('화요일')).toBeOnTheScreen();
    expect(screen.getByText('일요일')).toBeOnTheScreen();
    expect(screen.queryByText('월요일')).toBeNull();
    expect(screen.queryByText('수요일')).toBeNull();
    expect(screen.queryByText('목요일')).toBeNull();
    expect(screen.queryByText('금요일')).toBeNull();
    expect(screen.queryByText('토요일')).toBeNull();
    expect(tree.indexOf('화요일')).toBeLessThan(tree.indexOf('일요일'));
  });

  it('shows the blocker empty state when no blocker details were recorded', async () => {
    renderExistingReport({
      ...REPORT,
      primary_miss_reason_code: null,
      weekday_failure_summary: {},
      pattern_summary: {
        ...REPORT.pattern_summary,
        blocker_reason_codes: [],
      },
    });

    expect(
      await screen.findByText('이번 주에는 걸림돌 기록이 없었어요'),
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
