import { useState } from 'react';

import type { Api } from '../../api/endpoints';
import type { WeekResponse, WorkoutSessionLogSummary } from '../../api/types';
import {
  localDateString,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { CalendarReportScreen } from './CalendarReportScreen';
import type { CalendarDay } from './homeSecondaryModel';
import { WorkoutHistorySheet } from './WorkoutHistorySheet';
import { assertWeekMatchesSelection } from '../weekly/weeklyReportModel';
import {
  buildCalendarReportData,
  calendarGridRange,
  shiftCalendarMonth,
} from './calendarReportModel';

type CalendarReportContainerProps = {
  api: Api;
  timeZone?: string;
  routineStartLocalDate?: string;
  restLocalDate?: string | null;
  onNavigateTab?: (tab: TabId) => void;
  onOpenWeeklyReport: (weekStart: string) => void;
  now?: Date;
};

async function loadSessions(
  api: Api,
  fromLocalDate: string,
  toLocalDate: string,
  signal: AbortSignal,
): Promise<WorkoutSessionLogSummary[]> {
  const sessions: WorkoutSessionLogSummary[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await api.listWorkoutSessions(
      { fromLocalDate, toLocalDate, cursor, limit: 100 },
      signal,
    );
    sessions.push(...page.items);
    if (page.next_cursor === null) break;
    if (seenCursors.has(page.next_cursor)) {
      throw new Error('Workout session pagination returned a repeated cursor');
    }
    seenCursors.add(page.next_cursor);
    cursor = page.next_cursor;
  } while (!signal.aborted);
  return sessions;
}

function weekEndString(weekStart: string): string {
  const end = new Date(`${weekStart}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 6);
  return end.toISOString().slice(0, 10);
}

export function CalendarReportContainer({
  api,
  timeZone,
  routineStartLocalDate,
  restLocalDate,
  onNavigateTab,
  onOpenWeeklyReport,
  now,
}: CalendarReportContainerProps) {
  const referenceNow = now ?? new Date();
  const today = localDateString(referenceNow, timeZone);
  const latestMonth = today.slice(0, 7);
  const [month, setMonth] = useState(() => today.slice(0, 7));
  const [selectedDay, setSelectedDay] = useState<{
    localDate: string;
    sessionIds: readonly string[];
  } | null>(null);
  const range = calendarGridRange(month);
  const currentWeekStart = weekStartString(referenceNow, timeZone);

  const { state, reload } = useAsyncData(
    async (signal) => {
      const sessionsPromise =
        routineStartLocalDate !== undefined &&
        range.toLocalDate < routineStartLocalDate
          ? Promise.resolve([] as WorkoutSessionLogSummary[])
          : loadSessions(
              api,
              routineStartLocalDate === undefined
                ? range.fromLocalDate
                : [range.fromLocalDate, routineStartLocalDate].sort()[1]!,
              range.toLocalDate,
              signal,
            );
      const readableWeekStarts = range.weekStarts.filter(
        (start) =>
          start <= currentWeekStart &&
          (routineStartLocalDate === undefined ||
            weekEndString(start) >= routineStartLocalDate),
      );
      const weeksPromise = Promise.all(
        readableWeekStarts.map(async (start) => {
          const week = await api.getWeek(start, signal);
          assertWeekMatchesSelection(start, week);
          return [start, week] as const;
        }),
      );
      const [sessions, weekEntries] = await Promise.all([
        sessionsPromise,
        weeksPromise,
      ]);
      return buildCalendarReportData({
        month,
        today,
        sessions,
        weeksByStart: new Map<string, WeekResponse>(weekEntries),
        restLocalDate,
      });
    },
    [api, month, today, currentWeekStart, routineStartLocalDate, restLocalDate],
  );

  if (state.status === 'loading') {
    return (
      <ScreenShell>
        <ScreenHeading title="운동 캘린더" />
        <LoadingState label="운동 기록을 불러오고 있어요" />
      </ScreenShell>
    );
  }

  if (state.status === 'error') {
    return (
      <ScreenShell>
        <ScreenHeading title="운동 캘린더" />
        <ErrorState message={state.message} onRetry={reload} />
      </ScreenShell>
    );
  }

  const openDay = (day: CalendarDay) => {
    if (day.localDate === undefined || (day.sessionIds?.length ?? 0) === 0) {
      return;
    }
    setSelectedDay({
      localDate: day.localDate,
      sessionIds: day.sessionIds ?? [],
    });
  };

  return (
    <>
      <CalendarReportScreen
        monthLabel={state.data.monthLabel}
        monthStats={state.data.stats}
        weeks={state.data.weeks}
        selectedMonth={month}
        latestMonth={latestMonth}
        routineStartLocalDate={routineStartLocalDate}
        onChangeMonth={(direction) => {
          setSelectedDay(null);
          setMonth((current) =>
            direction === 'next' && current >= latestMonth
              ? current
              : shiftCalendarMonth(current, direction === 'previous' ? -1 : 1),
          );
        }}
        onSelectMonth={(selected) => {
          if (selected <= latestMonth) {
            setSelectedDay(null);
            setMonth(selected);
          }
        }}
        onNavigateTab={onNavigateTab}
        onOpenDay={openDay}
        onOpenWeeklyReport={onOpenWeeklyReport}
      />
      {selectedDay ? (
        <WorkoutHistorySheet
          api={api}
          localDate={selectedDay.localDate}
          onClose={() => setSelectedDay(null)}
          sessionIds={selectedDay.sessionIds}
        />
      ) : null}
    </>
  );
}
