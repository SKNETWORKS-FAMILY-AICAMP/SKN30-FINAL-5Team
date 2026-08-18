import { describe, expect, it, jest } from '@jest/globals';
import { useFonts } from 'expo-font';
import { Animated, Platform, processColor, StyleSheet } from 'react-native';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { fontFamilies } from '../src/app/fonts';
import { imageAssets } from '../src/assets';
import {
  getSplashLayout,
  SPLASH_ASSETS,
  SPLASH_ORIGINAL,
  SPLASH_WEB_TEXT_PAINT_ORDER,
  SplashScreen,
} from '../src/features/splash/SplashScreen';

const useFontsMock = jest.mocked(useFonts);

function expectSvgColor(actual: unknown, color: string) {
  expect(actual).toEqual({
    type: 0,
    payload: (processColor(color) as number) >>> 0,
  });
}

function getTextLayers(testID: 'splash-brand' | 'splash-slogan') {
  if (Platform.OS === 'web') {
    const text = screen.getByTestId(`${testID}-text`).props;
    return { fill: text, outline: text };
  }

  return {
    fill: screen.getByTestId(`${testID}-fill`).props,
    outline: screen.getByTestId(`${testID}-outline`).props,
  };
}

describe('SplashScreen', () => {
  it('transcribes the 390 x 844 source coordinates and 90vw island cap', () => {
    expect(getSplashLayout({ width: 390, height: 844 })).toEqual(
      expect.objectContaining({
        width: 390,
        height: 844,
        islandWidth: 351,
        questionSize: 56,
        questionLeft: 129,
        questionTop: 345,
        questionFloatDistance: 10,
        sloganLeft: 111,
        sloganTop: 203,
        sloganFontSize: 18,
        sloganLineHeight: 18,
        sloganStrokeWidth: 6,
        brandLeft: 159,
        brandTop: 227,
        brandFontSize: 26,
        brandLineHeight: 26,
        brandStrokeWidth: 6,
      }),
    );
  });

  it('keeps visual sizes fixed while moving anchors by the reference ratios', () => {
    expect(getSplashLayout({ width: 195, height: 422 })).toEqual(
      expect.objectContaining({
        islandWidth: 175.5,
        questionSize: 56,
        questionLeft: 64.5,
        questionTop: 172.5,
        questionFloatDistance: 10,
        sloganLeft: 55.5,
        sloganTop: 101.5,
        sloganFontSize: 18,
        sloganStrokeWidth: 6,
        brandLeft: 79.5,
        brandTop: 113.5,
        brandFontSize: 26,
        brandStrokeWidth: 6,
      }),
    );

    expect(getSplashLayout({ width: 780, height: 1688 })).toEqual(
      expect.objectContaining({
        islandWidth: 460,
        questionSize: 56,
        questionLeft: 258,
        questionTop: 690,
        sloganFontSize: 18,
        brandFontSize: 26,
      }),
    );
  });

  it('renders the registry assets with an in-flow centered island and root-relative overlays', async () => {
    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    const screenStyle = StyleSheet.flatten(
      screen.getByTestId('splash-screen').props.style,
    );
    const islandStyle = StyleSheet.flatten(
      screen.getByTestId('splash-island').props.style,
    );
    const questionStyle = StyleSheet.flatten(
      screen.getByTestId('question-mark').props.style,
    );

    expect(SPLASH_ASSETS.splashIsland).toBe(imageAssets.splashIsland);
    expect(SPLASH_ASSETS.questionMark).toBe(imageAssets.questionMark);
    expect(screen.getByTestId('splash-island').props.source).toBe(
      imageAssets.splashIsland,
    );
    expect(screen.getByTestId('question-mark').props.source).toBe(
      imageAssets.questionMark,
    );
    expect(screenStyle).toEqual(
      expect.objectContaining({
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#8ECB4E',
      }),
    );
    expect(islandStyle).toEqual(
      expect.objectContaining({
        alignSelf: 'center',
        zIndex: 1,
        width: 351,
        aspectRatio: SPLASH_ORIGINAL.islandAspectRatio,
      }),
    );
    expect(islandStyle.position).toBeUndefined();
    expect(islandStyle.filter).toBeUndefined();
    expect(islandStyle.shadowColor).toBeUndefined();
    expect(islandStyle.shadowOpacity).toBeUndefined();
    expect(islandStyle.shadowRadius).toBeUndefined();
    expect(questionStyle).toEqual(
      expect.objectContaining({
        position: 'absolute',
        zIndex: 2,
        left: 129,
        top: 345,
        width: 56,
        height: 56,
      }),
    );
  });

  it('keeps one accessible label while painting outline behind fill from the exact top edge', async () => {
    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(screen.getByRole('header', { name: '헬끼' })).toBeOnTheScreen();
    expect(
      screen.getByLabelText('혼자 하는 운동이 어려울 때'),
    ).toBeOnTheScreen();

    const brandStyle = StyleSheet.flatten(
      screen.getByTestId('splash-brand').props.style,
    );
    expect(brandStyle).toEqual(
      expect.objectContaining({
        left: 159,
        top: 227,
        shadowColor: 'rgba(107,74,43,0.35)',
        shadowOffset: { width: 0, height: 3 },
        zIndex: 3,
      }),
    );
    const brandText = getTextLayers('splash-brand');
    expectSvgColor(brandText.fill.fill, '#EEDA30');
    expectSvgColor(brandText.outline.stroke, '#6B4A2B');
    expect(brandText.outline.strokeWidth).toBe(6);
    expect(brandText.fill.font.fontFamily).toBe(fontFamilies.brand);
    expect(brandText.fill.font.fontSize).toBe(26);
    expect(brandText.fill.font.fontWeight).toBe('800');
    expect(brandText.fill.font.letterSpacing).toBe(0.52);
    expect(brandText.fill.alignmentBaseline).toBe('text-before-edge');
    expect(screen.queryByTestId('splash-brand-shadow')).toBeNull();
    expect(screen.queryByTestId('splash-brand-stroke')).toBeNull();

    expect(
      StyleSheet.flatten(screen.getByTestId('splash-slogan').props.style),
    ).toEqual(
      expect.objectContaining({
        left: 111,
        top: 203,
        shadowColor: 'rgba(47,82,51,0.35)',
        zIndex: 3,
      }),
    );
    const sloganText = getTextLayers('splash-slogan');
    expectSvgColor(sloganText.fill.fill, '#FFFFFF');
    expectSvgColor(sloganText.outline.stroke, '#2F5233');
    expect(sloganText.outline.strokeWidth).toBe(6);
    expect(sloganText.fill.font.fontFamily).toBe(fontFamilies.slogan);
    expect(sloganText.fill.font.fontSize).toBe(18);
    expect(sloganText.fill.font.fontWeight).toBe('400');
    expect(sloganText.fill.font.letterSpacing).toBeCloseTo(0.18);
    expect(sloganText.fill.alignmentBaseline).toBe('text-before-edge');
    expect(screen.queryByTestId('splash-slogan-shadow')).toBeNull();
    expect(screen.queryByTestId('splash-slogan-stroke')).toBeNull();
  });

  it('keeps readable system font fallbacks when local font loading fails', async () => {
    useFontsMock.mockReturnValueOnce([false, new Error('font unavailable')]);

    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(getTextLayers('splash-brand').fill.font.fontFamily).toBeUndefined();
    expect(getTextLayers('splash-slogan').fill.font.fontFamily).toBeUndefined();
  });

  it('uses native SVG paint-order on web without duplicating the label', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });

    try {
      await render(
        <SplashScreen
          reducedMotionOverride
          viewportOverride={{ width: 390, height: 844 }}
        />,
      );

      const brandText = screen.getByTestId('splash-brand-text').props;
      expect(SPLASH_WEB_TEXT_PAINT_ORDER).toBe('stroke fill');
      expectSvgColor(brandText.fill, '#EEDA30');
      expectSvgColor(brandText.stroke, '#6B4A2B');
      expect(brandText.alignmentBaseline).toBe('text-before-edge');
      expect(screen.queryByTestId('splash-brand-outline')).toBeNull();
      expect(screen.queryByTestId('splash-brand-fill')).toBeNull();
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
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

  it('keeps the original 2.4 second float motion and stops it on unmount', async () => {
    const stop = jest.fn();
    const start = jest.fn();
    const timingSpy = jest.spyOn(Animated, 'timing');
    const loopSpy = jest
      .spyOn(Animated, 'loop')
      .mockReturnValue({ start, stop, reset: jest.fn() });

    const view = await render(
      <SplashScreen
        reducedMotionOverride={false}
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(timingSpy).toHaveBeenNthCalledWith(
      1,
      expect.anything(),
      expect.objectContaining({ toValue: -10, duration: 1200 }),
    );
    expect(timingSpy).toHaveBeenNthCalledWith(
      2,
      expect.anything(),
      expect.objectContaining({ toValue: 0, duration: 1200 }),
    );
    expect(start).toHaveBeenCalledTimes(1);
    await act(() => view.unmount());
    expect(stop).toHaveBeenCalledTimes(1);
    timingSpy.mockRestore();
    loopSpy.mockRestore();
  });

  it('keeps the normal and error prototype boundary with retry isolated to error', async () => {
    const onRetry = jest.fn();
    const view = await render(
      <SplashScreen
        bootStatus="ready"
        onRetry={onRetry}
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(screen.queryByRole('alert')).not.toBeOnTheScreen();

    await act(() => {
      view.rerender(
        <SplashScreen
          bootStatus="error"
          onRetry={onRetry}
          reducedMotionOverride
          viewportOverride={{ width: 390, height: 844 }}
        />,
      );
    });

    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('splash-screen').props.edges).toEqual({
      top: 'additive',
      right: 'additive',
      bottom: 'additive',
      left: 'additive',
    });
  });
});
