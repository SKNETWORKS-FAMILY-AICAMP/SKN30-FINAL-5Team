import type { WeekResponse, WorkoutSessionLogSummary } from '../../api/types';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_STATUS_ORDER,
  type CalendarDayStatus,
  type CalendarMonthStat,
  type CalendarWeek,
  type CalendarWeekState,
} from './homeSecondaryModel';
import { weeklyReportAvailability } from '../weekly/weeklyReportModel';

export type CalendarReportData = {
  monthLabel: string;
  stats: readonly CalendarMonthStat[];
  weeks: readonly CalendarWeek[];
};

type CalendarReportInput = {
  month: string;
  today: string;
  sessions: readonly WorkoutSessionLogSummary[];
  weeksByStart: ReadonlyMap<string, WeekResponse>;
  restLocalDate?: string | null;
};

const DAY_STATUS_PRIORITY: Partial<Record<CalendarDayStatus, number>> = {
  done: 1,
  partial: 2,
  miss: 3,
};

function parseDate(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) {
    throw new Error(`Invalid local date: ${value}`);
  }
  return new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
  );
}

function dateString(value: Date): string {
  return [
    value.getUTCFullYear(),
    String(value.getUTCMonth() + 1).padStart(2, '0'),
    String(value.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

function addDays(value: string, amount: number): string {
  const date = parseDate(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return dateString(date);
}

function weekStart(value: string): string {
  const date = parseDate(value);
  const mondayOffset = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - mondayOffset);
  return dateString(date);
}

function monthParts(month: string): { year: number; monthNumber: number } {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (match === null) {
    throw new Error(`Invalid calendar month: ${month}`);
  }
  const year = Number(match[1]);
  const monthNumber = Number(match[2]);
  if (monthNumber < 1 || monthNumber > 12) {
    throw new Error(`Invalid calendar month: ${month}`);
  }
  return { year, monthNumber };
}

export function shiftCalendarMonth(month: string, amount: number): string {
  const { year, monthNumber } = monthParts(month);
  const date = new Date(Date.UTC(year, monthNumber - 1 + amount, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function calendarGridRange(month: string): {
  fromLocalDate: string;
  toLocalDate: string;
  weekStarts: string[];
} {
  const { year, monthNumber } = monthParts(month);
  const first = `${year}-${String(monthNumber).padStart(2, '0')}-01`;
  const lastDate = new Date(Date.UTC(year, monthNumber, 0));
  const last = dateString(lastDate);
  const fromLocalDate = weekStart(first);
  const lastWeekStart = weekStart(last);
  const toLocalDate = addDays(lastWeekStart, 6);
  const weekStarts: string[] = [];
  for (
    let cursor = fromLocalDate;
    cursor <= toLocalDate;
    cursor = addDays(cursor, 7)
  ) {
    weekStarts.push(cursor);
  }
  return { fromLocalDate, toLocalDate, weekStarts };
}

function sessionDayStatus(status: string): CalendarDayStatus | null {
  if (status === 'COMPLETED') return 'done';
  if (status === 'PARTIAL') return 'partial';
  if (status === 'NOT_COMPLETED' || status === 'STOPPED_FOR_SAFETY') {
    return 'miss';
  }
  return null;
}

function statusByDate(
  sessions: readonly WorkoutSessionLogSummary[],
): Map<string, CalendarDayStatus> {
  const result = new Map<string, CalendarDayStatus>();
  for (const session of sessions) {
    const status = sessionDayStatus(session.status_code);
    if (status === null) continue;
    const current = result.get(session.local_date);
    if (
      current === undefined ||
      (DAY_STATUS_PRIORITY[status] ?? 0) > (DAY_STATUS_PRIORITY[current] ?? 0)
    ) {
      result.set(session.local_date, status);
    }
  }
  return result;
}

function weekState(
  start: string,
  currentWeekStart: string,
  week: WeekResponse | undefined,
): CalendarWeekState {
  if (week === undefined) {
    return start > currentWeekStart ? 'upcoming' : 'progress';
  }
  const availability = weeklyReportAvailability(week);
  if (availability === 'IN_PROGRESS') return 'progress';
  if (availability === 'AVAILABLE_TO_CREATE') return 'make';
  if (availability === 'GENERATED') return 'unread';
  if (availability === 'ACKNOWLEDGED') return 'read';
  return 'unavailable';
}

/**
 * The weekly note follows the week's progress instead of repeating one fixed
 * sentence: in progress, goal reached, or the week has ended.
 */
function noteForWeek(
  state: CalendarWeekState,
  doneCount: number,
  targetWorkoutCount: number,
): string {
  if (state === 'progress') {
    if (targetWorkoutCount > 0 && doneCount >= targetWorkoutCount) {
      return '이번 주 목표를 달성했어요!';
    }
    return '이번 주 운동을 진행하고 있어요. 남은 일정도 함께 채워봐요.';
  }
  if (state === 'make') {
    return '이번 주 운동 기록을 확인해보세요. 리포트를 만들면 한 주의 운동 패턴을 정리해드려요.';
  }
  if (state === 'unread') {
    return '이번 주 운동 기록을 확인해보세요. 리포트가 준비됐어요.';
  }
  if (state === 'read') {
    return '이번 주 운동 기록을 다시 확인해볼 수 있어요.';
  }
  if (state === 'unavailable') {
    return '리포트를 불러오지 못했어요. 잠시 후 다시 확인해주세요.';
  }
  return '아직 시작하지 않은 주예요.';
}

function bandColorForState(state: CalendarWeekState): string {
  if (state === 'progress') return '#FFEBC2';
  if (state === 'read') return '#FFF8E5';
  if (state === 'make' || state === 'unread' || state === 'unavailable') {
    return '#F3F1EB';
  }
  return '#FCFBF8';
}

function rangeLabel(start: string): string {
  const end = addDays(start, 6);
  const format = (value: string) => {
    const date = parseDate(value);
    return `${date.getUTCMonth() + 1}.${date.getUTCDate()}`;
  };
  return `${format(start)} – ${format(end)}`;
}

function countStatuses(
  sessions: readonly WorkoutSessionLogSummary[],
  from: string,
  to: string,
  restLocalDate?: string | null,
): readonly [number, number, number, number] {
  let done = 0;
  let partial = 0;
  let miss = 0;
  for (const session of sessions) {
    if (session.local_date < from || session.local_date > to) continue;
    const status = sessionDayStatus(session.status_code);
    if (status === 'done') done += 1;
    if (status === 'partial') partial += 1;
    if (status === 'miss') miss += 1;
  }
  const rest =
    restLocalDate !== null &&
    restLocalDate !== undefined &&
    restLocalDate >= from &&
    restLocalDate <= to
      ? 1
      : 0;
  return [done, partial, rest, miss];
}

export function buildCalendarReportData({
  month,
  today,
  sessions,
  weeksByStart,
  restLocalDate,
}: CalendarReportInput): CalendarReportData {
  const { year, monthNumber } = monthParts(month);
  const range = calendarGridRange(month);
  const currentWeekStart = weekStart(today);
  const statuses = statusByDate(sessions);
  const sessionIdsByDate = new Map<string, string[]>();
  for (const session of sessions) {
    const ids = sessionIdsByDate.get(session.local_date) ?? [];
    ids.push(session.session_id);
    sessionIdsByDate.set(session.local_date, ids);
  }
  const monthFrom = `${month}-01`;
  const monthTo = dateString(new Date(Date.UTC(year, monthNumber, 0)));
  const monthCounts = countStatuses(
    sessions,
    monthFrom,
    monthTo,
    restLocalDate,
  );

  const weeks = range.weekStarts.map((start, index): CalendarWeek => {
    const week = weeksByStart.get(start);
    const state = weekState(start, currentWeekStart, week);
    const days = Array.from({ length: 7 }, (_, dayIndex) => {
      const localDate = addDays(start, dayIndex);
      const date = parseDate(localDate);
      const recorded = statuses.get(localDate);
      const status =
        recorded ?? (localDate === restLocalDate ? 'rest' : 'upcoming');
      return {
        day: String(date.getUTCDate()),
        status,
        inCurrentMonth: localDate.startsWith(`${month}-`),
        isToday: localDate === today,
        localDate,
        sessionIds: sessionIdsByDate.get(localDate) ?? [],
      };
    });
    const stats = countStatuses(
      sessions,
      start,
      addDays(start, 6),
      restLocalDate,
    );
    return {
      id: start,
      weekStart: start,
      label: `${index + 1}주차`,
      range: rangeLabel(start),
      state,
      bandColor: bandColorForState(state),
      days,
      stats,
      note: noteForWeek(state, stats[0], week?.target_workout_count ?? 0),
    };
  });

  return {
    monthLabel: `${year}년 ${monthNumber}월`,
    stats: CALENDAR_STATUS_ORDER.map((key, index) => ({
      key,
      label: CALENDAR_DAY_VISUALS[key].label,
      value: monthCounts[index] ?? 0,
      color: CALENDAR_DAY_VISUALS[key].accentColor,
    })),
    weeks,
  };
}
