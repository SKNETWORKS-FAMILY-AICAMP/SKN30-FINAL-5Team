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
import { useScale } from '../../components/scale';
import { colors } from '../../components/theme';

export const SPLASH_ORIGINAL = {
  width: 390,
  height: 844,
  mascotWidth: 147,
  mascotMaxWidthRatio: 0.54,
  mascotAspectRatio: 210 / 212,
  mascotMessageGap: 16,
  sloganFontSize: 18,
  sloganLineHeight: 18,
  sloganLetterSpacing: 18 * 0.01,
  sloganStrokeWidth: 4,
  sloganShadowOffsetY: 1,
  brandTopOffset: 27,
  brandFontSize: 42,
  brandLineHeight: 42,
  brandLetterSpacing: 42 * 0.04,
  brandStrokeWidth: 5,
  brandShadowOffsetY: 2,
} as const;

export const SPLASH_ASSETS = {
  mascot: imageAssets.splashMascot,
  questionMark: imageAssets.questionMark,
  splashIsland: imageAssets.splashIsland,
} as const;

export const SPLASH_COLORS = {
  background: '#FBE6BD',
  brandFill: '#F2B75B',
  brandOutline: '#806B5A',
  sloganFill: '#FFFDF8',
  sloganOutline: '#806B5A',
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
  containerLeft: number;
  containerWidth: number;
  fill: string;
  fontFamily?: string;
  fontSize: number;
  fontWeight: '400' | '800';
  letterSpacing: number;
  lineHeight: number;
  shadowColor: string;
  shadowOffsetY: number;
  stroke: string;
  strokeWidth: number;
  testID: string;
  text: string;
  top: number;
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
  const contentScale = Math.min(
    1,
    width / SPLASH_ORIGINAL.width,
    height / SPLASH_ORIGINAL.height,
  );
  const mascotWidth = Math.min(
    SPLASH_ORIGINAL.mascotWidth * contentScale,
    width * SPLASH_ORIGINAL.mascotMaxWidthRatio,
  );
  const mascotHeight = mascotWidth / SPLASH_ORIGINAL.mascotAspectRatio;
  const screenMidpoint = height / 2;
  const halfMascotMessageGap =
    (SPLASH_ORIGINAL.mascotMessageGap * contentScale) / 2;
  const sloganTop = screenMidpoint + halfMascotMessageGap;

  return {
    width,
    height,
    contentScale,
    screenMidpoint,
    mascotTop: screenMidpoint - halfMascotMessageGap - mascotHeight,
    mascotLeft: (width - mascotWidth) / 2,
    mascotWidth,
    mascotHeight,
    textLeft: width * 0.05,
    textWidth: width * 0.9,
    sloganTop,
    sloganFontSize: SPLASH_ORIGINAL.sloganFontSize * contentScale,
    sloganLineHeight: SPLASH_ORIGINAL.sloganLineHeight * contentScale,
    sloganLetterSpacing: SPLASH_ORIGINAL.sloganLetterSpacing * contentScale,
    sloganStrokeWidth: SPLASH_ORIGINAL.sloganStrokeWidth * contentScale,
    sloganShadowOffsetY: SPLASH_ORIGINAL.sloganShadowOffsetY * contentScale,
    brandTop: sloganTop + SPLASH_ORIGINAL.brandTopOffset * contentScale,
    brandFontSize: SPLASH_ORIGINAL.brandFontSize * contentScale,
    brandLineHeight: SPLASH_ORIGINAL.brandLineHeight * contentScale,
    brandLetterSpacing: SPLASH_ORIGINAL.brandLetterSpacing * contentScale,
    brandStrokeWidth: SPLASH_ORIGINAL.brandStrokeWidth * contentScale,
    brandShadowOffsetY: SPLASH_ORIGINAL.brandShadowOffsetY * contentScale,
  };
}

function OutlinedText({
  accessibilityLabel,
  accessibilityRole = 'text',
  containerLeft,
  containerWidth,
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
  testID,
  text,
  top,
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
          styles.webOutlinedText,
          {
            top,
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
    textAnchor: 'middle' as const,
    x: '50%' as const,
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
      style={[styles.outlinedText, { left: containerLeft, top }, shadowStyle]}
      testID={testID}
      width={containerWidth}
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
            x="50%"
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
          <TSpan fill={fill} stroke="none" x="50%" y={0}>
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
      <StatusBar style="dark" />
      <Image
        accessible={false}
        importantForAccessibility="no"
        resizeMode="contain"
        source={SPLASH_ASSETS.mascot}
        testID="splash-mascot"
        style={[
          styles.mascot,
          {
            top: layout.mascotTop,
            left: layout.mascotLeft,
            width: layout.mascotWidth,
            height: layout.mascotHeight,
          },
        ]}
      />
      <OutlinedText
        accessibilityLabel="혼자 하는 운동이 어려울 때"
        containerLeft={layout.textLeft}
        containerWidth={layout.textWidth}
        fill={SPLASH_COLORS.sloganFill}
        fontFamily={useLocalFonts ? fontFamilies.slogan : undefined}
        fontSize={layout.sloganFontSize}
        fontWeight="400"
        letterSpacing={layout.sloganLetterSpacing}
        lineHeight={layout.sloganLineHeight}
        shadowColor="rgba(128,107,90,0.2)"
        shadowOffsetY={layout.sloganShadowOffsetY}
        stroke={SPLASH_COLORS.sloganOutline}
        strokeWidth={layout.sloganStrokeWidth}
        testID="splash-slogan"
        text="혼자 하는 운동이 어려울 때"
        top={layout.sloganTop}
      />
      <OutlinedText
        accessibilityLabel="HELKKI"
        accessibilityRole="header"
        containerLeft={layout.textLeft}
        containerWidth={layout.textWidth}
        fill={SPLASH_COLORS.brandFill}
        fontFamily={useLocalFonts ? fontFamilies.brand : undefined}
        fontSize={layout.brandFontSize}
        fontWeight="800"
        letterSpacing={layout.brandLetterSpacing}
        lineHeight={layout.brandLineHeight}
        shadowColor="rgba(128,107,90,0.2)"
        shadowOffsetY={layout.brandShadowOffsetY}
        stroke={SPLASH_COLORS.brandOutline}
        strokeWidth={layout.brandStrokeWidth}
        testID="splash-brand"
        text="HELKKI"
        top={layout.brandTop}
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
    backgroundColor: SPLASH_COLORS.background,
  },
  outlinedText: {
    position: 'absolute',
    alignItems: 'center',
    overflow: 'visible',
    zIndex: 3,
  },
  webOutlinedText: {
    right: 0,
    left: 0,
  },
  mascot: {
    position: 'absolute',
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
