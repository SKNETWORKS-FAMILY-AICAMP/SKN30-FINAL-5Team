import { describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { imageAssets } from '../src/assets';
import { KikkiRunnerGameScreen } from '../src/features/kikkiRunner/KikkiRunnerGameScreen';

describe('KikkiRunnerGameScreen', () => {
  it('starts, double-jumps and finishes the thirty-second prototype', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    try {
      render(<KikkiRunnerGameScreen onBack={() => {}} />);

      expect(screen.getByRole('header', { name: '끼끼 달리기' })).toBeTruthy();
      expect(screen.getByText('끼끼와 바나나 섬을 달려요!')).toBeTruthy();
      expect(screen.getByLabelText('달리는 끼끼').props.source).toBe(
        imageAssets.mascotWarmupWalk,
      );

      fireEvent.press(screen.getByText('달리기 시작'));
      expect(screen.getByTestId('kikki-runner-banana-1')).toBeTruthy();

      const arena = screen.getByTestId('kikki-runner-arena');
      fireEvent(arena, 'responderGrant');
      act(() => jest.advanceTimersByTime(50));
      expect(screen.getByTestId('kikki-runner-player').props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            bottom: expect.not.stringMatching(/^22%$/),
          }),
        ]),
      );
      fireEvent(arena, 'responderGrant');

      act(() => jest.advanceTimersByTime(29_950));
      expect(
        screen.getByText(/300m를 달리고 바나나 \d+개를 만났어요!/),
      ).toBeTruthy();
      expect(screen.getByText('한 번 더')).toBeTruthy();
    } finally {
      random.mockRestore();
      jest.useRealTimers();
    }
  });

  it('returns to Kkikki house from the header', () => {
    const onBack = jest.fn();
    render(<KikkiRunnerGameScreen onBack={onBack} />);

    const back = screen.getByRole('button', {
      name: '끼끼의 집으로 돌아가기',
    });
    expect(back).toHaveStyle({ width: 44, height: 44 });
    fireEvent.press(back);

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
