import { useEffect, useMemo, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  type ImageSourcePropType,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  type TextStyle,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import { fontFamilies, useBrandFonts } from '../../app/fonts';
import { colors } from '../../components/theme';

const webSloganShadow = {
  textShadow: `0 2px 2px ${colors.sloganOutline}`,
} as unknown as TextStyle;
const webBrandShadow = {
  textShadow: `0 3px 3px ${colors.brandOutline}`,
} as unknown as TextStyle;

const questionMarkSource =
  require('../../assets/splash/question-mark.png') as ImageSourcePropType;
const splashIslandSource =
  require('../../assets/splash/splash-island.png') as ImageSourcePropType;

export const SPLASH_ASSETS = {
  questionMark: questionMarkSource,
  splashIsland: splashIslandSource,
} as const;

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

export function getSplashLayout({ width, height }: SplashViewport) {
  const artWidth = Math.min(width, 460);
  const artHeight = Math.min(height * 0.58, 490);
  const islandWidth = Math.min(width * 0.92, 460);
  const questionSize = Math.min(Math.max(width * 0.145, 44), 56);

  return {
    artWidth,
    artHeight,
    islandWidth,
    islandHeight: islandWidth * (2 / 3),
    questionSize,
    questionLeft: artWidth * 0.33,
    questionTop: artHeight * 0.34,
    sloganTop: artHeight * 0.05,
    brandTop: artHeight * 0.11,
    islandTop: artHeight * 0.13,
  };
}

function useReducedMotion(override?: boolean) {
  const [isReducedMotionEnabled, setReducedMotionEnabled] = useState(true);

  useEffect(() => {
    if (override !== undefined) {
      return;
    }

    let isMounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (isMounted) {
        setReducedMotionEnabled(enabled);
      }
    });

    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReducedMotionEnabled,
    );

    return () => {
      isMounted = false;
      subscription.remove();
    };
  }, [override]);

  return override ?? isReducedMotionEnabled;
}

export function SplashScreen({
  bootStatus = 'pending',
  onRetry,
  reducedMotionOverride,
  viewportOverride,
}: SplashScreenProps) {
  const window = useWindowDimensions();
  const viewport = viewportOverride ?? window;
  const layout = useMemo(() => getSplashLayout(viewport), [viewport]);
  const reduceMotion = useReducedMotion(reducedMotionOverride);
  const [questionOffset] = useState(() => new Animated.Value(0));
  const brandFonts = useBrandFonts();
  const useLocalFonts = brandFonts.loaded && !brandFonts.failed;

  useEffect(() => {
    if (reduceMotion) {
      questionOffset.stopAnimation();
      questionOffset.setValue(0);
      return;
    }

    const floatingAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(questionOffset, {
          toValue: -10,
          duration: 1200,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: Platform.OS !== 'web',
        }),
        Animated.timing(questionOffset, {
          toValue: 0,
          duration: 1200,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: Platform.OS !== 'web',
        }),
      ]),
    );

    floatingAnimation.start();
    return () => floatingAnimation.stop();
  }, [questionOffset, reduceMotion]);

  return (
    <SafeAreaView
      style={styles.screen}
      edges={['top', 'right', 'bottom', 'left']}
    >
      <StatusBar style="light" />
      <View
        testID="splash-art"
        style={[
          styles.art,
          { width: layout.artWidth, height: layout.artHeight },
        ]}
      >
        <Text
          accessibilityRole="text"
          style={[
            styles.slogan,
            useLocalFonts && styles.sloganFont,
            { top: layout.sloganTop },
          ]}
        >
          혼자 하는 운동이 어려울 때
        </Text>
        <Text
          accessibilityRole="header"
          accessibilityLabel="헬끼"
          style={[
            styles.brand,
            useLocalFonts && styles.brandFont,
            { top: layout.brandTop },
          ]}
        >
          Helkki
        </Text>
        <Image
          accessible={false}
          importantForAccessibility="no"
          resizeMode="contain"
          source={SPLASH_ASSETS.splashIsland}
          testID="splash-island"
          style={[
            styles.island,
            {
              top: layout.islandTop,
              width: layout.islandWidth,
              height: layout.islandHeight,
            },
          ]}
        />
        <Animated.Image
          accessible={false}
          importantForAccessibility="no"
          resizeMode="contain"
          source={SPLASH_ASSETS.questionMark}
          testID="question-mark"
          style={[
            styles.questionMark,
            {
              left: layout.questionLeft,
              top: layout.questionTop,
              width: layout.questionSize,
              height: layout.questionSize,
              transform: [{ translateY: questionOffset }],
            },
          ]}
        />
      </View>

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
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.splashBackground,
  },
  art: {
    position: 'relative',
    alignItems: 'center',
  },
  slogan: {
    position: 'absolute',
    zIndex: 3,
    color: colors.slogan,
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0.2,
    lineHeight: 22,
    textAlign: 'center',
    width: '100%',
    ...Platform.select({
      web: webSloganShadow,
      default: {
        textShadowColor: colors.sloganOutline,
        textShadowOffset: { width: 0, height: 2 },
        textShadowRadius: 2,
      },
    }),
  },
  sloganFont: {
    fontFamily: fontFamilies.slogan,
    fontWeight: '400',
  },
  brand: {
    position: 'absolute',
    zIndex: 3,
    color: colors.brandFill,
    fontSize: 30,
    fontWeight: '900',
    letterSpacing: 0.6,
    lineHeight: 34,
    textAlign: 'center',
    width: '100%',
    ...Platform.select({
      web: webBrandShadow,
      default: {
        textShadowColor: colors.brandOutline,
        textShadowOffset: { width: 0, height: 3 },
        textShadowRadius: 3,
      },
    }),
  },
  brandFont: {
    fontFamily: fontFamilies.brand,
    fontWeight: '800',
  },
  island: {
    position: 'absolute',
    alignSelf: 'center',
    ...Platform.select({
      web: { boxShadow: '0 18px 28px rgba(0, 0, 0, 0.18)' },
      default: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 18 },
        shadowOpacity: 0.18,
        shadowRadius: 14,
      },
    }),
  },
  questionMark: {
    position: 'absolute',
    zIndex: 2,
  },
  errorCard: {
    position: 'absolute',
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
