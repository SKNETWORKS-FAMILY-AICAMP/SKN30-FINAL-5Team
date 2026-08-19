import { type ComponentType } from 'react';
import {
  Image,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import Svg, { TSpan, Text as SvgText } from 'react-native-svg';

import { fontFamilies, useBrandFonts } from '../../app/fonts';
import { imageAssets } from '../../assets';
import { BASE_H, BASE_W, useScale } from '../../components/scale';
import { colors } from '../../components/theme';

export const SPLASH_ORIGINAL = {
  width: 390,
  height: 844,
  islandWidth: 460,
  islandMaxWidthRatio: 0.9,
  islandAspectRatio: 460 / 307,
  sloganLeft: 111,
  sloganTop: 203,
  sloganFontSize: 18,
  sloganLineHeight: 18,
  sloganLetterSpacing: 18 * 0.01,
  sloganStrokeWidth: 6,
  sloganShadowOffsetY: 2,
  brandLeft: 159,
  brandTop: 227,
  brandFontSize: 26,
  brandLineHeight: 26,
  brandLetterSpacing: 26 * 0.02,
  brandStrokeWidth: 6,
  brandShadowOffsetY: 3,
} as const;

export const SPLASH_ASSETS = {
  questionMark: imageAssets.questionMark,
  splashIsland: imageAssets.splashIsland,
} as const;

export const SPLASH_WEB_TEXT_PAINT_ORDER = 'stroke fill' as const;

export type SplashViewport = {
  width: number;
  height: number;
};

type SplashScreenProps = {
  bootStatus?: 'pending' | 'ready' | 'error';
  onRetry?: () => void;
  reducedMotionOverride?: boolean;
  viewportOverride?: SplashViewport;
};

type OutlinedTextProps = {
  accessibilityLabel: string;
  accessibilityRole?: 'header' | 'text';
  fill: string;
  fontFamily?: string;
  fontSize: number;
  fontWeight: '400' | '800';
  left: number;
  letterSpacing: number;
  lineHeight: number;
  shadowColor: string;
  shadowOffsetY: number;
  stroke: string;
  strokeWidth: number;
  testID: string;
  text: string;
  top: number;
  viewportWidth: number;
};

type SplashWebTextStyle = {
  color: string;
  fontFamily?: string;
  fontSize: string;
  fontWeight: '400' | '800';
  height: string;
  letterSpacing: string;
  lineHeight: string;
  margin: number;
  overflow: 'visible';
  padding: number;
  paintOrder: typeof SPLASH_WEB_TEXT_PAINT_ORDER;
  textShadow: string;
  WebkitTextFillColor: string;
  WebkitTextStroke: string;
  whiteSpace: 'nowrap';
  width: 'max-content';
};

type SplashWebTextStyleInput = Pick<
  OutlinedTextProps,
  | 'fill'
  | 'fontFamily'
  | 'fontSize'
  | 'fontWeight'
  | 'letterSpacing'
  | 'lineHeight'
  | 'shadowColor'
  | 'shadowOffsetY'
  | 'stroke'
  | 'strokeWidth'
>;

export function getSplashWebTextStyle({
  fill,
  fontFamily,
  fontSize,
  fontWeight,
  letterSpacing,
  lineHeight,
  shadowColor,
  shadowOffsetY,
  stroke,
  strokeWidth,
}: SplashWebTextStyleInput): SplashWebTextStyle {
  return {
    color: fill,
    fontFamily,
    fontSize: `${fontSize}px`,
    fontWeight,
    height: `${lineHeight}px`,
    letterSpacing: `${letterSpacing}px`,
    lineHeight: `${lineHeight}px`,
    margin: 0,
    overflow: 'visible',
    padding: 0,
    paintOrder: SPLASH_WEB_TEXT_PAINT_ORDER,
    textShadow: `0 ${shadowOffsetY}px 0 ${shadowColor}`,
    WebkitTextFillColor: fill,
    WebkitTextStroke: `${strokeWidth}px ${stroke}`,
    whiteSpace: 'nowrap',
    width: 'max-content',
  };
}

type WebTextElementProps = {
  'aria-hidden': true;
  children: string;
  style: SplashWebTextStyle;
};

const WebTextElement = 'div' as unknown as ComponentType<WebTextElementProps>;

export function getSplashLayout(viewport: SplashViewport) {
  const { width, height } = viewport;
  const x = (value: number) => (value * width) / BASE_W;
  const y = (value: number) => (value * height) / BASE_H;

  return {
    width,
    height,
    islandWidth: Math.min(
      SPLASH_ORIGINAL.islandWidth,
      width * SPLASH_ORIGINAL.islandMaxWidthRatio,
    ),
    sloganLeft: x(SPLASH_ORIGINAL.sloganLeft),
    sloganTop: y(SPLASH_ORIGINAL.sloganTop),
    sloganFontSize: SPLASH_ORIGINAL.sloganFontSize,
    sloganLineHeight: SPLASH_ORIGINAL.sloganLineHeight,
    sloganLetterSpacing: SPLASH_ORIGINAL.sloganLetterSpacing,
    sloganStrokeWidth: SPLASH_ORIGINAL.sloganStrokeWidth,
    sloganShadowOffsetY: SPLASH_ORIGINAL.sloganShadowOffsetY,
    brandLeft: x(SPLASH_ORIGINAL.brandLeft),
    brandTop: y(SPLASH_ORIGINAL.brandTop),
    brandFontSize: SPLASH_ORIGINAL.brandFontSize,
    brandLineHeight: SPLASH_ORIGINAL.brandLineHeight,
    brandLetterSpacing: SPLASH_ORIGINAL.brandLetterSpacing,
    brandStrokeWidth: SPLASH_ORIGINAL.brandStrokeWidth,
    brandShadowOffsetY: SPLASH_ORIGINAL.brandShadowOffsetY,
  };
}

function OutlinedText({
  accessibilityLabel,
  accessibilityRole = 'text',
  fill,
  fontFamily,
  fontSize,
  fontWeight,
  left,
  letterSpacing,
  lineHeight,
  shadowColor,
  shadowOffsetY,
  stroke,
  strokeWidth,
  testID,
  text,
  top,
  viewportWidth,
}: OutlinedTextProps) {
  if (Platform.OS === 'web') {
    const webTextStyle = getSplashWebTextStyle({
      fill,
      fontFamily,
      fontSize,
      fontWeight,
      letterSpacing,
      lineHeight,
      shadowColor,
      shadowOffsetY,
      stroke,
      strokeWidth,
    });

    return (
      <View
        accessible
        accessibilityLabel={accessibilityLabel}
        accessibilityRole={accessibilityRole}
        pointerEvents="none"
        style={[
          styles.outlinedText,
          {
            left,
            top,
            width: Math.max(0, viewportWidth - left),
            height: lineHeight,
          },
        ]}
        testID={testID}
      >
        <WebTextElement aria-hidden style={webTextStyle}>
          {text}
        </WebTextElement>
      </View>
    );
  }

  const sharedTextProps = {
    accessible: false,
    alignmentBaseline: 'text-before-edge' as const,
    fontFamily,
    fontSize,
    fontWeight,
    letterSpacing,
    x: 0,
    y: 0,
  };
  const shadowStyle = {
    shadowColor,
    shadowOffset: { width: 0, height: shadowOffsetY },
    shadowOpacity: 1,
    shadowRadius: 0,
  };

  return (
    <Svg
      accessible
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={accessibilityRole}
      height={lineHeight}
      pointerEvents="none"
      style={[styles.outlinedText, { left, top }, shadowStyle]}
      testID={testID}
      width={Math.max(0, viewportWidth - left)}
    >
      <>
        <SvgText
          {...sharedTextProps}
          fill="none"
          stroke={stroke}
          strokeLinejoin="round"
          strokeWidth={strokeWidth}
          testID={`${testID}-outline`}
        >
          <TSpan
            fill="none"
            stroke={stroke}
            strokeLinejoin="round"
            strokeWidth={strokeWidth}
            x={0}
            y={0}
          >
            {text}
          </TSpan>
        </SvgText>
        <SvgText
          {...sharedTextProps}
          fill={fill}
          stroke="none"
          testID={`${testID}-fill`}
        >
          <TSpan fill={fill} stroke="none" x={0} y={0}>
            {text}
          </TSpan>
        </SvgText>
      </>
    </Svg>
  );
}

export function SplashScreen({
  bootStatus = 'pending',
  onRetry,
  viewportOverride,
}: SplashScreenProps) {
  const scale = useScale();
  const layout = getSplashLayout(viewportOverride ?? scale);
  const brandFonts = useBrandFonts();
  const useLocalFonts = brandFonts.loaded && !brandFonts.failed;

  return (
    <SafeAreaView
      style={styles.screen}
      edges={['top', 'right', 'bottom', 'left']}
      testID="splash-screen"
    >
      <StatusBar style="light" />
      <Image
        accessible={false}
        importantForAccessibility="no"
        resizeMode="contain"
        source={SPLASH_ASSETS.splashIsland}
        testID="splash-island"
        style={[
          styles.island,
          {
            width: layout.islandWidth,
            aspectRatio: SPLASH_ORIGINAL.islandAspectRatio,
          },
        ]}
      />
      <OutlinedText
        accessibilityLabel="헬끼"
        accessibilityRole="header"
        fill={colors.brandFill}
        fontFamily={useLocalFonts ? fontFamilies.brand : undefined}
        fontSize={layout.brandFontSize}
        fontWeight="800"
        left={layout.brandLeft}
        letterSpacing={layout.brandLetterSpacing}
        lineHeight={layout.brandLineHeight}
        shadowColor="rgba(107,74,43,0.35)"
        shadowOffsetY={layout.brandShadowOffsetY}
        stroke={colors.brandOutline}
        strokeWidth={layout.brandStrokeWidth}
        testID="splash-brand"
        text="Helkki"
        top={layout.brandTop}
        viewportWidth={layout.width}
      />
      <OutlinedText
        accessibilityLabel="혼자 하는 운동이 어려울 때"
        fill={colors.slogan}
        fontFamily={useLocalFonts ? fontFamilies.slogan : undefined}
        fontSize={layout.sloganFontSize}
        fontWeight="400"
        left={layout.sloganLeft}
        letterSpacing={layout.sloganLetterSpacing}
        lineHeight={layout.sloganLineHeight}
        shadowColor="rgba(47,82,51,0.35)"
        shadowOffsetY={layout.sloganShadowOffsetY}
        stroke={colors.sloganOutline}
        strokeWidth={layout.sloganStrokeWidth}
        testID="splash-slogan"
        text="혼자 하는 운동이 어려울 때"
        top={layout.sloganTop}
        viewportWidth={layout.width}
      />

      {bootStatus === 'error' ? (
        <View accessibilityRole="alert" style={styles.errorCard}>
          <Text style={styles.errorTitle}>앱을 시작하지 못했어요</Text>
          <Text style={styles.errorMessage}>
            연결 상태를 확인한 뒤 다시 시도해 주세요.
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={onRetry}
            style={styles.retryButton}
          >
            <Text style={styles.retryLabel}>다시 시도</Text>
          </Pressable>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    backgroundColor: colors.splashBackground,
  },
  outlinedText: {
    position: 'absolute',
    overflow: 'visible',
    zIndex: 3,
  },
  island: {
    alignSelf: 'center',
    zIndex: 1,
  },
  errorCard: {
    position: 'absolute',
    zIndex: 4,
    right: 24,
    bottom: 32,
    left: 24,
    alignItems: 'center',
    borderRadius: 16,
    backgroundColor: colors.errorSurface,
    padding: 16,
  },
  errorTitle: {
    color: colors.errorText,
    fontSize: 16,
    fontWeight: '800',
  },
  errorMessage: {
    marginTop: 4,
    color: colors.errorText,
    fontSize: 14,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: 12,
    borderRadius: 999,
    backgroundColor: colors.sloganOutline,
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  retryLabel: {
    color: colors.slogan,
    fontSize: 15,
    fontWeight: '800',
  },
});
