import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import type { WeeklyReportResponse } from '../src/api/types';
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
        onBack={onBack}
        onNavigateTab={onNavigateTab}
      />,
    );

    expect(
      await screen.findByRole('header', { name: '주간 리포트' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('리포트 · 주간 상세')).toBeOnTheScreen();
    expect(screen.getByText('8.3 – 8.9')).toBeOnTheScreen();
    expect(screen.getByText('리포트 만들기')).toBeOnTheScreen();

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
    expect(
      screen.queryByRole('button', { name: '리포트 확인했어요' }),
    ).toBeNull();
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
});
