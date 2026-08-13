import { afterEach, describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { ScrollView, StyleSheet } from 'react-native';

import {
  clampWorkoutPageIndex,
  formatWorkoutTime,
  WorkoutScreen,
} from '../src/features/workout/WorkoutScreen';
import {
  SAFETY_GUIDANCE,
  WORKOUT_ARC,
  WORKOUT_BLOCKS,
  WORKOUT_CAROUSEL,
} from '../src/features/workout/workoutModel';

afterEach(() => {
  jest.useRealTimers();
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

describe('WorkoutScreen', () => {
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

  it('configures snap pagination and measures symmetric card padding', async () => {
    await render(<WorkoutScreen />);

    const carousel = screen.getByTestId('workout-carousel');
    expect(carousel.props.snapToInterval).toBe(250);
    expect(carousel.props.snapToAlignment).toBe('start');
    expect(carousel.props.decelerationRate).toBe('fast');
    expect(carousel.props.showsHorizontalScrollIndicator).toBe(false);
    expect(carousel.props.scrollEventThrottle).toBe(16);

    layoutCarousel(390);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-carousel').props.contentContainerStyle,
      ).paddingHorizontal,
    ).toBe(80);
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
      backgroundColor: '#8B8780',
      height: 8,
      width: 22,
    });
    expect(
      StyleSheet.flatten(screen.getByTestId('workout-dot-0').props.style),
    ).toMatchObject({ backgroundColor: '#4E8B3A', height: 8, width: 8 });

    fireEvent.press(screen.getByRole('button', { name: '4번째 블록 보기' }));
    expect(scrollTo).toHaveBeenLastCalledWith({ animated: true, x: 750 });
    expect(
      StyleSheet.flatten(screen.getByTestId('workout-dot-3').props.style),
    ).toMatchObject({ backgroundColor: '#8B8780', height: 8, width: 22 });
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
    expect(screen.getByText('전체 경과 · 기록용')).toBeOnTheScreen();

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
    expect(
      StyleSheet.flatten(
        screen.getByTestId('workout-pause-action').props.style,
      ),
    ).toMatchObject({
      backgroundColor: 'rgba(255,255,255,.18)',
      borderRadius: 18,
      height: 52,
      width: 52,
    });
    expect(
      StyleSheet.flatten(screen.getByTestId('workout-stop-action').props.style),
    ).toMatchObject({
      backgroundColor: 'transparent',
      borderRadius: 18,
      borderWidth: 1.5,
      height: 52,
    });
    expect(
      screen.getByRole('button', {
        name: '안전 중단 및 이상 반응 보고',
      }),
    ).toHaveTextContent('중단');
    expect(screen.queryByText('■')).toBeNull();
    expect(screen.queryByTestId('workout-stop-mark')).toBeNull();
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
    fireEvent.press(
      screen.getByRole('button', { name: '보고만 하고 계속하기' }),
    );
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
