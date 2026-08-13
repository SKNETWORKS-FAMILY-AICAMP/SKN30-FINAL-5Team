import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { CalendarReportScreen } from '../src/features/home/CalendarReportScreen';
import { MapHomeScreen } from '../src/features/home/MapHomeScreen';
import { MyPageScreen } from '../src/features/home/MyPageScreen';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_MONTH_STATS,
  CALENDAR_WEEK_CHIPS,
  CALENDAR_WEEKDAYS,
  CALENDAR_WEEKS,
} from '../src/features/home/homeSecondaryModel';

const EXPECTED_CALENDAR_WEEKS = [
  [
    'week-1',
    '7.27 – 8.2',
    'read',
    [
      '27:done:false',
      '28:done:false',
      '29:partial:false',
      '30:done:false',
      '31:miss:false',
      '1:partial:true',
      '2:rest:true',
    ],
    [0, 1, 1, 0],
  ],
  [
    'week-2',
    '8.3 – 8.9',
    'make',
    [
      '3:rest:true',
      '4:done:true',
      '5:done:true',
      '6:partial:true',
      '7:done:true',
      '8:miss:true',
      '9:rest:true',
    ],
    [3, 1, 2, 1],
  ],
  [
    'week-3',
    '8.10 – 8.16',
    'progress',
    [
      '10:done:true',
      '11:partial:true',
      '12:today:true',
      '13:upcoming:true',
      '14:upcoming:true',
      '15:upcoming:true',
      '16:upcoming:true',
    ],
    [1, 1, 0, 0],
  ],
  [
    'week-4',
    '8.17 – 8.23',
    'upcoming',
    [
      '17:upcoming:true',
      '18:upcoming:true',
      '19:upcoming:true',
      '20:upcoming:true',
      '21:upcoming:true',
      '22:upcoming:true',
      '23:upcoming:true',
    ],
    [0, 0, 0, 0],
  ],
  [
    'week-5',
    '8.24 – 8.30',
    'upcoming',
    [
      '24:upcoming:true',
      '25:upcoming:true',
      '26:upcoming:true',
      '27:upcoming:true',
      '28:upcoming:true',
      '29:upcoming:true',
      '30:upcoming:true',
    ],
    [0, 0, 0, 0],
  ],
  [
    'week-6',
    '8.31 – 9.6',
    'upcoming',
    [
      '31:upcoming:true',
      '1:upcoming:false',
      '2:upcoming:false',
      '3:upcoming:false',
      '4:upcoming:false',
      '5:upcoming:false',
      '6:upcoming:false',
    ],
    [0, 0, 0, 0],
  ],
] as const;

const EXPECTED_DAY_VISUALS = [
  ['done', '✓', 0x2713, '#4E8B3A', '#FFFFFF', '#4E8B3A'],
  ['partial', '◐', 0x25d0, '#FBD24E', '#6B520C', '#FBD24E'],
  ['miss', '×', 0x00d7, '#FFFFFF', '#C0BBB1', '#E2DED4'],
  ['rest', '–', 0x2013, '#EDEAE2', '#8B8780', '#EDEAE2'],
  ['today', '●', 0x25cf, '#FFFFFF', '#3E7A32', '#4E8B3A'],
  ['upcoming', '', undefined, 'transparent', 'transparent', 'transparent'],
] as const;

const EXPECTED_WEEK_CHIPS = [
  ['progress', '진행 중', '#FFFFFF', '#3E7A32', '#CBDDB4', 'solid'],
  ['make', '리포트 만들기', '#FBD24E', '#3A320F', '#EFC02F', 'solid'],
  ['unread', '확인 필요', '#FDECE9', '#C2402F', '#F5C9C1', 'solid'],
  ['read', '확인 완료', 'transparent', '#9A968E', '#E2DED4', 'solid'],
  ['upcoming', '예정', 'transparent', '#B7B2A8', '#DFDBD2', 'dashed'],
] as const;

describe('Home secondary visual prototypes', () => {
  it('matches the original deterministic August fixture table', () => {
    for (const [id, range, state, days, stats] of EXPECTED_CALENDAR_WEEKS) {
      const week = CALENDAR_WEEKS.find((item) => item.id === id);

      expect(week).toBeDefined();
      expect(week?.range).toBe(range);
      expect(week?.state).toBe(state);
      expect(
        week?.days.map(
          (day) => `${day.day}:${day.status}:${day.inCurrentMonth}`,
        ),
      ).toEqual(days);
      expect(week?.stats).toEqual(stats);
    }
  });

  it('keeps the exact Unicode glyph and circle color table', () => {
    for (const [
      status,
      glyph,
      codePoint,
      backgroundColor,
      color,
      borderColor,
    ] of EXPECTED_DAY_VISUALS) {
      expect(CALENDAR_DAY_VISUALS[status]).toMatchObject({
        glyph,
        backgroundColor,
        color,
        borderColor,
      });
      expect(Array.from(glyph).length).toBe(glyph === '' ? 0 : 1);
      expect(glyph.codePointAt(0)).toBe(codePoint);
    }
  });

  it('keeps the exact week chip label and color table', () => {
    for (const [
      state,
      label,
      backgroundColor,
      color,
      borderColor,
      borderStyle,
    ] of EXPECTED_WEEK_CHIPS) {
      expect(CALENDAR_WEEK_CHIPS[state]).toEqual({
        label,
        backgroundColor,
        color,
        borderColor,
        borderStyle,
      });
    }
  });

  it('covers the full August month and exact weekday colors', () => {
    expect(CALENDAR_WEEKS).toHaveLength(6);
    expect(CALENDAR_WEEKS.map((week) => week.range)).toEqual([
      '7.27 – 8.2',
      '8.3 – 8.9',
      '8.10 – 8.16',
      '8.17 – 8.23',
      '8.24 – 8.30',
      '8.31 – 9.6',
    ]);
    expect(CALENDAR_MONTH_STATS.map(({ key, value }) => [key, value])).toEqual([
      ['done', 4],
      ['partial', 3],
      ['rest', 3],
      ['miss', 1],
    ]);
    expect(CALENDAR_WEEKDAYS.map(({ label, color }) => [label, color])).toEqual(
      [
        ['월', '#9A968E'],
        ['화', '#9A968E'],
        ['수', '#9A968E'],
        ['목', '#9A968E'],
        ['금', '#9A968E'],
        ['토', '#5B7FB0'],
        ['일', '#C2402F'],
      ],
    );
  });

  it('renders exact calendar status and weekday styles from the fixture', async () => {
    await render(<CalendarReportScreen />);

    expect(screen.getByText('6주차')).toBeOnTheScreen();
    expect(
      screen.getByTestId('calendar-day-week-2-0-mark-glyph').props.children,
    ).toBe('–');
    expect(
      screen.getByTestId('calendar-day-week-3-2-mark-glyph').props.children,
    ).toBe('●');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-day-week-2-0-mark').props.style,
      ),
    ).toMatchObject({
      width: 20,
      height: 20,
      backgroundColor: '#EDEAE2',
      borderColor: '#EDEAE2',
      borderWidth: 1.5,
    });
    expect(
      StyleSheet.flatten(screen.getByTestId('calendar-weekday-토').props.style)
        .color,
    ).toBe('#5B7FB0');
    expect(
      StyleSheet.flatten(screen.getByTestId('calendar-weekday-일').props.style)
        .color,
    ).toBe('#C2402F');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-chip-week-2').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#FBD24E',
      borderColor: '#EFC02F',
      borderStyle: 'solid',
    });
    expect(
      screen.getByTestId('calendar-chip-week-2-label').props.children,
    ).toBe('리포트 만들기');
  });

  it('shows one map routine without the conflicting lighter public option', async () => {
    const onSelectRest = jest.fn();
    const onStartWorkout = jest.fn();
    await render(
      <MapHomeScreen
        onSelectRest={onSelectRest}
        onStartWorkout={onStartWorkout}
        previewState="routine"
      />,
    );

    expect(screen.getByText('오늘의 운동 계획을 준비했어요')).toBeOnTheScreen();
    expect(screen.queryByText('더 가벼운 루틴 보기')).toBeNull();

    fireEvent.press(
      screen.getByRole('button', { name: '이 루틴으로 시작하기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '오늘은 휴식하기' }));
    expect(onStartWorkout).toHaveBeenCalledTimes(1);
    expect(onSelectRest).toHaveBeenCalledTimes(1);
  });

  it('opens map condition information as a local visual state', async () => {
    await render(<MapHomeScreen />);

    fireEvent.press(screen.getByRole('button', { name: '컨디션 창 열기' }));
    expect(screen.getByText('4,200')).toBeOnTheScreen();
    expect(screen.getByText('7시간')).toBeOnTheScreen();
  });

  it('shows calendar week fixtures and exposes report navigation as a callback', async () => {
    const onOpenWeeklyReport = jest.fn();
    await render(
      <CalendarReportScreen
        onOpenWeeklyReport={onOpenWeeklyReport}
        previewState="week-detail"
      />,
    );

    expect(
      screen.getByRole('header', { name: '운동 캘린더' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByText(
        '한 주가 끝났어요. 리포트를 만들면 이번 주 운동 패턴을 정리해드려요.',
      ),
    ).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '주간 리포트 만들기  ›' }),
    );
    expect(onOpenWeeklyReport).toHaveBeenCalledWith('week-2');
  });

  it('keeps month selection as a visual-only picker', async () => {
    await render(<CalendarReportScreen previewState="month-picker" />);

    expect(screen.getByText('2025년')).toBeOnTheScreen();
    expect(screen.getByText('9월')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(screen.queryByText('2025년')).toBeNull();
  });

  it('returns notification and account actions through callbacks without persistence', async () => {
    const onAccountAction = jest.fn();
    const onNotificationChange = jest.fn();
    await render(
      <MyPageScreen
        onAccountAction={onAccountAction}
        onNotificationChange={onNotificationChange}
      />,
    );

    fireEvent.press(screen.getByRole('switch', { name: /응원 알림/ }));
    fireEvent.press(screen.getByRole('button', { name: /연동 기기/ }));
    expect(onNotificationChange).toHaveBeenCalledWith('encouragement', true);
    expect(onAccountAction).toHaveBeenCalledWith('연동 기기');
  });

  it('renders logout and withdrawal confirmations as callback-only states', async () => {
    const onConfirmLogout = jest.fn();
    const logout = await render(
      <MyPageScreen onConfirmLogout={onConfirmLogout} previewState="logout" />,
    );
    const logoutButtons = screen.getAllByRole('button', { name: '로그아웃' });
    fireEvent.press(logoutButtons[logoutButtons.length - 1]);
    expect(onConfirmLogout).toHaveBeenCalledTimes(1);

    const onConfirmWithdraw = jest.fn();
    logout.rerender(
      <MyPageScreen
        onConfirmWithdraw={onConfirmWithdraw}
        previewState="withdraw"
      />,
    );
    fireEvent.press(screen.getByRole('button', { name: '탈퇴하기' }));
    expect(onConfirmWithdraw).toHaveBeenCalledTimes(1);
  });
});
