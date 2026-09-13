import { describe, expect, it, jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';
import { Image } from 'react-native';

import { imageAssets } from '../src/assets';
import {
  KikkiRunnerGameScreen,
  wrapRunnerCloudLeft,
} from '../src/features/kikkiRunner/KikkiRunnerGameScreen';

describe('KikkiRunnerGameScreen', () => {
  it('shows the full sunset, starts, double-jumps and finishes after one minute', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.5);
    const onPlayed = jest.fn();
    const onBack = jest.fn();
    try {
      render(<KikkiRunnerGameScreen onBack={onBack} onPlayed={onPlayed} />);

      expect(screen.getByTestId('kikki-runner-city-background')).toHaveProp(
        'resizeMode',
        'stretch',
      );
      expect(screen.getByTestId('kikki-runner-city-background')).toHaveStyle({
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
        width: '100%',
        height: '100%',
      });
      expect(screen.getByTestId('kikki-runner-broken-road-preload')).toHaveProp(
        'fadeDuration',
        0,
      );
      expect(
        within(screen.getByTestId('kikki-runner-score-card')).getByText('60초'),
      ).toBeTruthy();
      expect(screen.getByLabelText(/60초 남음/)).toBeTruthy();
      expect(screen.getByRole('header', { name: '끼끼 달리기' })).toBeTruthy();
      expect(screen.queryByText('바나나 섬 한 바퀴')).toBeNull();
      expect(screen.getByText('끼끼와 바나나 도시를 달려요!')).toBeTruthy();
      expect(
        screen.getByText(
          '바나나 도시의 노을을 따라 달리며 바위와 절벽을 뛰어넘고, 바나나를 모아요. 화면을 두 번 터치하면 2단 점프해요.',
        ),
      ).toBeTruthy();
      expect(screen.getByLabelText('달리는 끼끼').props.source).toBe(
        imageAssets.kikkiRunnerMascot,
      );
      expect(screen.getByLabelText('달리는 끼끼')).toHaveStyle({
        transform: [{ translateY: 22 }, { scaleX: -1 }],
      });

      fireEvent.press(screen.getByText('달리기 시작'));
      expect(screen.getByTestId('kikki-runner-banana-1')).toBeTruthy();
      expect(screen.getByTestId('kikki-runner-banana-1').props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            transform: [{ translateY: 23 }, { rotate: expect.any(String) }],
          }),
        ]),
      );
      expect(screen.getAllByTestId(/kikki-runner-banana-/)).toHaveLength(5);
      expect(screen.getAllByTestId(/kikki-runner-cloud-/)).toHaveLength(3);
      const groundTrack = screen.getByTestId('kikki-runner-ground-track');
      const groundTiles = groundTrack.findAllByType(Image);
      expect(groundTiles[0]?.props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ left: 0, width: 396 }),
        ]),
      );
      expect(groundTiles[1]?.props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            left: 395,
            width: 396,
            transform: [{ scaleX: -1 }],
          }),
        ]),
      );
      expect(screen.getByTestId('kikki-runner-ground-layer')).toHaveStyle({
        bottom: 0,
        height: '22%',
      });

      act(() => jest.advanceTimersByTime(1_000));
      expect(screen.getByText('59초')).toBeTruthy();

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

      act(() => jest.advanceTimersByTime(58_950));
      expect(
        screen.getByText(/600m 달리고 바나나 \d+개를 모았어요!/),
      ).toBeTruthy();
      expect(
        screen.getByText(
          '오늘 처음 완료한 게임에서 바나나 보너스를 받을 수 있어요!',
        ),
      ).toBeTruthy();
      expect(screen.queryByText('한 번 더')).toBeNull();
      expect(onPlayed).toHaveBeenCalledTimes(1);
      expect(onPlayed).toHaveBeenCalledWith(expect.any(Number));
      fireEvent.press(screen.getByRole('button', { name: '확인' }));
      expect(onBack).toHaveBeenCalledTimes(1);
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

  it('renders a three-rock cluster as separate obstacles', () => {
    jest.useFakeTimers();
    const random = jest.spyOn(Math, 'random').mockReturnValue(0.89);
    const view = render(<KikkiRunnerGameScreen onBack={jest.fn()} />);
    try {
      fireEvent.press(screen.getByText('달리기 시작'));
      act(() => jest.advanceTimersByTime(850));

      expect(screen.getAllByTestId(/kikki-runner-rock-/)).toHaveLength(3);
      expect(
        screen.getAllByTestId(/kikki-runner-rock-/)[0]?.props.style,
      ).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            transform: [{ translateY: 11 }, { rotate: '0deg' }],
          }),
        ]),
      );
    } finally {
      view.unmount();
      random.mockRestore();
      jest.useRealTimers();
    }
  });

  it('wraps a cloud only after its full width leaves the screen', () => {
    expect(wrapRunnerCloudLeft(-119, 120, 390)).toBe(-119);
    expect(wrapRunnerCloudLeft(-121, 120, 390)).toBe(469);
  });

  it('renders broken-road caps on both sides of a cliff gap', () => {
    jest.useFakeTimers();
    let randomCalls = 0;
    const random = jest.spyOn(Math, 'random').mockImplementation(() => {
      randomCalls += 1;
      return randomCalls === 29 ? 0.95 : 0.5;
    });
    const view = render(<KikkiRunnerGameScreen onBack={jest.fn()} />);
    try {
      fireEvent.press(screen.getByText('달리기 시작'));
      act(() => jest.advanceTimersByTime(3_400));

      const preloadedCliff = screen.getAllByTestId(
        /^kikki-runner-cliff-\d+$/,
      )[0];
      expect(
        preloadedCliff?.props.style[1].transform[0].translateX,
      ).toBeGreaterThan(390);

      act(() => jest.advanceTimersByTime(1_600));

      const cliff = screen.getAllByTestId(/^kikki-runner-cliff-\d+$/)[0];
      const leftCap = screen.getAllByTestId(/kikki-runner-cliff-left-/)[0];
      expect(cliff).toBeTruthy();
      expect(cliff).toHaveProp('renderToHardwareTextureAndroid', true);
      expect(leftCap).toBeTruthy();
      expect(leftCap?.findByType(Image).props.fadeDuration).toBe(0);
      expect(screen.getAllByTestId(/kikki-runner-cliff-right-/)).toHaveLength(
        1,
      );
      expect(
        screen.getAllByTestId(/kikki-runner-cliff-background-/),
      ).toHaveLength(1);
      expect(screen.getAllByTestId('kikki-runner-ground-track')).toHaveLength(
        1,
      );
    } finally {
      view.unmount();
      random.mockRestore();
      jest.useRealTimers();
    }
  });
});
