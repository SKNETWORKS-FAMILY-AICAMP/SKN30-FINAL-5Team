import { act, render, screen } from '@testing-library/react-native';
import { StyleSheet, Text } from 'react-native';

import {
  ROUTINE_GENERATION_ASSETS,
  RoutineGenerationLoading,
} from '../src/features/home/RoutineGenerationLoading';

function imageOpacity(testID: string): number {
  return StyleSheet.flatten(
    screen.getByTestId(testID, { includeHiddenElements: true }).props.style,
  ).opacity;
}

describe('RoutineGenerationLoading', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('cycles one to three periods every second and resets them for a new phase', () => {
    const clearIntervalSpy = jest.spyOn(globalThis, 'clearInterval');
    const view = render(<RoutineGenerationLoading />);

    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼가 오늘의 운동 재료를 하나씩 모으는 중');
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '.',
    );
    expect(
      screen.getByTestId('routine-generation-bubble-1', {
        includeHiddenElements: true,
      }).props.source,
    ).toBe(ROUTINE_GENERATION_ASSETS.bubbles[0]);
    expect(imageOpacity('routine-generation-bubble-1')).toBe(1);
    expect(imageOpacity('routine-generation-bubble-2')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-3')).toBe(0);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('routine-generation-bubble-1', {
          includeHiddenElements: true,
        }).props.style,
      ),
    ).toMatchObject({ right: expect.any(Number) });

    act(() => jest.advanceTimersByTime(1_000));
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '..',
    );
    expect(imageOpacity('routine-generation-bubble-1')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-2')).toBe(1);
    expect(imageOpacity('routine-generation-bubble-3')).toBe(0);

    act(() => jest.advanceTimersByTime(1_000));
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '...',
    );
    expect(imageOpacity('routine-generation-bubble-1')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-2')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-3')).toBe(1);

    act(() => jest.advanceTimersByTime(2_000));
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼의 바나나가 안전 수칙을 꼼꼼히 확인하는 중');
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '.',
    );

    view.unmount();
    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
  });

  it('accepts a future server-owned phase code and resets its period cycle', () => {
    const view = render(<RoutineGenerationLoading phaseCode="SAFETY_CHECK" />);

    act(() => jest.advanceTimersByTime(2_000));
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '...',
    );

    view.rerender(<RoutineGenerationLoading phaseCode="FINAL_VALIDATION" />);
    act(() => jest.advanceTimersByTime(0));
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('조금만 기다려 주세요. 안전한 루틴인지 마지막으로 확인하는 중');
    expect(screen.getByTestId('routine-generation-dots').props.children).toBe(
      '.',
    );
    expect(
      screen.getByTestId('routine-generation-progress').props
        .accessibilityValue,
    ).toEqual({ min: 0, max: 100, now: 95 });
    expect(imageOpacity('routine-generation-bubble-1')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-2')).toBe(0);
    expect(imageOpacity('routine-generation-bubble-3')).toBe(0);
    expect(imageOpacity('routine-generation-mascot-1')).toBe(0);
    expect(imageOpacity('routine-generation-mascot-2')).toBe(0);
    expect(imageOpacity('routine-generation-mascot-3')).toBe(0);
    expect(imageOpacity('routine-generation-mascot-6')).toBe(1);

    view.unmount();
  });

  it('changes the loading mascot independently about every five seconds', () => {
    const randomSpy = jest.spyOn(Math, 'random').mockReturnValue(0);
    const view = render(<RoutineGenerationLoading />);
    expect(imageOpacity('routine-generation-mascot-1')).toBe(1);
    expect(imageOpacity('routine-generation-mascot-2')).toBe(0);

    act(() => jest.advanceTimersByTime(4_999));
    expect(imageOpacity('routine-generation-mascot-1')).toBe(1);
    expect(imageOpacity('routine-generation-mascot-2')).toBe(0);

    act(() => jest.advanceTimersByTime(1));
    expect(imageOpacity('routine-generation-mascot-1')).toBe(0);
    expect(imageOpacity('routine-generation-mascot-2')).toBe(1);

    view.unmount();
    randomSpy.mockRestore();
  });

  it('waits for an API-owned phase before showing final validation', () => {
    const view = render(<RoutineGenerationLoading />);

    act(() => jest.advanceTimersByTime(60_000));

    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼가 운동 순서와 쉬는 시간을 정리하는 중');
    expect(
      screen.getByTestId('routine-generation-progress').props
        .accessibilityValue,
    ).toEqual({ min: 0, max: 100, now: 88 });

    view.unmount();
  });

  it('renders supplied artwork instead of the bundled loading scene', () => {
    const view = render(
      <RoutineGenerationLoading
        asset={<Text testID="provided-loading-asset">움직이는 끼끼</Text>}
      />,
    );

    expect(
      screen.getByTestId('provided-loading-asset', {
        includeHiddenElements: true,
      }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByTestId('routine-generation-mascot-1', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
    expect(
      screen.queryByTestId('routine-generation-bubble-1', {
        includeHiddenElements: true,
      }),
    ).toBeNull();

    view.unmount();
  });
});
