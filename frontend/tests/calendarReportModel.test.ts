import type { WorkoutSessionLogSummary } from '../src/api/types';
import {
  buildCalendarReportData,
  type CalendarReportData,
} from '../src/features/home/calendarReportModel';

function dayStatus(
  data: CalendarReportData,
  localDate: string,
): string | undefined {
  for (const week of data.weeks) {
    const day = week.days.find((item) => item.localDate === localDate);
    if (day !== undefined) return day.status;
  }
  return undefined;
}

function session(
  id: string,
  date: string,
  status: WorkoutSessionLogSummary['status_code'],
): WorkoutSessionLogSummary {
  return {
    training_type_code: 'STRENGTH',
    not_completed_reason_code: null,
    started_at: `${date}T09:30:00+09:00`,
    session_id: id,
    local_date: date,
    status_code: status,
    completed_item_count:
      status === 'COMPLETED' ? 2 : status === 'PARTIAL' ? 1 : 0,
    total_item_count: 2,
    requested_duration_minutes: 30,
    finished_at: `${date}T10:00:00+09:00`,
  };
}

it('merges missed sessions and a rest marker into one rest count without duplicating the same marker', () => {
  const data = buildCalendarReportData({
    month: '2026-09',
    today: '2026-09-08',
    weeksByStart: new Map(),
    restLocalDate: '2026-09-07',
    sessions: [
      session('rest-1', '2026-09-07', 'NOT_COMPLETED'),
      session('rest-2', '2026-09-08', 'NOT_COMPLETED'),
      session('partial', '2026-09-06', 'PARTIAL'),
      session('done', '2026-09-05', 'COMPLETED'),
    ],
  });
  expect(
    data.stats.map(({ key, label, value }) => ({ key, label, value })),
  ).toEqual([
    { key: 'done', label: '완료', value: 1 },
    { key: 'partial', label: '부분 수행', value: 1 },
    { key: 'rest', label: '휴식', value: 2 },
    { key: 'safety', label: '안전 중단', value: 0 },
  ]);
  const week = data.weeks.find((item) => item.weekStart === '2026-09-07')!;
  expect(week.stats).toEqual([0, 0, 2, 0]);
  expect(week.days[0]?.status).toBe('rest');
  expect(week.days[1]?.status).toBe('rest');
  expect(week.days[2]?.status).toBe('upcoming');
});

it('fills days the user let pass as rest, but not today, the future, or dates before the routine', () => {
  const data = buildCalendarReportData({
    month: '2026-09',
    today: '2026-09-08',
    weeksByStart: new Map(),
    routineStartLocalDate: '2026-09-03',
    sessions: [session('done', '2026-09-04', 'COMPLETED')],
  });

  expect(dayStatus(data, '2026-09-02')).toBe('upcoming');
  expect(dayStatus(data, '2026-09-03')).toBe('rest');
  expect(dayStatus(data, '2026-09-04')).toBe('done');
  expect(dayStatus(data, '2026-09-07')).toBe('rest');
  expect(dayStatus(data, '2026-09-08')).toBe('upcoming');
  expect(dayStatus(data, '2026-09-09')).toBe('upcoming');
  expect(data.stats.map(({ key, value }) => [key, value])).toEqual([
    ['done', 1],
    ['partial', 0],
    ['rest', 4],
    ['safety', 0],
  ]);
});

it('leaves every day open when the routine start is unknown', () => {
  const data = buildCalendarReportData({
    month: '2026-09',
    today: '2026-09-08',
    weeksByStart: new Map(),
    sessions: [],
  });

  expect(dayStatus(data, '2026-09-03')).toBe('upcoming');
  expect(data.stats.map(({ key, value }) => [key, value])).toEqual([
    ['done', 0],
    ['partial', 0],
    ['rest', 0],
    ['safety', 0],
  ]);
});

it('counts a safety stop apart from rest even when no block was completed', () => {
  const data = buildCalendarReportData({
    month: '2026-09',
    today: '2026-09-08',
    weeksByStart: new Map(),
    routineStartLocalDate: '2026-09-01',
    sessions: [session('safety', '2026-09-05', 'STOPPED_FOR_SAFETY')],
  });

  expect(dayStatus(data, '2026-09-05')).toBe('safety');
  expect(data.stats.map(({ key, value }) => [key, value])).toEqual([
    ['done', 0],
    ['partial', 0],
    ['rest', 6],
    ['safety', 1],
  ]);
});
