import { describe, expect, it, jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import {
  AccessibilityInfo,
  Animated,
  Platform,
  ScrollView,
  StyleSheet,
} from 'react-native';

import { CalendarReportScreen } from '../src/features/home/CalendarReportScreen';
import { MapHomeScreen } from '../src/features/home/MapHomeScreen';
import { MyPageScreen } from '../src/features/home/MyPageScreen';
import {
  PREVIEW_OPEN_WEEK,
  PREVIEW_ROUTINE,
} from '../src/features/preview/backendPreview';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_MONTH_STATS,
  CALENDAR_STATUS_ORDER,
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
      '12:upcoming:true',
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
  ['done', '✓', 0x2713, '#5E8342', '#FFFFFF', '#5E8342'],
  ['partial', '△', 0x25b3, '#F6BA50', '#6B520C', '#F6BA50'],
  ['miss', '×', 0x00d7, '#FFFFFF', '#C0BBB1', '#E2DED4'],
  ['rest', '–', 0x2013, '#EDEAE2', '#8B8780', '#EDEAE2'],
  ['today', '', undefined, 'transparent', 'transparent', 'transparent'],
  ['upcoming', '', undefined, 'transparent', 'transparent', 'transparent'],
] as const;

const EXPECTED_WEEK_CHIPS = [
  ['progress', '진행 중', '#FFFFFF', '#A45F00', '#F1D39A', 'solid'],
  ['make', '리포트 생성 가능!', '#E7F3FA', '#356A85', '#9CC5DF', 'solid'],
  ['unread', '리포트 확인하기', '#EDF3DD', '#5F7048', '#C8D7AC', 'solid'],
  ['read', '확인 완료', '#EDF3DD', '#5F7048', '#C8D7AC', 'solid'],
  ['unavailable', '리포트 오류', '#FDECE9', '#C2402F', '#F5C9C1', 'solid'],
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
    ).toBe('');
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
      backgroundColor: '#E7F3FA',
      borderColor: '#9CC5DF',
      borderStyle: 'solid',
    });
    expect(
      screen.getByTestId('calendar-chip-week-2-label').props.children,
    ).toBe('리포트 생성 가능!');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-chip-week-1').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#EDF3DD',
      borderColor: '#C8D7AC',
      borderStyle: 'solid',
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-week-week-2').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#F3F9FC',
      borderColor: '#79B1D2',
      borderWidth: 2,
      elevation: 3,
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-week-week-1').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#F6F9EF',
      borderColor: '#C8D7AC',
      borderWidth: 1.5,
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-week-week-3').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#FFF9EA',
      borderColor: '#E7D3A8',
      borderWidth: 1.5,
    });
  });

  it('renders the untitled status legend above the weekday row', () => {
    const view = render(<CalendarReportScreen />);
    const tree = JSON.stringify(view.toJSON());

    expect(screen.queryByText('아이콘 안내')).toBeNull();
    expect(tree.indexOf('calendar-legend-done')).toBeLessThan(
      tree.indexOf('calendar-weekday-월'),
    );
    expect(
      CALENDAR_STATUS_ORDER.map((status) => CALENDAR_DAY_VISUALS[status].label),
    ).toEqual(['완료', '부분 수행', '휴식', '미수행']);
    expect(CALENDAR_MONTH_STATS.map((stat) => stat.label)).toEqual([
      '완료',
      '부분 수행',
      '휴식',
      '미수행',
    ]);
  });

  it('marks today separately from the recorded day status', () => {
    render(<CalendarReportScreen />);

    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-day-week-3-2').props.style,
      ),
    ).toMatchObject({ borderColor: '#E0A742', backgroundColor: '#FFF3D6' });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-day-week-3-2-number').props.style,
      ),
    ).toMatchObject({ color: '#A45F00', fontWeight: '800' });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-day-week-3-1').props.style,
      ).borderColor,
    ).toBe('transparent');
  });

  it('shows a caret on every expandable week card and flips it when open', () => {
    render(<CalendarReportScreen />);

    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-week-caret-week-3', {
          includeHiddenElements: true,
        }).props.style,
      ).transform,
    ).toBeUndefined();

    fireEvent.press(
      screen.getByRole('button', { name: '3주차 진행 중, 요약 펼치기' }),
    );

    expect(
      StyleSheet.flatten(
        screen.getByTestId('calendar-week-caret-week-3', {
          includeHiddenElements: true,
        }).props.style,
      ).transform,
    ).toEqual([{ rotate: '180deg' }]);
  });

  it('summarises an expanded week with the shared status labels', () => {
    render(<CalendarReportScreen />);

    fireEvent.press(
      screen.getByRole('button', { name: '3주차 진행 중, 요약 펼치기' }),
    );

    expect(screen.getByText('완료 1회 / 부분 수행 1회')).toBeOnTheScreen();
    expect(screen.queryByText(/^3주차 ·/)).toBeNull();
    for (const status of CALENDAR_STATUS_ORDER) {
      expect(
        screen.getByTestId(`calendar-week-stat-${status}`),
      ).toBeOnTheScreen();
    }
    expect(
      screen.getByText(
        '이번 주 운동을 진행하고 있어요. 남은 일정도 함께 채워봐요.',
      ),
    ).toBeOnTheScreen();
  });

  it('periodically shakes the report creation CTA when motion is allowed', async () => {
    jest
      .mocked(AccessibilityInfo.isReduceMotionEnabled)
      .mockResolvedValueOnce(false);
    const loopSpy = jest.spyOn(Animated, 'loop');
    const timingSpy = jest.spyOn(Animated, 'timing');

    render(<CalendarReportScreen />);
    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(loopSpy).toHaveBeenCalledTimes(1));
    expect(timingSpy).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        toValue: -4,
        duration: 55,
        useNativeDriver: true,
      }),
    );
  });

  it('shows API routine items below the map without map overlays', async () => {
    const onSelectRest = jest.fn();
    const onStartWorkout = jest.fn();
    await render(
      <MapHomeScreen
        onSelectRest={onSelectRest}
        onStartWorkout={onStartWorkout}
        previewState="map"
        routine={PREVIEW_ROUTINE}
        week={PREVIEW_OPEN_WEEK}
      />,
    );

    expect(screen.getByText('이번 주')).toBeOnTheScreen();
    expect(screen.getByText('목표 4회')).toBeOnTheScreen();
    expect(
      screen.getByText('진행 중인 주예요. 편한 날에 하나씩 채워요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('지금 내 루틴')).toBeOnTheScreen();
    expect(screen.getByText('근력 · 30분 · 블록 3개')).toBeOnTheScreen();
    expect(screen.getByText('의자 스쿼트')).toBeOnTheScreen();
    expect(screen.getAllByText('3세트 × 10회')).toHaveLength(3);
    expect(screen.getByText('제자리 걷기')).toBeOnTheScreen();
    expect(screen.queryByText('3세트 · 180초')).toBeNull();
    expect(screen.queryByText('더 가벼운 루틴 보기')).toBeNull();
    expect(screen.getByTestId('home-map-stage')).toBeOnTheScreen();
    expect(screen.getByTestId('home-map-api-section')).toBeOnTheScreen();
    expect(screen.queryByLabelText('근력 운동 위치')).toBeNull();
    expect(screen.queryByLabelText('컨디션 창 열기')).toBeNull();
    expect(screen.queryByLabelText('오늘 체크인')).toBeNull();
    expect(
      screen.queryByText(
        '오늘의 운동 섬이에요. 표시를 눌러 루틴을 확인해보세요.',
      ),
    ).toBeNull();

    fireEvent.press(
      screen.getByRole('button', { name: '이 루틴으로 시작하기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '오늘은 휴식하기' }));
    expect(onStartWorkout).toHaveBeenCalledTimes(1);
    expect(onSelectRest).toHaveBeenCalledTimes(1);
  });

  it('shows an empty API state at the bottom without restoring map controls', async () => {
    await render(<MapHomeScreen previewState="condition" />);

    expect(
      screen.getByText(
        '아직 보여줄 루틴이 없어요. 홈에서 기본 루틴을 다시 불러와 주세요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.queryByText('4,200')).toBeNull();
    expect(screen.queryByText('7시간')).toBeNull();
    expect(screen.queryByLabelText('컨디션 창 열기')).toBeNull();
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
      screen.getByRole('button', { name: '2주차 리포트 생성 가능!' }),
    );
    expect(onOpenWeeklyReport).toHaveBeenCalledWith('2026-08-03');
  });

  it('keeps the month picker above the calendar and removes future choices', async () => {
    await render(<CalendarReportScreen previewState="month-picker" />);

    expect(screen.getByText('2025년')).toBeOnTheScreen();
    expect(screen.queryByText('2027년')).toBeNull();
    expect(screen.queryByText('9월')).toBeNull();
    expect(
      StyleSheet.flatten(screen.getByTestId('month-picker').props.style),
    ).toMatchObject({
      zIndex: 1000,
      elevation: 24,
    });
    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(screen.queryByText('2025년')).toBeNull();
  });

  it('animates the date caret when the month picker opens and closes', async () => {
    const timingSpy = jest.spyOn(Animated, 'timing');
    await render(<CalendarReportScreen />);
    const dateButton = screen.getByRole('button', {
      name: '연도와 월 선택',
    });

    fireEvent.press(dateButton);
    expect(timingSpy).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }),
    );

    fireEvent.press(dateButton);
    expect(timingSpy).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({
        toValue: 0,
        duration: 150,
        useNativeDriver: true,
      }),
    );
    timingSpy.mockRestore();
  });

  it('defaults the first date selection to the current year and month', async () => {
    const onSelectMonth = jest.fn();
    await render(
      <CalendarReportScreen
        latestMonth="2026-08"
        onSelectMonth={onSelectMonth}
        selectedMonth="2025-12"
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '연도와 월 선택' }));
    expect(
      screen.getByTestId('month-picker-year-wheel').props.contentOffset,
    ).toEqual({ x: 0, y: 10 * 44 });
    expect(
      screen.getByTestId('month-picker-month-wheel').props.contentOffset,
    ).toEqual({ x: 0, y: 7 * 44 });
    expect(
      screen.getByTestId('month-picker-year-wheel-value-2026').props
        .accessibilityState,
    ).toEqual({ selected: true });
    expect(
      screen.getByTestId('month-picker-month-wheel-value-8').props
        .accessibilityState,
    ).toEqual({ selected: true });

    const selectionBandStyle = StyleSheet.flatten(
      screen.getByTestId('month-picker-selection-band').props.style,
    );
    expect(selectionBandStyle).toMatchObject({ top: 2 * 44, height: 44 });

    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(onSelectMonth).toHaveBeenCalledWith('2026-08');
  });

  it('moves one item for a small web wheel gesture and several for a fast gesture', async () => {
    const onSelectMonth = jest.fn();
    const originalPlatform = Platform.OS;
    const wheelNodes: {
      handler?: (event: {
        deltaMode: number;
        deltaY: number;
        preventDefault: () => void;
      }) => void;
    }[] = [];
    const getScrollableNode = jest
      .spyOn(ScrollView.prototype, 'getScrollableNode')
      .mockImplementation(() => {
        const node: (typeof wheelNodes)[number] = {};
        wheelNodes.push(node);
        return {
          addEventListener: (
            type: string,
            handler: (typeof node)['handler'],
          ) => {
            if (type === 'wheel') node.handler = handler;
          },
          removeEventListener: () => undefined,
        };
      });
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: 'web',
    });

    try {
      await render(
        <CalendarReportScreen
          latestMonth="2026-12"
          onSelectMonth={onSelectMonth}
          previewState="month-picker"
        />,
      );

      const wheelUp = (deltaY: number) => ({
        deltaMode: 0,
        deltaY,
        preventDefault: jest.fn(),
      });
      await act(async () => {
        wheelNodes.at(-1)?.handler?.(wheelUp(-20));
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      expect(
        screen.getByTestId('month-picker-month-wheel-value-11').props
          .accessibilityState,
      ).toEqual({ selected: true });

      await act(async () => {
        const handler = wheelNodes.at(-1)?.handler;
        handler?.(wheelUp(-100));
        handler?.(wheelUp(-100));
        handler?.(wheelUp(-100));
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      expect(
        screen.getByTestId('month-picker-month-wheel-value-8').props
          .accessibilityState,
      ).toEqual({ selected: true });

      fireEvent.press(screen.getByRole('button', { name: '완료' }));
      expect(onSelectMonth).toHaveBeenCalledWith('2026-08');
    } finally {
      getScrollableNode.mockRestore();
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  });

  it('keeps the initial current-month offset stable while the wheel is dragged', async () => {
    const onSelectMonth = jest.fn();
    await render(
      <CalendarReportScreen
        latestMonth="2026-08"
        onSelectMonth={onSelectMonth}
        previewState="month-picker"
        selectedMonth="2025-12"
      />,
    );

    const initialOffset = screen.getByTestId('month-picker-month-wheel').props
      .contentOffset;
    expect(initialOffset).toEqual({ x: 0, y: 7 * 44 });

    fireEvent.scroll(screen.getByTestId('month-picker-month-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 6 * 44 } },
    });
    expect(
      screen.getByTestId('month-picker-month-wheel').props.contentOffset,
    ).toBe(initialOffset);

    fireEvent.scroll(screen.getByTestId('month-picker-month-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 3 * 44 } },
    });
    expect(
      screen.getByTestId('month-picker-month-wheel').props.contentOffset,
    ).toBe(initialOffset);

    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(onSelectMonth).toHaveBeenCalledWith('2026-04');
  });

  it('keeps the month wheel mounted and selected while changing years', async () => {
    const onSelectMonth = jest.fn();
    await render(
      <CalendarReportScreen
        latestMonth="2026-08"
        onSelectMonth={onSelectMonth}
        previewState="month-picker"
      />,
    );

    fireEvent.scroll(screen.getByTestId('month-picker-month-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 3 * 44 } },
    });
    fireEvent.scroll(screen.getByTestId('month-picker-year-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 9 * 44 } },
    });
    const monthWheel = screen.getByTestId('month-picker-month-wheel');

    fireEvent.scroll(screen.getByTestId('month-picker-year-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 8 * 44 } },
    });

    expect(screen.getByTestId('month-picker-month-wheel')).toBe(monthWheel);
    expect(
      screen.getByTestId('month-picker-month-wheel-value-4').props
        .accessibilityState,
    ).toEqual({ selected: true });

    fireEvent.scroll(screen.getByTestId('month-picker-year-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 10 * 44 } },
    });

    expect(screen.getByTestId('month-picker-month-wheel')).toBe(monthWheel);
    expect(
      screen.getByTestId('month-picker-month-wheel-value-4').props
        .accessibilityState,
    ).toEqual({ selected: true });
    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(onSelectMonth).toHaveBeenCalledWith('2026-04');
  });

  it('clamps a future month without remounting when returning to the latest year', async () => {
    const onSelectMonth = jest.fn();
    await render(
      <CalendarReportScreen
        latestMonth="2026-08"
        onSelectMonth={onSelectMonth}
        previewState="month-picker"
      />,
    );

    fireEvent.scroll(screen.getByTestId('month-picker-year-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 9 * 44 } },
    });
    fireEvent.scroll(screen.getByTestId('month-picker-month-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 11 * 44 } },
    });
    const monthWheel = screen.getByTestId('month-picker-month-wheel');

    fireEvent.scroll(screen.getByTestId('month-picker-year-wheel'), {
      nativeEvent: { contentOffset: { x: 0, y: 10 * 44 } },
    });

    expect(screen.getByTestId('month-picker-month-wheel')).toBe(monthWheel);
    expect(screen.queryByText('9월')).toBeNull();
    expect(
      screen.getByTestId('month-picker-month-wheel-value-8').props
        .accessibilityState,
    ).toEqual({ selected: true });
    fireEvent.press(screen.getByRole('button', { name: '완료' }));
    expect(onSelectMonth).toHaveBeenCalledWith('2026-08');
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
