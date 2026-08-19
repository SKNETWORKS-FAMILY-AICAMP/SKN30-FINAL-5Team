import { describe, expect, it, jest } from '@jest/globals';
import { render, screen } from '@testing-library/react-native';

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
  adjustment_direction_code: 'MAINTAIN',
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
    expect(createWeeklyReport).not.toHaveBeenCalled();
    expect(acknowledgeWeeklyReport).not.toHaveBeenCalled();
    expect(
      screen.queryByRole('button', { name: '리포트 생성하기' }),
    ).toBeNull();
  });
});
