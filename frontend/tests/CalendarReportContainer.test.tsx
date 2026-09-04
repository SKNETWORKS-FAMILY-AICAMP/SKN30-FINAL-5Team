import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import type { Api } from '../src/api/endpoints';
import type { WeekResponse } from '../src/api/types';
import { CalendarReportContainer } from '../src/features/home/CalendarReportContainer';

function week(
  weekStart: string,
  status: 'OPEN' | 'CLOSED',
  reportStatus: WeekResponse['report_status_code'] = null,
  targetWorkoutCount = 4,
): WeekResponse {
  const start = new Date(`${weekStart}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() + 6);
  const weekEnd = start.toISOString().slice(0, 10);
  return {
    week_id: `week-${weekStart}`,
    week_start: weekStart,
    week_end: weekEnd,
    timezone: 'Asia/Seoul',
    target_workout_count: targetWorkoutCount,
    plan_origin_code: 'WEEKLY_REPORT',
    cold_start_applied: false,
    status_code: status,
    closed_at: status === 'CLOSED' ? `${weekStart}T00:00:00Z` : null,
    report_id: reportStatus === null ? null : `report-${weekStart}`,
    report_status_code: reportStatus,
  };
}

describe('CalendarReportContainer', () => {
  it('uses the standard navigation CTA to create a weekly report', async () => {
    const listWorkoutSessions = jest.fn<Api['listWorkoutSessions']>(
      async () => ({ items: [], next_cursor: null }),
    );
    const getWeek = jest.fn<Api['getWeek']>(async (weekStart) =>
      week(weekStart, weekStart === '2026-08-10' ? 'OPEN' : 'CLOSED'),
    );
    const onOpenWeeklyReport = jest.fn();

    await render(
      <CalendarReportContainer
        api={{ listWorkoutSessions, getWeek } as unknown as Api}
        now={new Date('2026-08-12T03:00:00Z')}
        onOpenWeeklyReport={onOpenWeeklyReport}
        timeZone="Asia/Seoul"
      />,
    );

    expect(await screen.findByText('2026년 8월')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', {
        name: '2주차 리포트 생성 가능!, 요약 펼치기',
      }),
    );

    const reportAction = screen.getByRole('button', {
      name: '주간 리포트 만들기',
    });
    expect(
      screen.getByTestId('calendar-week-report-action-gradient'),
    ).toBeOnTheScreen();
    expect(
      screen.getByTestId('calendar-week-report-action-chevron'),
    ).toBeOnTheScreen();
    expect(StyleSheet.flatten(reportAction.props.style)).toMatchObject({
      height: 46,
    });

    fireEvent.press(reportAction);
    expect(onOpenWeeklyReport).toHaveBeenCalledWith('2026-08-03');
  });

  it('celebrates an open week after the completed-session target is reached', async () => {
    const listWorkoutSessions = jest.fn<Api['listWorkoutSessions']>(
      async () => ({
        items: ['10', '11', '12', '13'].map((day, index) => ({
          session_id: `completed-${index + 1}`,
          local_date: `2026-08-${day}`,
          status_code: 'COMPLETED' as const,
          completed_item_count: 3,
          total_item_count: 3,
          requested_duration_minutes: 30,
          training_type_code: 'STRENGTH',
          not_completed_reason_code: null,
          started_at: `2026-08-${day}T09:00:00+09:00`,
          finished_at: `2026-08-${day}T09:30:00+09:00`,
        })),
        next_cursor: null,
      }),
    );
    const getWeek = jest.fn<Api['getWeek']>(async (weekStart) =>
      week(weekStart, weekStart === '2026-08-10' ? 'OPEN' : 'CLOSED'),
    );

    await render(
      <CalendarReportContainer
        api={{ listWorkoutSessions, getWeek } as unknown as Api}
        now={new Date('2026-08-14T03:00:00Z')}
        onOpenWeeklyReport={jest.fn()}
        timeZone="Asia/Seoul"
      />,
    );

    expect(await screen.findByText('2026년 8월')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', {
        name: '3주차 진행 중, 요약 펼치기',
      }),
    );
    expect(screen.getByText('이번 주 목표를 달성했어요!')).toBeOnTheScreen();
  });

  it('disables and darkens dates before the user started their routine', async () => {
    const listWorkoutSessions = jest.fn<Api['listWorkoutSessions']>(
      async () => ({ items: [], next_cursor: null }),
    );
    const getWeek = jest.fn<Api['getWeek']>(async (weekStart) =>
      week(weekStart, weekStart === '2026-08-10' ? 'OPEN' : 'CLOSED'),
    );

    await render(
      <CalendarReportContainer
        api={{ listWorkoutSessions, getWeek } as unknown as Api}
        now={new Date('2026-08-12T03:00:00Z')}
        onOpenWeeklyReport={jest.fn()}
        routineStartLocalDate="2026-08-06"
        timeZone="Asia/Seoul"
      />,
    );

    expect(await screen.findByText('2026년 8월')).toBeOnTheScreen();
    expect(listWorkoutSessions).toHaveBeenCalledWith(
      expect.objectContaining({ fromLocalDate: '2026-08-06' }),
      expect.anything(),
    );
    expect(getWeek.mock.calls.map(([weekStart]) => weekStart)).toEqual([
      '2026-08-03',
      '2026-08-10',
    ]);

    const unavailableWeek = screen.getByRole('button', {
      name: '1주차 루틴 시작 전, 선택할 수 없음',
    });
    expect(unavailableWeek.props.accessibilityState).toEqual({
      disabled: true,
    });
    fireEvent.press(unavailableWeek);
    expect(screen.queryByText('리포트를 확인한 주예요.')).toBeNull();

    const unavailableDay = screen.getByRole('button', {
      name: '2026-08-03 루틴 시작 전 날짜',
    });
    expect(unavailableDay.props.accessibilityState).toEqual({ disabled: true });
    expect(StyleSheet.flatten(unavailableDay.props.style)).toMatchObject({
      backgroundColor: '#C9C5BC',
      opacity: 1,
    });
    expect(
      screen.getByTestId('calendar-day-2026-08-03-0-mark-glyph').props.children,
    ).toBe('');
    expect(
      screen.getByTestId('calendar-day-2026-08-10-2-mark-glyph').props.children,
    ).toBe('');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-day-2026-08-10-2-mark').props.style,
      ),
    ).toMatchObject({
      backgroundColor: 'transparent',
      borderColor: 'transparent',
    });
  });

  it('renders the existing calendar UI from paginated backend records', async () => {
    const listWorkoutSessions = jest
      .fn<Api['listWorkoutSessions']>()
      .mockResolvedValue({ items: [], next_cursor: null })
      .mockResolvedValueOnce({
        items: [
          {
            session_id: 'completed',
            local_date: '2026-08-04',
            status_code: 'COMPLETED',
            completed_item_count: 3,
            total_item_count: 3,
            requested_duration_minutes: 30,
            training_type_code: 'STRENGTH',
            not_completed_reason_code: null,
            started_at: '2026-08-04T09:00:00+09:00',
            finished_at: '2026-08-04T09:30:00+09:00',
          },
          {
            session_id: 'safety-stop',
            local_date: '2026-08-08',
            status_code: 'STOPPED_FOR_SAFETY',
            completed_item_count: 0,
            total_item_count: 3,
            requested_duration_minutes: 30,
            training_type_code: 'STRENGTH',
            not_completed_reason_code: null,
            started_at: '2026-08-08T09:00:00+09:00',
            finished_at: '2026-08-08T09:05:00+09:00',
          },
        ],
        next_cursor: 'second-page',
      })
      .mockResolvedValueOnce({
        items: [
          {
            session_id: 'partial',
            local_date: '2026-08-12',
            status_code: 'PARTIAL',
            completed_item_count: 1,
            total_item_count: 3,
            requested_duration_minutes: 30,
            training_type_code: 'STRENGTH',
            not_completed_reason_code: null,
            started_at: '2026-08-12T09:00:00+09:00',
            finished_at: '2026-08-12T09:15:00+09:00',
          },
        ],
        next_cursor: null,
      });
    const getWeek = jest.fn<Api['getWeek']>(async (weekStart) => {
      if (weekStart === '2026-07-27') {
        return week(weekStart, 'CLOSED', 'ACKNOWLEDGED');
      }
      if (weekStart === '2026-08-03') {
        return week(weekStart, 'CLOSED', 'GENERATED');
      }
      return week(weekStart, 'OPEN');
    });
    const getWorkoutSession = jest.fn<Api['getWorkoutSession']>(async () => ({
      session_id: 'completed',
      local_date: '2026-08-04',
      status_code: 'COMPLETED',
      completed_item_count: 2,
      total_item_count: 2,
      requested_duration_minutes: 30,
      items: [
        {
          plan_item_id: 'history-item-1',
          exercise_id: 'history-exercise-1',
          exercise_name: '스쿼트',
          status_code: 'COMPLETED',
          sets: 3,
          reps: 10,
          work_seconds_per_set: null,
          completed_at: '2026-08-04T09:10:00+09:00',
        },
        {
          plan_item_id: 'history-item-2',
          exercise_id: 'history-exercise-2',
          exercise_name: '플랭크',
          status_code: 'COMPLETED',
          sets: 2,
          reps: null,
          work_seconds_per_set: 30,
          completed_at: '2026-08-04T09:20:00+09:00',
        },
      ],
      feedback: {
        perceived_difficulty_code: 'APPROPRIATE',
        post_workout_discomfort_reported: false,
      },
      not_completed_reason_code: null,
      started_at: '2026-08-04T09:00:00+09:00',
      finished_at: '2026-08-04T09:30:00+09:00',
    }));
    const onOpenWeeklyReport = jest.fn();

    await render(
      <CalendarReportContainer
        api={
          { listWorkoutSessions, getWeek, getWorkoutSession } as unknown as Api
        }
        now={new Date('2026-08-12T03:00:00Z')}
        timeZone="Asia/Seoul"
        restLocalDate="2026-08-03"
        onOpenWeeklyReport={onOpenWeeklyReport}
      />,
    );

    expect(await screen.findByText('2026년 8월')).toBeOnTheScreen();
    expect(
      screen.getByTestId('calendar-day-2026-08-03-0-mark-glyph').props.children,
    ).toBe('–');
    expect(
      screen.getByTestId('calendar-day-2026-08-03-1-mark-glyph').props.children,
    ).toBe('✓');
    expect(
      screen.getByTestId('calendar-day-2026-08-03-5-mark-glyph').props.children,
    ).toBe('×');
    expect(
      screen.getByTestId('calendar-day-2026-08-10-2-mark-glyph').props.children,
    ).toBe('△');
    expect(
      screen.getByTestId('calendar-chip-2026-08-03-label').props.children,
    ).toBe('리포트 확인하기');

    fireEvent.press(
      screen.getByRole('button', {
        name: '2주차 리포트 확인하기, 요약 펼치기',
      }),
    );
    fireEvent.press(
      screen.getByRole('button', {
        name: '2026-08-04 운동 기록 보기',
      }),
    );
    expect(await screen.findByText('2026-08-04 운동 기록')).toBeOnTheScreen();
    expect(screen.getByText(/스쿼트/)).toBeOnTheScreen();
    expect(screen.getByText(/플랭크/)).toBeOnTheScreen();
    expect(getWorkoutSession).toHaveBeenCalledWith(
      'completed',
      expect.anything(),
    );
    fireEvent.press(screen.getByRole('button', { name: '운동 기록 닫기' }));
    expect(
      screen.getByTestId('calendar-week-report-action-gradient'),
    ).toBeOnTheScreen();
    expect(
      screen.getByTestId('calendar-week-report-action-chevron'),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '주간 리포트 보기' }));
    expect(onOpenWeeklyReport).toHaveBeenCalledWith('2026-08-03');
    fireEvent.press(
      screen.getByRole('button', {
        name: '3주차 진행 중, 요약 펼치기',
      }),
    );
    expect(
      screen.getByText(
        '이번 주 운동을 진행하고 있어요. 남은 일정도 함께 채워봐요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.queryByText('진행 중 요약 보기 ›')).toBeNull();
    expect(screen.queryByRole('button', { name: /주간 리포트/ })).toBeNull();
    expect(onOpenWeeklyReport).toHaveBeenCalledTimes(1);
    expect(listWorkoutSessions).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ cursor: 'second-page', limit: 100 }),
      expect.anything(),
    );
    expect(getWeek).toHaveBeenCalledTimes(3);

    expect(
      screen.getByRole('button', { name: '다음 달' }).props.accessibilityState,
    ).toEqual({ disabled: true });
    fireEvent.press(screen.getByRole('button', { name: '다음 달' }));
    expect(screen.getByText('2026년 8월')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '이전 달' }));
    await waitFor(() =>
      expect(screen.getByText('2026년 7월')).toBeOnTheScreen(),
    );
    expect(listWorkoutSessions).toHaveBeenCalledWith(
      expect.objectContaining({
        fromLocalDate: '2026-06-29',
        toLocalDate: '2026-08-02',
      }),
      expect.anything(),
    );
  });
});
