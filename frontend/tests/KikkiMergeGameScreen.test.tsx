import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { describe, expect, it, jest } from '@jest/globals';
import { StyleSheet } from 'react-native';

import { kikkiMergeStageSources } from '../src/assets';
import { KikkiMergeGameScreen } from '../src/features/kikkiMerge/KikkiMergeGameScreen';

describe('Kkikki merge screen', () => {
  it('starts, accepts a drop and stays open without a timer', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    const onBack = jest.fn();
    const onPlayed = jest.fn();
    try {
      render(<KikkiMergeGameScreen onBack={onBack} onPlayed={onPlayed} />);

      expect(
        screen.getByLabelText('9단계 0개, 10단계 0개, 11단계 0개'),
      ).toBeTruthy();
      expect(
        screen.getByTestId('kikki-merge-stage-9-stat-icon').props.source,
      ).toBe(kikkiMergeStageSources[8]);
      expect(
        screen.getByTestId('kikki-merge-stage-10-stat-icon').props.source,
      ).toBe(kikkiMergeStageSources[9]);
      expect(
        screen.getByTestId('kikki-merge-stage-11-stat-icon').props.source,
      ).toBe(kikkiMergeStageSources[10]);

      expect(screen.getByText('아기 끼끼를 챔피언 끼끼로!')).toBeTruthy();
      expect(screen.queryByText('시간 제한 없음')).toBeNull();
      expect(
        screen.getByText(
          '같은 끼끼가 만나면 성장해요! 잘 조준해서 떨어뜨려 보세요',
        ),
      ).toBeTruthy();
      expect(
        screen.getByLabelText('아기 끼끼에서 챔피언 끼끼로 성장'),
      ).toBeTruthy();
      const baby = screen.getByTestId('kikki-merge-intro-baby');
      const champion = screen.getByTestId('kikki-merge-intro-champion');
      expect(baby.props.source).toBe(kikkiMergeStageSources[0]);
      expect(champion.props.source).toBe(
        kikkiMergeStageSources[kikkiMergeStageSources.length - 1],
      );
      expect(Number(StyleSheet.flatten(baby.props.style).width)).toBeLessThan(
        Number(StyleSheet.flatten(champion.props.style).width),
      );
      fireEvent.press(screen.getByRole('button', { name: '합치기 시작' }));
      expect(screen.getByTestId('kikki-merge-preview')).toBeTruthy();

      fireEvent.press(screen.getByRole('button', { name: '떨어뜨리기' }));
      expect(screen.getByText('합치는 중')).toBeTruthy();

      act(() => jest.advanceTimersByTime(60_000));
      expect(screen.queryByText('시간 제한 없음')).toBeNull();
      expect(screen.queryByRole('button', { name: '확인' })).toBeNull();
      expect(onPlayed).not.toHaveBeenCalled();
      expect(onBack).not.toHaveBeenCalled();
    } finally {
      random.mockRestore();
      jest.useRealTimers();
    }
  });

  it('returns without spending a play before a round starts', () => {
    const onBack = jest.fn();
    const onPlayed = jest.fn();
    render(<KikkiMergeGameScreen onBack={onBack} onPlayed={onPlayed} />);

    fireEvent.press(screen.getByLabelText('끼끼의 집으로 돌아가기'));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onPlayed).not.toHaveBeenCalled();
  });
});
