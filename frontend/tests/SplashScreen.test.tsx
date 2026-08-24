import { describe, expect, it, jest } from '@jest/globals';
import { useFonts } from 'expo-font';
import { Platform, processColor, StyleSheet } from 'react-native';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { fontFamilies } from '../src/app/fonts';
import { imageAssets } from '../src/assets';
import {
  getSplashWebTextStyle,
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
  return {
    fill: screen.getByTestId(`${testID}-fill`).props,
    outline: screen.getByTestId(`${testID}-outline`).props,
  };
}

describe('SplashScreen', () => {
  it('transcribes the 390 x 844 vertical coordinates and 90vw island cap', () => {
    expect(getSplashLayout({ width: 390, height: 844 })).toEqual(
      expect.objectContaining({
        width: 390,
        height: 844,
        islandLeft: 19.5,
        islandWidth: 351,
        sloganTop: 203,
        sloganFontSize: 18,
        sloganLineHeight: 18,
        sloganStrokeWidth: 6,
        brandTop: 227,
        brandFontSize: 26,
        brandLineHeight: 26,
        brandStrokeWidth: 6,
      }),
    );
  });

  it('keeps visual sizes fixed while moving vertical anchors by the reference ratio', () => {
    expect(getSplashLayout({ width: 195, height: 422 })).toEqual(
      expect.objectContaining({
        islandWidth: 175.5,
        islandLeft: 9.75,
        sloganTop: 101.5,
        sloganFontSize: 18,
        sloganStrokeWidth: 6,
        brandTop: 113.5,
        brandFontSize: 26,
        brandStrokeWidth: 6,
      }),
    );

    expect(getSplashLayout({ width: 780, height: 1688 })).toEqual(
      expect.objectContaining({
        islandLeft: 160,
        islandWidth: 460,
        sloganFontSize: 18,
        brandFontSize: 26,
      }),
    );
  });

  it('renders the centered island without the question-mark overlay', async () => {
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
    expect(SPLASH_ASSETS.splashIsland).toBe(imageAssets.splashIsland);
    expect(screen.getByTestId('splash-island').props.source).toBe(
      imageAssets.splashIsland,
    );
    expect(screen.queryByTestId('question-mark')).toBeNull();
    expect(screenStyle).toEqual(
      expect.objectContaining({
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#F6BA50',
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
  });

  it('centers outlined text on the responsive island width', async () => {
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
        left: 19.5,
        width: 351,
        top: 227,
        shadowColor: 'rgba(107,74,43,0.35)',
        shadowOffset: { width: 0, height: 3 },
        zIndex: 3,
      }),
    );
    const brandText = getTextLayers('splash-brand');
    expectSvgColor(brandText.fill.fill, '#F6BA50');
    expectSvgColor(brandText.outline.stroke, '#5A4636');
    expect(brandText.outline.strokeWidth).toBe(6);
    expect(brandText.fill.font.fontFamily).toBe(fontFamilies.brand);
    expect(brandText.fill.font.fontSize).toBe(26);
    expect(brandText.fill.font.fontWeight).toBe('800');
    expect(brandText.fill.font.letterSpacing).toBe(0.52);
    expect(brandText.fill.font.textAnchor).toBe('middle');
    expect(brandText.fill.x).toEqual(['50%']);
    expect(brandText.fill.alignmentBaseline).toBe('text-before-edge');
    expect(screen.queryByTestId('splash-brand-shadow')).toBeNull();
    expect(screen.queryByTestId('splash-brand-stroke')).toBeNull();

    expect(
      StyleSheet.flatten(screen.getByTestId('splash-slogan').props.style),
    ).toEqual(
      expect.objectContaining({
        left: 19.5,
        width: 351,
        top: 203,
        shadowColor: 'rgba(90,70,54,0.35)',
        zIndex: 3,
      }),
    );
    const sloganText = getTextLayers('splash-slogan');
    expectSvgColor(sloganText.fill.fill, '#FFFFFF');
    expectSvgColor(sloganText.outline.stroke, '#5A4636');
    expect(sloganText.outline.strokeWidth).toBe(6);
    expect(sloganText.fill.font.fontFamily).toBe(fontFamilies.slogan);
    expect(sloganText.fill.font.fontSize).toBe(18);
    expect(sloganText.fill.font.fontWeight).toBe('400');
    expect(sloganText.fill.font.letterSpacing).toBeCloseTo(0.18);
    expect(sloganText.fill.font.textAnchor).toBe('middle');
    expect(sloganText.fill.x).toEqual(['50%']);
    expect(sloganText.fill.alignmentBaseline).toBe('text-before-edge');
    expect(screen.queryByTestId('splash-slogan-shadow')).toBeNull();
    expect(screen.queryByTestId('splash-slogan-stroke')).toBeNull();
  });

  it.each([
    { height: 422, islandWidth: 175.5, width: 195 },
    { height: 1688, islandWidth: 460, width: 780 },
  ])(
    'keeps both text centers aligned with the island at $width x $height',
    async ({ height, islandWidth, width }) => {
      await render(
        <SplashScreen
          reducedMotionOverride
          viewportOverride={{ width, height }}
        />,
      );

      const expectedLeft = (width - islandWidth) / 2;
      const layout = getSplashLayout({ width, height });

      expect(layout.islandLeft + layout.islandWidth / 2).toBe(width / 2);

      for (const testID of ['splash-brand', 'splash-slogan'] as const) {
        const textStyle = StyleSheet.flatten(
          screen.getByTestId(testID).props.style,
        );
        const textLayers = getTextLayers(testID);

        expect(textStyle.left).toBe(expectedLeft);
        expect(Math.abs(textStyle.width - islandWidth)).toBeLessThanOrEqual(
          0.5,
        );
        expect(textLayers.fill.x).toEqual(['50%']);
        expect(textLayers.fill.font.textAnchor).toBe('middle');
      }
    },
  );

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

  it('uses one painted text node on web instead of duplicated outline and fill nodes', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });

    try {
      await render(
        <SplashScreen
          reducedMotionOverride
          viewportOverride={{ width: 390, height: 844 }}
        />,
      );

      const brandText = screen.getByTestId('splash-brand').props.children;
      expect(SPLASH_WEB_TEXT_PAINT_ORDER).toBe('stroke fill');
      expect(
        getSplashWebTextStyle({
          fill: '#F6BA50',
          fontFamily: fontFamilies.brand,
          fontSize: 26,
          fontWeight: '800',
          letterSpacing: 0.52,
          lineHeight: 26,
          shadowColor: 'rgba(107,74,43,0.35)',
          shadowOffsetY: 3,
          stroke: '#5A4636',
          strokeWidth: 6,
        }),
      ).toEqual({
        color: '#F6BA50',
        fontFamily: fontFamilies.brand,
        fontSize: '26px',
        fontWeight: '800',
        height: '26px',
        letterSpacing: '0.52px',
        lineHeight: '26px',
        margin: 0,
        overflow: 'visible',
        padding: 0,
        paintOrder: 'stroke fill',
        textShadow: '0 3px 0 rgba(107,74,43,0.35)',
        WebkitTextFillColor: '#F6BA50',
        WebkitTextStroke: '6px #5A4636',
        whiteSpace: 'nowrap',
        width: 'max-content',
      });
      expect(brandText.props.children).toBe('Helkki');
      expect(brandText.props.style.color).toBe('#F6BA50');
      expect(brandText.props.style.WebkitTextFillColor).toBe('#F6BA50');
      expect(brandText.props.style.WebkitTextStroke).toBe('6px #5A4636');
      expect(screen.queryByTestId('splash-brand-outline')).toBeNull();
      expect(screen.queryByTestId('splash-brand-fill')).toBeNull();
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  });

  it('centers web text within the rendered splash container on wide viewports', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });

    try {
      await render(
        <SplashScreen
          reducedMotionOverride
          viewportOverride={{ width: 1440, height: 900 }}
        />,
      );

      for (const testID of ['splash-brand', 'splash-slogan'] as const) {
        const textStyle = StyleSheet.flatten(
          screen.getByTestId(testID).props.style,
        );

        expect(textStyle).toEqual(
          expect.objectContaining({
            left: 0,
            right: 0,
            alignItems: 'center',
          }),
        );
        expect(textStyle.width).toBeUndefined();
      }
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
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
