import { describe, expect, it, jest } from '@jest/globals';
import { useFonts } from 'expo-font';
import { Animated, StyleSheet } from 'react-native';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import {
  getSplashLayout,
  SPLASH_ASSETS,
  SplashScreen,
} from '../src/features/splash/SplashScreen';
import { fontFamilies } from '../src/app/fonts';

const useFontsMock = jest.mocked(useFonts);

describe('SplashScreen', () => {
  it('renders the accessible brand hierarchy and bundled local assets', async () => {
    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(screen.getByRole('header', { name: '헬끼' })).toBeOnTheScreen();
    expect(screen.getByText('혼자 하는 운동이 어려울 때')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(
        screen.getByRole('header', { name: '헬끼' }).props.style,
      ).fontFamily,
    ).toBe(fontFamilies.brand);
    expect(
      StyleSheet.flatten(
        screen.getByText('혼자 하는 운동이 어려울 때').props.style,
      ).fontFamily,
    ).toBe(fontFamilies.slogan);
    expect(screen.getByTestId('splash-island').props.source).toBe(
      SPLASH_ASSETS.splashIsland,
    );
    expect(screen.getByTestId('question-mark').props.source).toBe(
      SPLASH_ASSETS.questionMark,
    );
  });

  it('keeps readable system font fallbacks when local font loading fails', async () => {
    useFontsMock.mockReturnValueOnce([false, new Error('font unavailable')]);

    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(
      StyleSheet.flatten(
        screen.getByRole('header', { name: '헬끼' }).props.style,
      ).fontFamily,
    ).toBeUndefined();
    expect(screen.getByText('혼자 하는 운동이 어려울 때')).toBeOnTheScreen();
  });

  it.each([
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ])('keeps art within a $width x $height viewport', async (viewport) => {
    const layout = getSplashLayout(viewport);
    const view = await render(
      <SplashScreen reducedMotionOverride viewportOverride={viewport} />,
    );
    const artStyle = StyleSheet.flatten(
      view.getByTestId('splash-art').props.style,
    );
    const islandStyle = StyleSheet.flatten(
      view.getByTestId('splash-island').props.style,
    );

    expect(artStyle.width).toBeLessThanOrEqual(viewport.width);
    expect(artStyle.height).toBeLessThanOrEqual(viewport.height);
    expect(islandStyle.width).toBeLessThanOrEqual(viewport.width);
    expect(layout.islandTop + layout.islandHeight).toBeLessThan(
      layout.artHeight,
    );
  });

  it('does not start the floating animation when reduced motion is enabled', async () => {
    const loopSpy = jest.spyOn(Animated, 'loop');

    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(loopSpy).not.toHaveBeenCalled();
    loopSpy.mockRestore();
  });

  it('stops the floating animation when the screen unmounts', async () => {
    const stop = jest.fn();
    const start = jest.fn();
    const loopSpy = jest
      .spyOn(Animated, 'loop')
      .mockReturnValue({ start, stop, reset: jest.fn() });

    const view = await render(
      <SplashScreen
        reducedMotionOverride={false}
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(start).toHaveBeenCalledTimes(1);
    await act(() => view.unmount());
    expect(stop).toHaveBeenCalledTimes(1);
    loopSpy.mockRestore();
  });

  it('shows a retry action when boot initialization fails', async () => {
    const onRetry = jest.fn();
    await render(
      <SplashScreen
        bootStatus="error"
        onRetry={onRetry}
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
