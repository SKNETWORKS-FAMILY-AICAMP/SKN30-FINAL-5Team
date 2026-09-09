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
  /** Left edge of the rest fill. Without it no empty day is filled. */
  routineStartLocalDate?: string;
};

/**
 * Which status a day keeps when it holds more than one session; highest wins.
 *
 * What the user performed outranks what they did not. A day where a workout was
 * completed and a second session was later abandoned is a completed day, and
 * showing it as rest is the exact hiding of completed blocks `sessionDayStatus`
 * below sets out to avoid. Safety still outranks rest, because a pain stop is a
 * distinct event the legend names, not an absence; the weekly report counts
 * safety stops separately either way. A status absent here (`today`,
 * `upcoming`) falls back to 0 and never displaces a performed session.
 */
const DAY_STATUS_PRIORITY: Partial<Record<CalendarDayStatus, number>> = {
  done: 4,
  partial: 3,
  safety: 2,
  rest: 1,
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

/**
 * A pain or adverse-reaction stop keeps its own status. Folding it into rest
 * hid days where the user had completed blocks before stopping, and it
 * disagreed with the weekly report, which already counts safety stops apart.
 */
function sessionDayStatus(status: string): CalendarDayStatus | null {
  if (status === 'COMPLETED') return 'done';
  if (status === 'PARTIAL') return 'partial';
  if (status === 'STOPPED_FOR_SAFETY') return 'safety';
  if (status === 'NOT_COMPLETED') return 'rest';
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

/**
 * Resolve one grid day.
 *
 * A day the user let pass without any record is a rest day: not working out is
 * how a rest day looks in the data. Only days the routine already covers are
 * filled, and only once they are over - today is still open and the future is
 * not decided, so neither is turned into a rest day.
 */
function dayStatusResolver({
  statuses,
  today,
  restLocalDate,
  routineStartLocalDate,
}: {
  statuses: ReadonlyMap<string, CalendarDayStatus>;
  today: string;
  restLocalDate?: string | null;
  routineStartLocalDate?: string;
}): (localDate: string) => CalendarDayStatus {
  return (localDate) => {
    const recorded = statuses.get(localDate);
    if (recorded !== undefined) return recorded;
    if (localDate === restLocalDate) return 'rest';
    if (
      routineStartLocalDate !== undefined &&
      localDate >= routineStartLocalDate &&
      localDate < today
    ) {
      return 'rest';
    }
    return 'upcoming';
  };
}

/**
 * Counts are days, not sessions, so the totals match the marks on the grid.
 * The weekly report counts sessions instead; the units differ on purpose.
 */
function countStatuses(
  resolveDayStatus: (localDate: string) => CalendarDayStatus,
  from: string,
  to: string,
): readonly [number, number, number, number] {
  let done = 0;
  let partial = 0;
  let rest = 0;
  let safety = 0;
  for (let cursor = from; cursor <= to; cursor = addDays(cursor, 1)) {
    const status = resolveDayStatus(cursor);
    if (status === 'done') done += 1;
    else if (status === 'partial') partial += 1;
    else if (status === 'rest') rest += 1;
    else if (status === 'safety') safety += 1;
  }
  return [done, partial, rest, safety];
}

export function buildCalendarReportData({
  month,
  today,
  sessions,
  weeksByStart,
  restLocalDate,
  routineStartLocalDate,
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
  const resolveDayStatus = dayStatusResolver({
    statuses,
    today,
    restLocalDate,
    routineStartLocalDate,
  });
  const monthFrom = `${month}-01`;
  const monthTo = dateString(new Date(Date.UTC(year, monthNumber, 0)));
  const monthCounts = countStatuses(resolveDayStatus, monthFrom, monthTo);

  const weeks = range.weekStarts.map((start, index): CalendarWeek => {
    const week = weeksByStart.get(start);
    const state = weekState(start, currentWeekStart, week);
    const days = Array.from({ length: 7 }, (_, dayIndex) => {
      const localDate = addDays(start, dayIndex);
      const date = parseDate(localDate);
      const status = resolveDayStatus(localDate);
      return {
        day: String(date.getUTCDate()),
        status,
        inCurrentMonth: localDate.startsWith(`${month}-`),
        isToday: localDate === today,
        localDate,
        sessionIds: sessionIdsByDate.get(localDate) ?? [],
      };
    });
    const stats = countStatuses(resolveDayStatus, start, addDays(start, 6));
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
