import { describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { BananaCatchGameScreen } from '../src/features/bananaCatch/BananaCatchGameScreen';

describe('BananaCatchGameScreen', () => {
  it('starts, moves the catcher and finishes after thirty seconds', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    try {
      render(<BananaCatchGameScreen onBack={() => {}} />);

      expect(screen.getByText('30초 동안 바나나를 받아요!')).toBeTruthy();
      fireEvent.press(screen.getByRole('button', { name: '게임 시작' }));
      expect(screen.getByTestId('falling-banana-1')).toBeTruthy();

      fireEvent.press(screen.getByTestId('banana-catch-right'));
      expect(screen.getByTestId('banana-catcher')).toHaveStyle({ left: '59%' });

      act(() => jest.advanceTimersByTime(30_000));
      expect(screen.getByText(/바나나 \d+개를 받았어요!/)).toBeTruthy();
      expect(screen.getByText('한 번 더')).toBeTruthy();
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
