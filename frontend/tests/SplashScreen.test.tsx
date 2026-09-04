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
  SPLASH_COLORS,
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
  it('places the mascot above the centered two-line message at 390 x 844', () => {
    expect(getSplashLayout({ width: 390, height: 844 })).toEqual(
      expect.objectContaining({
        width: 390,
        height: 844,
        contentScale: 1,
        screenMidpoint: 422,
        mascotTop: expect.closeTo(265.6),
        mascotLeft: 121.5,
        mascotWidth: 147,
        mascotHeight: expect.closeTo(148.4),
        textLeft: 19.5,
        textWidth: 351,
        sloganTop: 430,
        sloganFontSize: 18,
        sloganLineHeight: 18,
        sloganStrokeWidth: 4,
        brandTop: 457,
        brandFontSize: 42,
        brandLineHeight: 42,
        brandStrokeWidth: 5,
      }),
    );
  });

  it('keeps the mascot-message gap centered as the viewport changes', () => {
    const compactLayout = getSplashLayout({ width: 195, height: 422 });

    expect(compactLayout).toEqual(
      expect.objectContaining({
        screenMidpoint: 211,
        contentScale: 0.5,
        sloganTop: 215,
        sloganFontSize: 9,
        sloganStrokeWidth: 2,
        brandTop: 228.5,
        brandFontSize: 21,
        brandStrokeWidth: 2.5,
      }),
    );
    expect(compactLayout.mascotWidth).toBe(73.5);
    expect(compactLayout.mascotLeft).toBe(60.75);
    expect(compactLayout.mascotTop).toBeCloseTo(132.8);
    expect(
      (compactLayout.mascotTop +
        compactLayout.mascotHeight +
        compactLayout.sloganTop) /
        2,
    ).toBe(compactLayout.screenMidpoint);

    expect(getSplashLayout({ width: 780, height: 1688 })).toEqual(
      expect.objectContaining({
        mascotLeft: 316.5,
        mascotWidth: 147,
        contentScale: 1,
        screenMidpoint: 844,
        sloganFontSize: 18,
        brandFontSize: 42,
      }),
    );
  });

  it('scales the complete composition to fit short landscape screens', () => {
    const landscapeLayout = getSplashLayout({ width: 844, height: 390 });

    expect(landscapeLayout.contentScale).toBeCloseTo(390 / 844);
    expect(landscapeLayout.mascotTop).toBeGreaterThanOrEqual(0);
    expect(
      landscapeLayout.brandTop + landscapeLayout.brandLineHeight,
    ).toBeLessThanOrEqual(390);
    expect(
      (landscapeLayout.mascotTop +
        landscapeLayout.mascotHeight +
        landscapeLayout.sloganTop) /
        2,
    ).toBeCloseTo(landscapeLayout.screenMidpoint);
  });

  it('renders the requested monkey asset in the upper portion of the screen', async () => {
    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    const screenStyle = StyleSheet.flatten(
      screen.getByTestId('splash-screen').props.style,
    );
    const mascotStyle = StyleSheet.flatten(
      screen.getByTestId('splash-mascot').props.style,
    );
    expect(SPLASH_ASSETS.mascot).toBe(imageAssets.splashMascot);
    expect(screen.getByTestId('splash-mascot').props.source).toBe(
      imageAssets.splashMascot,
    );
    expect(screenStyle).toEqual(
      expect.objectContaining({
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: SPLASH_COLORS.background,
      }),
    );
    expect(mascotStyle).toEqual(
      expect.objectContaining({
        position: 'absolute',
        zIndex: 1,
        top: expect.closeTo(265.6),
        left: 121.5,
        width: 147,
        height: expect.closeTo(148.4),
      }),
    );
    expect(mascotStyle.filter).toBeUndefined();
    expect(mascotStyle.shadowColor).toBeUndefined();
  });

  it('centers the lighter outlined slogan and uppercase brand below the mascot', async () => {
    await render(
      <SplashScreen
        reducedMotionOverride
        viewportOverride={{ width: 390, height: 844 }}
      />,
    );

    expect(screen.getByRole('header', { name: 'HELKKI' })).toBeOnTheScreen();
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
        top: 457,
        shadowColor: 'rgba(128,107,90,0.2)',
        shadowOffset: { width: 0, height: 2 },
        zIndex: 3,
      }),
    );
    const brandText = getTextLayers('splash-brand');
    expectSvgColor(brandText.fill.fill, SPLASH_COLORS.brandFill);
    expectSvgColor(brandText.outline.stroke, SPLASH_COLORS.brandOutline);
    expect(brandText.outline.strokeWidth).toBe(5);
    expect(brandText.fill.font.fontFamily).toBe(fontFamilies.brand);
    expect(brandText.fill.font.fontSize).toBe(42);
    expect(brandText.fill.font.fontWeight).toBe('800');
    expect(brandText.fill.font.letterSpacing).toBe(1.68);
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
        top: 430,
        shadowColor: 'rgba(128,107,90,0.2)',
        zIndex: 3,
      }),
    );
    const sloganText = getTextLayers('splash-slogan');
    expectSvgColor(sloganText.fill.fill, SPLASH_COLORS.sloganFill);
    expectSvgColor(sloganText.outline.stroke, SPLASH_COLORS.sloganOutline);
    expect(sloganText.outline.strokeWidth).toBe(4);
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
    { height: 422, textWidth: 175.5, width: 195 },
    { height: 1688, textWidth: 702, width: 780 },
  ])(
    'keeps both text centers aligned within the viewport at $width x $height',
    async ({ height, textWidth, width }) => {
      await render(
        <SplashScreen
          reducedMotionOverride
          viewportOverride={{ width, height }}
        />,
      );

      const expectedLeft = (width - textWidth) / 2;
      const layout = getSplashLayout({ width, height });

      expect(layout.mascotLeft + layout.mascotWidth / 2).toBe(width / 2);

      for (const testID of ['splash-brand', 'splash-slogan'] as const) {
        const textStyle = StyleSheet.flatten(
          screen.getByTestId(testID).props.style,
        );
        const textLayers = getTextLayers(testID);

        expect(textStyle.left).toBe(expectedLeft);
        expect(Math.abs(textStyle.width - textWidth)).toBeLessThanOrEqual(0.5);
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
          fill: SPLASH_COLORS.brandFill,
          fontFamily: fontFamilies.brand,
          fontSize: 42,
          fontWeight: '800',
          letterSpacing: 1.68,
          lineHeight: 42,
          shadowColor: 'rgba(128,107,90,0.2)',
          shadowOffsetY: 2,
          stroke: SPLASH_COLORS.brandOutline,
          strokeWidth: 5,
        }),
      ).toEqual({
        color: SPLASH_COLORS.brandFill,
        fontFamily: fontFamilies.brand,
        fontSize: '42px',
        fontWeight: '800',
        height: '42px',
        letterSpacing: '1.68px',
        lineHeight: '42px',
        margin: 0,
        overflow: 'visible',
        padding: 0,
        paintOrder: 'stroke fill',
        textShadow: '0 2px 0 rgba(128,107,90,0.2)',
        WebkitTextFillColor: SPLASH_COLORS.brandFill,
        WebkitTextStroke: `5px ${SPLASH_COLORS.brandOutline}`,
        whiteSpace: 'nowrap',
        width: 'max-content',
      });
      expect(brandText.props.children).toBe('HELKKI');
      expect(brandText.props.style.color).toBe(SPLASH_COLORS.brandFill);
      expect(brandText.props.style.WebkitTextFillColor).toBe(
        SPLASH_COLORS.brandFill,
      );
      expect(brandText.props.style.WebkitTextStroke).toBe(
        `5px ${SPLASH_COLORS.brandOutline}`,
      );
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
