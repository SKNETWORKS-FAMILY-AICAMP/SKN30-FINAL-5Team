import { afterEach, describe, expect, it, jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';
import { Platform, processColor, ScrollView, StyleSheet } from 'react-native';

import type { Api } from '../src/api/endpoints';
import type {
  SessionItemUpdateResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
} from '../src/api/types';
import { fontFamilies } from '../src/app/fonts';
import { imageAssets } from '../src/assets';
import {
  clampWorkoutPageIndex,
  formatWorkoutTime,
  workoutPageAfterHorizontalDrag,
  WorkoutScreen,
} from '../src/features/workout/WorkoutScreen';
import {
  getWorkoutResponsiveLayout,
  SAFETY_GUIDANCE,
  WORKOUT_ARC,
  WORKOUT_BLOCKS,
  WORKOUT_CAROUSEL,
  WORKOUT_MOCK_PREVIEW_OPTIONS,
} from '../src/features/workout/workoutModel';

afterEach(() => {
  jest.useRealTimers();
});

it('records non-API symptom fixtures separately as mock states', () => {
  expect(WORKOUT_MOCK_PREVIEW_OPTIONS).toEqual([
    { id: 'symptom-mild', label: '경미한 불편 (mock)' },
    { id: 'symptom-severe', label: '중대한 이상 반응 (mock)' },
  ]);
});

function layoutCarousel(width = 390) {
  fireEvent(screen.getByTestId('workout-carousel'), 'layout', {
    nativeEvent: {
      layout: { height: 320, width, x: 0, y: 0 },
    },
  });
}

function momentumTo(offsetX: number) {
  fireEvent(screen.getByTestId('workout-carousel'), 'momentumScrollEnd', {
    nativeEvent: { contentOffset: { x: offsetX, y: 0 } },
  });
}

const API_PLAN: WorkoutPlan = {
  plan_id: 'plan-api',
  action_code: 'KEEP',
  training_type_code: 'STRENGTH',
  body_focus_code: 'FULL_BODY',
  requested_duration_minutes: 10,
  estimated_duration_seconds: 600,
  estimated_calories_burned: 40,
  setup_seconds: 0,
  warmup_seconds: 60,
  cooldown_seconds: 60,
  items: [
    {
      plan_item_id: 'plan-item-api',
      exercise_id: 'exercise-api',
      exercise_name: '의자 스쿼트',
      sequence: 1,
      tier_code: 'CORE',
      sets: 2,
      reps: 8,
      work_seconds: 120,
      rest_seconds: 30,
      transition_seconds: 15,
      estimated_item_seconds: 240,
      instruction_available: false,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    },
  ],
};

function sessionDetail(status: 'PLANNED' | 'IN_PROGRESS' = 'PLANNED') {
  return {
    session_id: 'session-api',
    local_date: '2026-08-19',
    status_code: status,
    completed_item_count: 0,
    total_item_count: 1,
    requested_duration_minutes: 10,
    items: [
      {
        plan_item_id: 'plan-item-api',
        exercise_id: 'exercise-api',
        exercise_name: '의자 스쿼트',
        status_code: 'PENDING' as const,
        sets: 2,
        reps: 8,
        work_seconds_per_set: null,
        completed_at: null,
      },
    ],
    feedback: null,
    not_completed_reason_code: null,
    started_at: status === 'IN_PROGRESS' ? '2026-08-19T09:00:00+09:00' : null,
    finished_at: null,
  };
}

function workoutApi(overrides: Partial<Api> = {}): Api {
  return {
    getWorkoutSession: jest.fn(async () => sessionDetail()),
    startSession: jest.fn(async (_sessionId: string, startedAt: string) => ({
      session_id: 'session-api',
      status_code: 'IN_PROGRESS' as const,
      started_at: startedAt,
      items: [
        {
          plan_item_id: 'plan-item-api',
          status_code: 'PENDING' as const,
          completed_at: null,
        },
      ],
      current_plan_item_id: 'plan-item-api',
    })),
    recordTimerEvent: jest.fn(async () => ({ event_id: 'timer-event-api' })),
    getExerciseVariants: jest.fn(async (exerciseId: string) => ({
      source_exercise_id: exerciseId,
      source_required_equipment_codes: ['BODYWEIGHT'],
      items: [],
      catalog_version: 'test-catalog-v1',
      alternative_set_version: null,
    })),
    ...overrides,
  } as unknown as Api;
}

describe('WorkoutScreen', () => {
  it('uses set and repetition prescriptions for every preview workout block', () => {
    render(<WorkoutScreen />);

    expect(screen.getByText('1세트 × 10회 · 스트레칭')).toBeOnTheScreen();
    expect(screen.getByText('1세트 × 10회 · 호흡 정리')).toBeOnTheScreen();
    expect(screen.queryByText(/세트 × \d+(?:분|초)/)).toBeNull();
  });

  it('shows the workout mascot inside a circular white frame', () => {
    render(<WorkoutScreen />);

    expect(screen.getByText('지금 할 운동')).toBeOnTheScreen();
    expect(screen.getByTestId('workout-warmup-mascot').props.source).toBe(
      imageAssets.mascotWarmupWalk,
    );
    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-mascot-frame').props.style,
      ),
    ).toMatchObject({
      width: 124.8,
      height: 124.8,
      overflow: 'hidden',
      borderRadius: 62.4,
      backgroundColor: '#FFFFFF',
    });
  });

  it('keeps the carousel and arc constants faithful to the handoff', () => {
    expect(WORKOUT_CAROUSEL).toEqual({
      CARD_HEIGHT: 320,
      CARD_WIDTH: 230,
      GAP: 20,
      STRIDE: 250,
    });
    expect(WORKOUT_ARC).toEqual({
      INPUT_OFFSETS: [-2, -1, 0, 1, 2],
      LIFT: [104, 26, 0, 26, 104],
      OPACITY: [0.31, 0.43, 1, 0.43, 0.31],
      ROTATE: ['14deg', '7deg', '0deg', '-7deg', '-14deg'],
      SCALE: [0.74, 0.87, 1, 0.87, 0.74],
    });
  });

  it('preserves the 390 x 844 proportions while bounding responsive growth', () => {
    expect(getWorkoutResponsiveLayout({ width: 320, height: 568 })).toEqual(
      expect.objectContaining({
        cardHeight: 210,
        cardWidth: 230,
        headerTopPadding: 28,
        mascotHeight: 90,
        scale: 0.9,
        stride: 250,
      }),
    );
    expect(getWorkoutResponsiveLayout({ width: 390, height: 844 })).toEqual(
      expect.objectContaining({
        cardHeight: 280,
        cardWidth: 230,
        mascotHeight: 180,
        scale: 1,
        stride: 250,
      }),
    );
    expect(getWorkoutResponsiveLayout({ width: 430, height: 932 })).toEqual(
      expect.objectContaining({
        cardHeight: 309,
        cardWidth: 254,
        gap: 22,
        headerTopPadding: 60,
        mascotHeight: 199,
        stride: 276,
      }),
    );
    expect(getWorkoutResponsiveLayout({ width: 768, height: 1024 })).toEqual(
      expect.objectContaining({
        cardHeight: 336,
        cardWidth: 276,
        contentMaxWidth: 1100,
        mascotHeight: 216,
        scale: 1.2,
        stride: 300,
      }),
    );
    expect(getWorkoutResponsiveLayout({ width: 1440, height: 900 })).toEqual(
      expect.objectContaining({
        cardWidth: 265,
        contentMaxWidth: 1100,
        stride: 288,
      }),
    );
  });

  it('configures snap pagination and measures symmetric card padding', async () => {
    await render(<WorkoutScreen />);

    const carousel = screen.getByTestId('workout-carousel');
    expect(carousel.props.snapToInterval).toBe(300);
    expect(carousel.props.snapToAlignment).toBe('start');
    expect(carousel.props.decelerationRate).toBe('fast');
    expect(carousel.props.showsHorizontalScrollIndicator).toBe(false);
    expect(carousel.props.scrollEventThrottle).toBe(16);

    layoutCarousel(390);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-carousel').props.contentContainerStyle,
      ).paddingHorizontal,
    ).toBe(57);
  });

  it.each([
    [-500, 5, 0],
    [124, 5, 0],
    [126, 5, 1],
    [624, 5, 2],
    [9999, 5, 4],
    [500, 0, 0],
  ])(
    'clamps momentum offset %s with %s blocks to page %s',
    (offset, count, expected) => {
      expect(clampWorkoutPageIndex(offset, count)).toBe(expected);
    },
  );

  it.each([
    [2, 5, -80, 0, 3],
    [2, 5, 80, 0, 1],
    [2, 5, -10, -0.4, 3],
    [2, 5, 10, 0.4, 1],
    [2, 5, -10, -0.1, 2],
    [0, 5, 80, 0, 0],
    [4, 5, -80, 0, 4],
    [0, 0, -80, 0, 0],
  ])(
    'moves page %s of %s after horizontal drag %s at velocity %s to %s',
    (current, count, dragX, velocityX, expected) => {
      expect(
        workoutPageAfterHorizontalDrag(current, count, dragX, velocityX),
      ).toBe(expected);
    },
  );

  it('enables mouse dragging on the web carousel without changing native scrolling', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });
    try {
      await render(<WorkoutScreen />);

      const dragSurface = screen.getByTestId('workout-carousel-drag-surface');
      expect(StyleSheet.flatten(dragSurface.props.style)).toMatchObject({
        cursor: 'grab',
        touchAction: 'pan-y',
        width: '100%',
      });
      expect(dragSurface.props.onMoveShouldSetResponderCapture).toEqual(
        expect.any(Function),
      );
      expect(screen.getByTestId('workout-carousel').props.horizontal).toBe(
        true,
      );
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  });

  it('updates the visible page from momentum without changing the completion index', async () => {
    const onBlockStatusChange = jest.fn();
    await render(<WorkoutScreen onBlockStatusChange={onBlockStatusChange} />);

    momentumTo(9999);
    expect(screen.getByText('다른 블록 보는 중')).toBeOnTheScreen();
    expect(screen.getByText('1 / 5 블록')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '준비 운동 블록 격파' }),
    ).toBeDisabled();
    fireEvent.press(
      screen.getByRole('button', { name: '준비 운동 블록 격파' }),
    );
    expect(onBlockStatusChange).not.toHaveBeenCalled();

    momentumTo(-999);
    expect(screen.getByText('좌우로 밀어 다른 블록 보기')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '준비 운동 블록 격파' }),
    );
    expect(onBlockStatusChange).toHaveBeenCalledWith('warm-up', 'COMPLETED');
  });

  it('makes every dot selectable, scrolls by stride, and applies state colors', async () => {
    const scrollTo = jest.spyOn(ScrollView.prototype, 'scrollTo');
    await render(<WorkoutScreen previewState="partial" />);
    layoutCarousel();
    scrollTo.mockClear();

    const initialDot = screen.getByTestId('workout-dot-2');
    expect(StyleSheet.flatten(initialDot.props.style)).toMatchObject({
      backgroundColor: '#958476',
      height: 8,
      width: 22,
    });
    expect(
      StyleSheet.flatten(screen.getByTestId('workout-dot-0').props.style),
    ).toMatchObject({ backgroundColor: '#F6BA50', height: 8, width: 8 });

    fireEvent.press(screen.getByRole('button', { name: '4번째 블록 보기' }));
    expect(scrollTo).toHaveBeenLastCalledWith({ animated: true, x: 900 });
    expect(
      StyleSheet.flatten(screen.getByTestId('workout-dot-3').props.style),
    ).toMatchObject({ backgroundColor: '#958476', height: 8, width: 22 });
    expect(screen.getByText('다른 블록 보는 중')).toBeOnTheScreen();
    scrollTo.mockRestore();
  });

  it('expands and collapses every tip for a block with accessibility state', async () => {
    await render(<WorkoutScreen />);

    const expand = screen.getAllByRole('button', {
      name: '자세 · 설명 보기',
    })[1]!;
    expect(expand.props.accessibilityState).toEqual({ expanded: false });
    fireEvent.press(expand);

    const collapse = screen.getByRole('button', { name: '설명 접기' });
    expect(collapse.props.accessibilityState).toEqual({ expanded: true });
    expect(screen.getByTestId('workout-detail-overlay')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-detail-sheet').props.style,
      ),
    ).toMatchObject({ maxHeight: '82%', maxWidth: 640, width: '100%' });
    expect(screen.getByTestId('workout-detail-scroll').props).toMatchObject({
      nestedScrollEnabled: true,
      showsVerticalScrollIndicator: true,
    });
    WORKOUT_BLOCKS[1]!.tips.forEach((tip) => {
      expect(screen.getByText(tip)).toBeOnTheScreen();
    });
    fireEvent.press(collapse);
    WORKOUT_BLOCKS[1]!.tips.forEach((tip) => {
      expect(screen.queryByText(tip)).toBeNull();
    });
  });

  it.each([
    [11, '00:11'],
    [3599, '59:59'],
    [3600, '60:00'],
    [3690, '61:30'],
  ])('formats %s seconds as %s without an hours field', (seconds, expected) => {
    expect(formatWorkoutTime(seconds)).toBe(expected);
  });

  it('renders the elapsed timer with the readable brand font', async () => {
    await render(<WorkoutScreen />);

    const timerStyle = StyleSheet.flatten(
      screen.getByText('00:00').props.style,
    );
    expect(timerStyle.fontFamily).toBe(fontFamilies.brand);
    expect(timerStyle.fontWeight).toBe('600');
  });

  it('counts elapsed time without changing block completion', async () => {
    jest.useFakeTimers();
    const onBlockStatusChange = jest.fn();
    await render(<WorkoutScreen onBlockStatusChange={onBlockStatusChange} />);

    expect(screen.getByLabelText('운동 시간 00:00')).toBeOnTheScreen();
    await act(() => jest.advanceTimersByTime(2000));
    expect(screen.getByLabelText('운동 시간 00:02')).toBeOnTheScreen();
    expect(onBlockStatusChange).not.toHaveBeenCalled();
    expect(screen.getByText('완료 0 / 5')).toBeOnTheScreen();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('uses the three exact timer captions for active, paused, and rest states', async () => {
    await render(<WorkoutScreen />);
    expect(screen.getByText('운동 시간')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '일시정지' }));
    expect(screen.getByText('일시정지됨 · 기록용')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '재개' }));
    fireEvent.press(screen.getByRole('button', { name: '선택 휴식 타이머' }));
    expect(
      screen.getByText('휴식 중 · 타이머 정지', {
        includeHiddenElements: true,
      }),
    ).toBeOnTheScreen();
  });

  it('keeps the bottom actions equal and the smash action flat', async () => {
    await render(<WorkoutScreen />);

    const smashStyle = StyleSheet.flatten(
      screen.getByTestId('workout-smash-action').props.style,
    );
    const restStyle = StyleSheet.flatten(
      screen.getByTestId('workout-rest-action').props.style,
    );

    expect(smashStyle).toMatchObject({ flex: 1, flexBasis: 0 });
    expect(restStyle).toMatchObject({ flex: 1, flexBasis: 0 });
    expect(smashStyle.height).toBeCloseTo(69.6);
    expect(restStyle.height).toBeCloseTo(69.6);
    expect(smashStyle.borderBottomWidth).toBeUndefined();
    expect(smashStyle.shadowColor).toBeUndefined();
    expect(smashStyle.elevation).toBeUndefined();
  });

  it('keeps the disabled smash action flat', async () => {
    await render(<WorkoutScreen previewState="all-blocks" />);

    const smashStyle = StyleSheet.flatten(
      screen.getByTestId('workout-smash-action').props.style,
    );
    expect(smashStyle.backgroundColor).toBe('#CFCCC5');
    expect(smashStyle.borderBottomWidth).toBeUndefined();
    expect(smashStyle.shadowColor).toBeUndefined();
    expect(smashStyle.elevation).toBeUndefined();
  });

  it('uses the original two-sided header layout and text-only stop action', async () => {
    await render(<WorkoutScreen />);

    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-header-top-row').props.style,
      ),
    ).toMatchObject({
      flexDirection: 'row',
      justifyContent: 'space-between',
    });
    const pauseStyle = StyleSheet.flatten(
      screen.getByTestId('workout-pause-action').props.style,
    );
    expect(pauseStyle).toMatchObject({
      backgroundColor: 'rgba(255,255,255,.18)',
    });
    expect(pauseStyle.borderRadius).toBeCloseTo(21.6);
    expect(pauseStyle.height).toBeCloseTo(62.4);
    expect(pauseStyle.width).toBeCloseTo(62.4);
    const stopStyle = StyleSheet.flatten(
      screen.getByTestId('workout-stop-action').props.style,
    );
    expect(stopStyle).toMatchObject({
      backgroundColor: '#FDECE7',
      borderColor: '#F1BFAE',
      borderWidth: 1.5,
    });
    expect(stopStyle.borderRadius).toBeCloseTo(21.6);
    expect(stopStyle.height).toBeCloseTo(62.4);
    const stopLabelStyle = StyleSheet.flatten(
      screen.getByText('중단').props.style,
    );
    expect(stopLabelStyle.color).toBe('#A23F2A');
    expect(stopLabelStyle.fontWeight).toBe('400');
    expect(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    ).toHaveTextContent('중단');
    expect(screen.queryByText('■')).toBeNull();
    expect(screen.queryByTestId('workout-stop-mark')).toBeNull();
  });

  it('matches the check-in action styling for stop confirmation while keeping the red tone', async () => {
    await render(<WorkoutScreen />);

    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );

    const stopButton = screen.getByRole('button', { name: '중단하기' });
    const stopButtonStyle = StyleSheet.flatten(stopButton.props.style);
    const stopLabelStyle = StyleSheet.flatten(
      screen.getByText('중단하기').props.style,
    );
    const stopGradient = screen.getByTestId('workout-stop-confirm-gradient');

    expect(stopButtonStyle).toMatchObject({
      width: '100%',
      borderColor: 'rgba(142, 50, 38, 0.8)',
      borderWidth: 1,
      borderRadius: 18,
      padding: 17,
      shadowColor: '#8E3226',
      shadowOpacity: 0.11,
      shadowRadius: 6,
      elevation: 3,
    });
    expect(stopButtonStyle.backgroundColor).toBeUndefined();
    expect(stopButtonStyle.borderBottomWidth).toBeUndefined();
    expect(stopLabelStyle).toMatchObject({
      color: '#FFFFFF',
      fontSize: 18,
      fontWeight: '400',
    });
    expect(stopGradient.props.colors).toEqual(
      ['#D97260', '#CC5A47', '#C2503C'].map(processColor),
    );
    expect(stopGradient.props.locations).toEqual([0, 0.55, 1]);
  });

  it('explains that 끼끼 will provide the reporting outcome', async () => {
    await render(<WorkoutScreen />);

    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );

    expect(
      screen.getByText(
        '불편·이상 반응을 보고하면 운동을 중단할지, 계속할지 끼끼가 알려줘요',
      ),
    ).toBeOnTheScreen();
    expect(screen.queryByText(/여기까지 완료한 블록/)).toBeNull();
  });

  it('returns from symptom reporting to the previous stop confirmation sheet', async () => {
    const onPauseChange = jest.fn();
    await render(<WorkoutScreen onPauseChange={onPauseChange} />);

    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '불편·이상 반응 먼저 보고하기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '취소' }));

    expect(
      screen.getByRole('header', { name: '지금 운동을 중단할까요?' }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByRole('header', { name: '불편·이상 반응 보고' }),
    ).toBeNull();
    expect(onPauseChange).toHaveBeenCalledTimes(1);
    expect(onPauseChange).toHaveBeenCalledWith(true);
  });

  it('reports only the current block through the explicit smash action and restarts the burst', async () => {
    const onBlockStatusChange = jest.fn();
    await render(<WorkoutScreen onBlockStatusChange={onBlockStatusChange} />);
    layoutCarousel();

    expect(screen.queryByText('격파!')).toBeNull();
    fireEvent.press(
      screen.getByRole('button', { name: '준비 운동 블록 격파' }),
    );
    expect(onBlockStatusChange).toHaveBeenCalledWith('warm-up', 'COMPLETED');
    expect(screen.getByTestId('workout-smash-burst')).toHaveTextContent(
      '격파!',
    );
    expect(screen.getByText('완료 1 / 5')).toBeOnTheScreen();
    expect(screen.getByText('2 / 5 블록')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '푸시업 블록 격파' }));
    expect(onBlockStatusChange).toHaveBeenLastCalledWith(
      'push-up',
      'COMPLETED',
    );
    expect(screen.getByTestId('workout-smash-burst')).toHaveTextContent(
      '격파!',
    );
  });

  it('does not turn all locally completed blocks into an official result', async () => {
    await render(<WorkoutScreen previewState="all-blocks" />);

    expect(screen.getByText('완료 5 / 5')).toBeOnTheScreen();
    expect(screen.getByText('5 / 5 블록')).toBeOnTheScreen();
    expect(
      screen.queryByRole('header', { name: '오늘 운동 완료!' }),
    ).toBeNull();
  });

  it('opens the preview result immediately after the last explicit smash', async () => {
    await render(<WorkoutScreen />);

    for (const block of WORKOUT_BLOCKS) {
      fireEvent.press(
        screen.getByRole('button', { name: `${block.name} 블록 격파` }),
      );
    }

    expect(
      screen.getByRole('header', { name: '오늘 운동 완료!' }),
    ).toBeOnTheScreen();
  });

  it('keeps rest separate, starts at 60 seconds, adds 30 seconds, and ends explicitly', async () => {
    const onBlockStatusChange = jest.fn();
    const onRestChange = jest.fn();
    await render(
      <WorkoutScreen
        onBlockStatusChange={onBlockStatusChange}
        onRestChange={onRestChange}
        previewState="rest"
      />,
    );

    expect(screen.getByText('선택 휴식')).toBeOnTheScreen();
    expect(screen.getByLabelText('남은 휴식 01:00')).toBeOnTheScreen();
    expect(
      screen.getByText(
        '휴식 타이머는 선택 사항이에요. 완료 상태는 직접 체크할 때만 바뀝니다.',
      ),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '+30초' }));
    expect(screen.getByLabelText('남은 휴식 01:30')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '휴식 끝' }));
    expect(onRestChange).toHaveBeenCalledWith(false);
    expect(onBlockStatusChange).not.toHaveBeenCalled();
  });

  it('shows the exact offline fixture banner only in the offline state', async () => {
    const copy =
      '연결이 끊겼어요. 진행 상태는 기기에 임시 저장되고, 연결되면 자동으로 올려드려요.';
    const view = await render(<WorkoutScreen />);
    expect(screen.queryByText(copy)).toBeNull();

    view.rerender(<WorkoutScreen previewState="offline" />);
    expect(screen.getByText(copy)).toBeOnTheScreen();
    expect(screen.getByLabelText('운동 시간 00:11')).toBeOnTheScreen();
  });

  it('allows a caution report to continue with the approved mild copy', async () => {
    const onSafetyEvent = jest.fn();
    await render(
      <WorkoutScreen
        onSafetyEvent={onSafetyEvent}
        previewState="symptom-mild"
      />,
    );

    expect(screen.getByText(SAFETY_GUIDANCE.mild)).toBeOnTheScreen();
    const reportButton = screen.getByRole('button', {
      name: '보고만 하고 계속하기',
    });
    const reportButtonStyle = StyleSheet.flatten(reportButton.props.style);
    const reportLabelStyle = StyleSheet.flatten(
      screen.getByText('보고만 하고 계속하기').props.style,
    );
    const reportGradient = screen.getByTestId(
      'workout-report-continue-gradient',
    );

    expect(reportButtonStyle).toMatchObject({
      width: '100%',
      borderColor: 'rgba(142, 50, 38, 0.8)',
      borderWidth: 1,
      borderRadius: 18,
      padding: 17,
      shadowColor: '#8E3226',
      shadowOpacity: 0.11,
      shadowRadius: 6,
      elevation: 3,
    });
    expect(reportButtonStyle.backgroundColor).toBeUndefined();
    expect(reportButtonStyle.borderBottomWidth).toBeUndefined();
    expect(reportLabelStyle).toMatchObject({
      color: '#FFFFFF',
      fontSize: 18,
      fontWeight: '400',
    });
    expect(reportGradient.props.colors).toEqual(
      ['#D97260', '#CC5A47', '#C2503C'].map(processColor),
    );
    expect(reportGradient.props.locations).toEqual([0, 0.55, 1]);
    fireEvent.press(reportButton);
    expect(onSafetyEvent).toHaveBeenCalledWith(
      { symptomCode: 'PAIN', severityCode: 'MILD' },
      'SHOW_CAUTION',
    );
    expect(
      screen.queryByRole('header', { name: '불편·이상 반응 보고' }),
    ).toBeNull();
  });

  it('does not offer a continue path for an emergency instruction', async () => {
    await render(<WorkoutScreen previewState="symptom-severe" />);

    expect(screen.getByText(SAFETY_GUIDANCE.emergency)).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '보고하고 안전 중단' }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByRole('button', { name: '보고만 하고 계속하기' }),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: '취소' })).toBeNull();
  });

  it('emits a machine-readable not-completed reason', async () => {
    const onNotCompleted = jest.fn();
    await render(
      <WorkoutScreen
        onNotCompleted={onNotCompleted}
        previewState="not-completed"
      />,
    );
    fireEvent.press(screen.getByRole('button', { name: '시간이 부족했어요' }));
    expect(onNotCompleted).toHaveBeenCalledWith('TIME_SHORTAGE');
  });

  it.each([
    {
      previewState: 'completed' as const,
      title: '오늘 운동 완료!',
      subtitle: '완료한 블록이 이번 주 루틴에 반영됐어요.',
      elapsed: '36:00',
      completed: '5/5',
      status: '완료',
      report: null,
    },
    {
      previewState: 'stopped' as const,
      title: '중단했어요',
      subtitle: '여기까지의 기록은 저장돼요. 회복이 우선입니다.',
      elapsed: '13:22',
      completed: '2/5',
      status: '중단',
      report: '보고된 이상 반응 — 호흡 곤란 · 심함',
    },
  ])(
    'shows the original $previewState result fixture details',
    async ({
      completed,
      elapsed,
      previewState,
      report,
      status,
      subtitle,
      title,
    }) => {
      const onBackHome = jest.fn();
      await render(
        <WorkoutScreen onBackHome={onBackHome} previewState={previewState} />,
      );

      expect(screen.getByRole('header', { name: title })).toBeOnTheScreen();
      expect(screen.getByText(subtitle)).toBeOnTheScreen();
      expect(screen.getByText(elapsed)).toBeOnTheScreen();
      expect(screen.getByText(completed)).toBeOnTheScreen();
      expect(screen.getAllByText(status).length).toBeGreaterThan(0);
      WORKOUT_BLOCKS.forEach((block) => {
        expect(screen.getByText(block.name)).toBeOnTheScreen();
      });
      if (report) {
        expect(screen.getByText(report)).toBeOnTheScreen();
      } else {
        expect(screen.queryByText(/보고된 이상 반응/)).toBeNull();
      }
      fireEvent.press(
        screen.getByRole('button', { name: '기록 저장하고 홈으로' }),
      );
      expect(onBackHome).toHaveBeenCalledTimes(1);
    },
  );
});

describe('WorkoutScreen API mode', () => {
  it('shows reviewed variants during the workout without changing session state', async () => {
    const getExerciseVariants = jest.fn(async (exerciseId: string) => ({
      source_exercise_id: exerciseId,
      source_required_equipment_codes: ['BODYWEIGHT', 'CHAIR'],
      items: [
        {
          exercise_id: 'exercise-bodyweight-squat',
          exercise_name: '맨몸 스쿼트',
          required_equipment_codes: ['BODYWEIGHT'],
          instruction_summary:
            '의자 없이 엉덩이를 뒤로 보내며 가능한 범위까지 앉아요.',
          form_cues: ['무릎과 발끝 방향을 맞춰요.'],
          media_asset_key: null,
          goal_preservation_code: 'GENERAL_FITNESS',
        },
      ],
      catalog_version: 'test-catalog-v1',
      alternative_set_version: 'test-alternatives-v1',
    }));
    const updateSessionItem = jest.fn<Api['updateSessionItem']>();
    const api = workoutApi({ getExerciseVariants, updateSessionItem });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={jest.fn()}
      />,
    );

    const equipmentAction = await screen.findByRole('button', {
      name: '의자 스쿼트 장비가 없을 때 보기',
    });
    expect(StyleSheet.flatten(equipmentAction.props.style)).toMatchObject({
      alignSelf: 'flex-start',
      paddingHorizontal: 0,
    });
    expect(
      StyleSheet.flatten(equipmentAction.props.style).borderWidth,
    ).toBeUndefined();
    expect(
      StyleSheet.flatten(equipmentAction.props.style).backgroundColor,
    ).toBeUndefined();

    fireEvent.press(equipmentAction);

    expect(
      screen.getByRole('header', { name: '의자 스쿼트 장비 안내' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('의자')).toBeOnTheScreen();
    expect(screen.getByText('맨몸 스쿼트')).toBeOnTheScreen();
    expect(
      screen.getByText(
        '의자 없이 엉덩이를 뒤로 보내며 가능한 범위까지 앉아요.',
      ),
    ).toBeOnTheScreen();
    expect(updateSessionItem).not.toHaveBeenCalled();
    expect(getExerciseVariants).toHaveBeenCalledWith(
      'exercise-api',
      expect.any(AbortSignal),
    );
  });

  it('loads reviewed exercise guidance inside the scrollable detail sheet', async () => {
    const plan = {
      ...API_PLAN,
      items: [{ ...API_PLAN.items[0]!, instruction_available: true }],
    };
    const getExercise = jest.fn(async () => ({
      exercise_id: 'exercise-api',
      exercise_name: '의자 스쿼트',
      training_type_code: 'STRENGTH',
      primary_body_area_codes: ['KNEE'],
      instruction_summary: '발바닥을 바닥에 고르게 두고 천천히 움직여요.',
      form_cues: [
        '무릎과 발끝의 방향을 맞춰요.',
        '통증 없는 범위에서 진행해요.',
      ],
      media_asset_key: null,
      mascot_animation_asset_key: null,
      instruction_content_version: 'test-v1',
    }));
    const api = workoutApi({ getExercise });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    expect(screen.getByText('2세트 × 8회')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '자세 · 설명 보기' }));

    expect(screen.getByTestId('workout-detail-scroll')).toBeOnTheScreen();
    expect(
      await screen.findByText('발바닥을 바닥에 고르게 두고 천천히 움직여요.'),
    ).toBeOnTheScreen();
    expect(getExercise).toHaveBeenCalledWith(
      'exercise-api',
      expect.any(AbortSignal),
    );
  });

  it('builds the carousel and progress count from every Home plan item', async () => {
    const names = ['워밍업 걷기', '스쿼트', '플랭크'];
    const plan: WorkoutPlan = {
      ...API_PLAN,
      items: names.map((exerciseName, index) => ({
        ...API_PLAN.items[0]!,
        plan_item_id: `dynamic-item-${index + 1}`,
        exercise_id: `dynamic-exercise-${index + 1}`,
        exercise_name: exerciseName,
        sequence: index + 1,
      })),
    };
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => ({
        ...sessionDetail('IN_PROGRESS'),
        total_item_count: plan.items.length,
        items: plan.items.map((item) => ({
          plan_item_id: item.plan_item_id,
          exercise_id: item.exercise_id,
          exercise_name: item.exercise_name,
          status_code: 'PENDING' as const,
          sets: item.sets,
          reps: item.reps,
          work_seconds_per_set: item.work_seconds,
          completed_at: null,
        })),
      })),
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    expect(screen.getByText('1 / 3 블록')).toBeOnTheScreen();
    expect(screen.getByText('완료 0 / 3')).toBeOnTheScreen();
    names.forEach((name) =>
      expect(screen.getAllByText(name).length).toBeGreaterThan(0),
    );
    expect(screen.getAllByTestId(/workout-card-/)).toHaveLength(3);
  });

  it('uses the Home sequence even when the plan item array is unsorted', async () => {
    const first = {
      ...API_PLAN.items[0]!,
      plan_item_id: 'ordered-first',
      exercise_name: '먼저 할 운동',
      sequence: 1,
    };
    const second = {
      ...API_PLAN.items[0]!,
      plan_item_id: 'ordered-second',
      exercise_name: '나중에 할 운동',
      sequence: 2,
    };
    const plan = { ...API_PLAN, items: [second, first] };
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => ({
        ...sessionDetail('IN_PROGRESS'),
        total_item_count: 2,
        items: [second, first].map((item) => ({
          plan_item_id: item.plan_item_id,
          exercise_id: item.exercise_id,
          exercise_name: item.exercise_name,
          status_code: 'PENDING' as const,
          sets: item.sets,
          reps: item.reps,
          work_seconds_per_set: item.work_seconds,
          completed_at: null,
        })),
      })),
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    expect(
      within(screen.getByTestId('workout-card-0')).getByText('먼저 할 운동'),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('workout-card-1')).getByText('나중에 할 운동'),
    ).toBeOnTheScreen();
  });

  it('advances the block UI before the server confirms completion', async () => {
    const secondItem = {
      ...API_PLAN.items[0]!,
      plan_item_id: 'plan-item-api-2',
      exercise_id: 'exercise-api-2',
      exercise_name: 'Second exercise',
      sequence: 2,
    };
    const plan = { ...API_PLAN, items: [API_PLAN.items[0]!, secondItem] };
    const firstResult = sessionDetail('IN_PROGRESS').items[0]!;
    const detail = {
      ...sessionDetail('IN_PROGRESS'),
      total_item_count: 2,
      items: [
        firstResult,
        {
          ...firstResult,
          plan_item_id: secondItem.plan_item_id,
          exercise_id: secondItem.exercise_id,
          exercise_name: secondItem.exercise_name,
        },
      ],
    };
    let releaseUpdate: (() => void) | undefined;
    const updateSessionItem = jest.fn(
      async (
        _sessionId: string,
        planItemId: string,
        statusCode: 'PENDING' | 'COMPLETED',
        recordedAt: string,
      ) => {
        await new Promise<void>((resolve) => {
          releaseUpdate = resolve;
        });
        return {
          session_id: 'session-api',
          status_code: 'IN_PROGRESS' as const,
          item: {
            plan_item_id: planItemId,
            status_code: statusCode,
            completed_at: statusCode === 'COMPLETED' ? recordedAt : null,
          },
          completed_item_count: 1,
          total_item_count: 2,
          next_pending_plan_item_id: secondItem.plan_item_id,
        };
      },
    );
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => detail),
      updateSessionItem,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId('workout-smash-action').props.accessibilityState
          .disabled,
      ).toBe(false),
    );
    expect(
      within(screen.getByTestId('workout-card-0')).queryByRole('button'),
    ).toBeNull();

    fireEvent.press(screen.getByTestId('workout-smash-action'));

    expect(updateSessionItem).toHaveBeenCalledTimes(1);
    expect(
      within(screen.getByTestId('workout-card-0')).getByRole('button'),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('workout-smash-burst')).toBeOnTheScreen();
    expect(
      screen.getByTestId('workout-smash-action').props.accessibilityState
        .disabled,
    ).toBe(true);

    await act(async () => {
      releaseUpdate?.();
    });
    await waitFor(() =>
      expect(
        screen.getByTestId('workout-smash-action').props.accessibilityState
          .disabled,
      ).toBe(false),
    );
  });

  it('rolls optimistic progress back after the server confirms it is pending', async () => {
    const getWorkoutSession = jest.fn(async () => sessionDetail('IN_PROGRESS'));
    let rejectUpdate: ((reason?: unknown) => void) | undefined;
    const updateSessionItem = jest.fn(
      () =>
        new Promise<SessionItemUpdateResponse>((_, reject) => {
          rejectUpdate = reject;
        }),
    );
    const api = workoutApi({ getWorkoutSession, updateSessionItem });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId('workout-smash-action').props.accessibilityState
          .disabled,
      ).toBe(false),
    );
    fireEvent.press(screen.getByTestId('workout-smash-action'));
    expect(
      within(screen.getByTestId('workout-card-0')).getByRole('button'),
    ).toBeOnTheScreen();

    await act(async () => {
      rejectUpdate?.(new Error('response lost'));
    });

    await waitFor(() =>
      expect(
        within(screen.getByTestId('workout-card-0')).queryByRole('button'),
      ).toBeNull(),
    );
    expect(getWorkoutSession).toHaveBeenCalledTimes(2);
  });

  it('keeps optimistic progress when a reread confirms the lost response committed', async () => {
    const secondItem = {
      ...API_PLAN.items[0]!,
      plan_item_id: 'plan-item-api-2',
      exercise_id: 'exercise-api-2',
      exercise_name: 'Second exercise',
      sequence: 2,
    };
    const plan = { ...API_PLAN, items: [API_PLAN.items[0]!, secondItem] };
    const firstResult = sessionDetail('IN_PROGRESS').items[0]!;
    const pendingDetail: WorkoutSessionDetailResponse = {
      ...sessionDetail('IN_PROGRESS'),
      total_item_count: 2,
      items: [
        firstResult,
        {
          ...firstResult,
          plan_item_id: secondItem.plan_item_id,
          exercise_id: secondItem.exercise_id,
          exercise_name: secondItem.exercise_name,
        },
      ],
    };
    const completedDetail: WorkoutSessionDetailResponse = {
      ...pendingDetail,
      completed_item_count: 1,
      items: [
        {
          ...pendingDetail.items[0]!,
          status_code: 'COMPLETED' as const,
          completed_at: '2026-08-19T09:01:00+09:00',
        },
        pendingDetail.items[1]!,
      ],
    };
    const getWorkoutSession = jest
      .fn<Api['getWorkoutSession']>()
      .mockResolvedValueOnce(pendingDetail)
      .mockResolvedValueOnce(completedDetail);
    const updateSessionItem = jest.fn(async () => {
      throw new Error('response lost');
    });
    const api = workoutApi({ getWorkoutSession, updateSessionItem });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId('workout-smash-action').props.accessibilityState
          .disabled,
      ).toBe(false),
    );
    fireEvent.press(screen.getByTestId('workout-smash-action'));

    await waitFor(() => expect(getWorkoutSession).toHaveBeenCalledTimes(2));
    expect(
      within(screen.getByTestId('workout-card-0')).getByRole('button'),
    ).toBeOnTheScreen();
    expect(
      screen.getByTestId('workout-smash-action').props.accessibilityState
        .disabled,
    ).toBe(false);
  });

  it('loads, starts and auto-finishes after the server confirms the last block', async () => {
    const updateSessionItem = jest.fn(
      async (
        _sessionId: string,
        planItemId: string,
        _statusCode: 'PENDING' | 'COMPLETED',
        recordedAt: string,
      ) => ({
        session_id: 'session-api',
        status_code: 'IN_PROGRESS' as const,
        item: {
          plan_item_id: planItemId,
          status_code: _statusCode,
          completed_at: _statusCode === 'COMPLETED' ? recordedAt : null,
        },
        completed_item_count: _statusCode === 'COMPLETED' ? 1 : 0,
        total_item_count: 1,
        next_pending_plan_item_id: null,
      }),
    );
    const finishSession = jest.fn(
      async (_sessionId: string, endedAt: string, elapsed: number) => ({
        session_id: 'session-api',
        status_code: 'COMPLETED' as const,
        ended_at: endedAt,
        completed_item_count: 1,
        total_item_count: 1,
        actual_elapsed_seconds: elapsed,
        estimated_calories_burned: 40,
      }),
    );
    const onOutcome = jest.fn();
    const api = workoutApi({ updateSessionItem, finishSession });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={onOutcome}
      />,
    );

    await waitFor(() => expect(api.startSession).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '의자 스쿼트 블록 격파' }),
    );
    await waitFor(() => expect(updateSessionItem).toHaveBeenCalledTimes(1));
    expect(screen.getByText('완료 1 / 1')).toBeOnTheScreen();
    await waitFor(() =>
      expect(onOutcome).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'finished' }),
      ),
    );
    expect(finishSession).toHaveBeenCalledTimes(1);
    expect(api.recordTimerEvent).toHaveBeenCalledWith(
      'session-api',
      'START',
      expect.any(String),
    );
    expect(api.recordTimerEvent).toHaveBeenCalledWith(
      'session-api',
      'END',
      expect.any(String),
    );
  });

  it('reopens a completed non-final block through the server', async () => {
    const secondItem = {
      ...API_PLAN.items[0]!,
      plan_item_id: 'plan-item-api-2',
      exercise_id: 'exercise-api-2',
      exercise_name: '플랭크',
      sequence: 2,
    };
    const plan = { ...API_PLAN, items: [API_PLAN.items[0]!, secondItem] };
    const updateSessionItem = jest.fn(
      async (
        _sessionId: string,
        planItemId: string,
        statusCode: 'PENDING' | 'COMPLETED',
        recordedAt: string,
      ) => ({
        session_id: 'session-api',
        status_code: 'IN_PROGRESS' as const,
        item: {
          plan_item_id: planItemId,
          status_code: statusCode,
          completed_at: statusCode === 'COMPLETED' ? recordedAt : null,
        },
        completed_item_count: statusCode === 'COMPLETED' ? 1 : 0,
        total_item_count: 2,
        next_pending_plan_item_id:
          statusCode === 'COMPLETED' ? 'plan-item-api-2' : 'plan-item-api',
      }),
    );
    const finishSession = jest.fn<Api['finishSession']>();
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => ({
        ...sessionDetail('IN_PROGRESS'),
        total_item_count: 2,
        items: [
          sessionDetail('IN_PROGRESS').items[0]!,
          {
            ...sessionDetail('IN_PROGRESS').items[0]!,
            plan_item_id: 'plan-item-api-2',
            exercise_id: 'exercise-api-2',
            exercise_name: '플랭크',
          },
        ],
      })),
      updateSessionItem,
      finishSession,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={plan}
        onOutcome={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '의자 스쿼트 블록 격파' }),
    );
    await waitFor(() =>
      expect(screen.getByText('완료 1 / 2')).toBeOnTheScreen(),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '의자 스쿼트 완료 취소' }),
    );

    await waitFor(() =>
      expect(updateSessionItem).toHaveBeenLastCalledWith(
        'session-api',
        'plan-item-api',
        'PENDING',
        expect.any(String),
      ),
    );
    expect(screen.getByText('완료 0 / 2')).toBeOnTheScreen();
    expect(finishSession).not.toHaveBeenCalled();
  });

  it('returns from API safety reporting to stop confirmation without submitting', async () => {
    const reportSafetyEvent = jest.fn(async () => ({
      event_id: 'unused-safety-event',
      instruction_code: 'SHOW_CAUTION' as const,
      resulting_action_code: null,
      session_status_code: 'IN_PROGRESS' as const,
      guidance_code: 'MILD_DISCOMFORT_CAUTION',
      guidance: '사용되지 않는 안전 안내',
      pressure_notifications_allowed: true,
    }));
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => sessionDetail('IN_PROGRESS')),
      reportSafetyEvent,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '불편·이상 반응 먼저 보고하기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '취소' }));

    expect(
      screen.getByRole('header', { name: '지금 운동을 중단할까요?' }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByRole('header', { name: '불편·이상 반응 보고' }),
    ).toBeNull();
    expect(reportSafetyEvent).not.toHaveBeenCalled();
  });

  it('sends reviewed safety fields and renders the server guidance', async () => {
    const reportSafetyEvent = jest.fn(async () => ({
      event_id: 'safety-api',
      instruction_code: 'SHOW_CAUTION' as const,
      resulting_action_code: null,
      session_status_code: 'IN_PROGRESS' as const,
      guidance_code: 'MILD_DISCOMFORT_CAUTION',
      guidance: '서버에서 확인한 안전 안내입니다.',
      pressure_notifications_allowed: true,
    }));
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => sessionDetail('IN_PROGRESS')),
      reportSafetyEvent,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '불편·이상 반응 먼저 보고하기' }),
    );
    expect(screen.queryByRole('checkbox', { name: '전신' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: '기타 부위' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: '목' })).toBeNull();
    fireEvent.press(
      screen.getByRole('checkbox', { name: '다른 부위 더 보기' }),
    );
    expect(screen.getByRole('checkbox', { name: '목' })).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('checkbox', { name: '무릎' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '어깨' }));
    fireEvent.press(screen.getByRole('radio', { name: '어깨 심함' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '심한 어지럼' }));
    const submitButton = screen.getByRole('button', {
      name: '보고하고 안전 안내 확인',
    });
    const submitButtonStyle = StyleSheet.flatten(submitButton.props.style);
    const submitLabelStyle = StyleSheet.flatten(
      screen.getByText('보고하고 안전 안내 확인').props.style,
    );
    const submitGradient = screen.getByTestId(
      'workout-api-safety-submit-gradient',
    );

    expect(submitButtonStyle).toMatchObject({
      width: '100%',
      borderColor: 'rgba(142, 50, 38, 0.8)',
      borderWidth: 1,
      borderRadius: 18,
      padding: 17,
      shadowColor: '#8E3226',
      shadowOpacity: 0.11,
      shadowRadius: 6,
      elevation: 3,
    });
    expect(submitButtonStyle.backgroundColor).toBeUndefined();
    expect(submitButtonStyle.borderBottomWidth).toBeUndefined();
    expect(submitLabelStyle).toMatchObject({
      color: '#FFFFFF',
      fontSize: 18,
      fontWeight: '400',
    });
    expect(submitGradient.props.colors).toEqual(
      ['#D97260', '#CC5A47', '#C2503C'].map(processColor),
    );
    expect(submitGradient.props.locations).toEqual([0, 0.55, 1]);

    fireEvent.press(submitButton);

    await waitFor(() => expect(reportSafetyEvent).toHaveBeenCalledTimes(1));
    expect(reportSafetyEvent).toHaveBeenCalledWith(
      'session-api',
      expect.objectContaining({
        discomforts: [
          { body_area_code: 'KNEE', severity_code: 'MILD' },
          { body_area_code: 'SHOULDER', severity_code: 'SEVERE' },
        ],
        adverse_reaction_codes: ['SEVERE_DIZZINESS'],
      }),
    );
    expect(
      await screen.findByText('서버에서 확인한 안전 안내입니다.'),
    ).toBeOnTheScreen();
  });

  it('records a complete additional activity without changing block completion', async () => {
    const recordAdditionalActivity = jest.fn(async () => ({
      activity_id: 'activity-api',
      session_id: 'session-api',
      activity_type_code: 'WALKING',
      duration_seconds: 1200,
      intensity_code: null,
      note: null,
      created_at: '2026-08-19T09:20:00+09:00',
      session_status_code: 'IN_PROGRESS' as const,
    }));
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => sessionDetail('IN_PROGRESS')),
      recordAdditionalActivity,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    for (const testId of [
      'workout-smash-action',
      'workout-rest-action',
      'workout-additional-action',
    ]) {
      expect(
        StyleSheet.flatten(screen.getByTestId(testId).props.style),
      ).toMatchObject({ flex: 1, flexBasis: 0, height: 69.6 });
    }
    fireEvent.press(screen.getByRole('button', { name: '계획 외 활동 기록' }));
    fireEvent.press(screen.getByRole('radio', { name: '자전거' }));
    fireEvent.press(screen.getByRole('radio', { name: '20분' }));
    fireEvent.press(screen.getByRole('radio', { name: '강하게' }));
    fireEvent.changeText(
      screen.getByLabelText('추가 활동 메모'),
      '공원 한 바퀴',
    );
    fireEvent.press(screen.getByRole('button', { name: '추가 활동 저장' }));

    await waitFor(() =>
      expect(recordAdditionalActivity).toHaveBeenCalledWith('session-api', {
        activity_type_code: 'CYCLING',
        duration_seconds: 1200,
        intensity_code: 'VIGOROUS',
        note: '공원 한 바퀴',
      }),
    );
    expect(screen.getByText('완료 0 / 1')).toBeOnTheScreen();
  });

  it('requires and stores a server reason when no block was completed', async () => {
    const markNotCompleted = jest.fn(
      async (_sessionId: string, endedAt: string) => ({
        session_id: 'session-api',
        status_code: 'NOT_COMPLETED' as const,
        reason_code: 'TIME_SHORTAGE' as const,
        ended_at: endedAt,
      }),
    );
    const onOutcome = jest.fn();
    const api = workoutApi({
      getWorkoutSession: jest.fn(async () => sessionDetail('IN_PROGRESS')),
      markNotCompleted,
    });

    render(
      <WorkoutScreen
        api={api}
        sessionId="session-api"
        plan={API_PLAN}
        onOutcome={onOutcome}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    );
    fireEvent.press(screen.getByRole('button', { name: '중단하기' }));
    fireEvent.press(screen.getByRole('button', { name: '시간이 부족했어요' }));

    await waitFor(() =>
      expect(markNotCompleted).toHaveBeenCalledWith(
        'session-api',
        expect.any(String),
        'TIME_SHORTAGE',
      ),
    );
    expect(onOutcome).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'notCompleted' }),
    );
  });
});
