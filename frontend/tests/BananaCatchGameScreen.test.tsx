import { describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { imageAssets } from '../src/assets';
import { BananaCatchGameScreen } from '../src/features/bananaCatch/BananaCatchGameScreen';

describe('BananaCatchGameScreen', () => {
  it('starts, moves the catcher and finishes after thirty seconds', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    try {
      render(<BananaCatchGameScreen onBack={() => {}} />);

      expect(screen.getByText('30초 동안 바나나를 받아요!')).toBeTruthy();
      fireEvent.press(screen.getByRole('button', { name: '게임 시작' }));
      expect(screen.getByTestId('falling-banana-1')).toHaveStyle({ zIndex: 5 });
      expect(screen.getByLabelText('점수 0점, 30초 남음')).toBeTruthy();
      expect(
        screen.getByTestId('banana-catcher-mascot-empty').props.source,
      ).toBe(imageAssets.houseMascotCollectingBananasEmpty);
      expect(screen.getByTestId('banana-catcher-mascot-empty')).toHaveStyle({
        opacity: 1,
      });
      expect(screen.getByTestId('banana-catcher-mascot-medium')).toHaveStyle({
        opacity: 0,
      });
      expect(screen.queryByTestId('banana-catch-left')).toBeNull();
      expect(screen.queryByTestId('banana-catch-right')).toBeNull();

      const arena = screen.getByTestId('banana-catch-arena');
      fireEvent(arena, 'layout', {
        nativeEvent: { layout: { height: 500, width: 300 } },
      });
      fireEvent(arena, 'responderGrant', {
        nativeEvent: { locationX: 270 },
      });
      expect(screen.getByTestId('banana-catcher')).toHaveStyle({ left: '89%' });

      act(() => jest.advanceTimersByTime(30_000));
      expect(screen.getByText(/바나나 \d+개를 받았어요!/)).toBeTruthy();
      expect(screen.getByText('한 번 더')).toBeTruthy();
    } finally {
      random.mockRestore();
      jest.useRealTimers();
    }
  });

  it('updates the collecting mascot for each ten caught bananas', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    try {
      render(<BananaCatchGameScreen onBack={() => {}} />);
      fireEvent.press(screen.getByRole('button', { name: '게임 시작' }));

      act(() => jest.advanceTimersByTime(9_700));
      expect(screen.getByTestId('banana-catcher-mascot-empty')).toHaveStyle({
        opacity: 0,
      });
      expect(screen.getByTestId('banana-catcher-mascot-medium')).toHaveStyle({
        opacity: 1,
      });

      act(() => jest.advanceTimersByTime(6_500));
      expect(screen.getByTestId('banana-catcher-mascot-medium')).toHaveStyle({
        opacity: 0,
      });
      expect(screen.getByTestId('banana-catcher-mascot-full')).toHaveStyle({
        opacity: 1,
      });
    } finally {
      random.mockRestore();
      jest.useRealTimers();
    }
  });

  it('returns to the house from the header', () => {
    const onBack = jest.fn();
    render(<BananaCatchGameScreen onBack={onBack} />);

    fireEvent.press(screen.getByLabelText('끼끼의 집으로 돌아가기'));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
