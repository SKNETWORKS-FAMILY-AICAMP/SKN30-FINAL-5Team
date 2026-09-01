import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  type ImageSourcePropType,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { useScale } from '../../components/scale';

export type RoutineGenerationPhaseCode =
  | 'PREPARING_INPUTS'
  | 'SAFETY_CHECK'
  | 'CONDITION_CHECK'
  | 'CONSTRAINT_CHECK'
  | 'EQUIPMENT_CHECK'
  | 'INTENSITY_MATCHING'
  | 'EXERCISE_SELECTION'
  | 'ROUTINE_DRAFTING'
  | 'ROUTINE_COMPILING'
  | 'FINAL_VALIDATION';

type RoutineGenerationPhase = {
  code: RoutineGenerationPhaseCode;
  progress: number;
  text: string;
};

/**
 * Stable presentation codes that a future progress API can drive directly.
 * Until that contract exists, the component walks through the same codes on a
 * timer. Korean copy remains presentation-only and never becomes an API key.
 */
export const ROUTINE_GENERATION_PHASES: readonly RoutineGenerationPhase[] = [
  {
    code: 'PREPARING_INPUTS',
    progress: 10,
    text: '끼끼가 오늘의 운동 재료를 하나씩 모으는 중',
  },
  {
    code: 'SAFETY_CHECK',
    progress: 20,
    text: '끼끼의 바나나가 안전 수칙을 꼼꼼히 확인하는 중',
  },
  {
    code: 'CONDITION_CHECK',
    progress: 30,
    text: '끼끼가 오늘의 피로도와 컨디션을 살펴보는 중',
  },
  {
    code: 'CONSTRAINT_CHECK',
    progress: 40,
    text: '끼끼가 운동할 수 있는 시간과 장소를 확인하는 중',
  },
  {
    code: 'EQUIPMENT_CHECK',
    progress: 50,
    text: '끼끼가 사용할 수 있는 운동 기구를 살펴보는 중',
  },
  {
    code: 'INTENSITY_MATCHING',
    progress: 60,
    text: '끼끼가 오늘 알맞은 운동 강도를 맞추는 중',
  },
  {
    code: 'EXERCISE_SELECTION',
    progress: 70,
    text: '끼끼가 오늘 잘 맞는 운동 후보를 고르는 중',
  },
  {
    code: 'ROUTINE_DRAFTING',
    progress: 80,
    text: '끼끼가 바나나를 먹으며 운동 조합을 고민하는 중',
  },
  {
    code: 'ROUTINE_COMPILING',
    progress: 88,
    text: '끼끼가 운동 순서와 쉬는 시간을 정리하는 중',
  },
  {
    code: 'FINAL_VALIDATION',
    progress: 95,
    text: '조금만 기다려 주세요. 안전한 루틴인지 마지막으로 확인하는 중',
  },
] as const;

const DOT_INTERVAL_MS = 1_000;
const PHASE_DURATION_SECONDS = 4;
const MASCOT_INTERVAL_MS = 5_000;

export const ROUTINE_GENERATION_ASSETS = {
  bubbles: [
    require('../../assets/routine_loading/dot/01_dots1.png') as ImageSourcePropType,
    require('../../assets/routine_loading/dot/01_dots2.png') as ImageSourcePropType,
    require('../../assets/routine_loading/dot/01_dots3.png') as ImageSourcePropType,
  ],
  mascots: [
    require('../../assets/routine_loading/mascot/01.png') as ImageSourcePropType,
    require('../../assets/routine_loading/mascot/02.png') as ImageSourcePropType,
    require('../../assets/routine_loading/mascot/03.png') as ImageSourcePropType,
  ],
  completedMascot:
    require('../../assets/routine_loading/mascot/06.png') as ImageSourcePropType,
} as const;

function nextMascotIndex(current: number): number {
  const candidate = Math.floor(
    Math.random() * (ROUTINE_GENERATION_ASSETS.mascots.length - 1),
  );
  return candidate >= current ? candidate + 1 : candidate;
}

export type RoutineGenerationLoadingProps = {
  /** Animated artwork supplied by the caller. A neutral spinner reserves its slot for now. */
  asset?: ReactNode;
  /** When present, a server-owned progress code controls the displayed phase. */
  phaseCode?: RoutineGenerationPhaseCode;
};

export function RoutineGenerationLoading({
  asset,
  phaseCode,
}: RoutineGenerationLoadingProps) {
  return <RoutineGenerationLoadingView asset={asset} phaseCode={phaseCode} />;
}

function RoutineGenerationLoadingView({
  asset,
  phaseCode,
}: RoutineGenerationLoadingProps) {
  const { s, f } = useScale();
  const styles = useMemo(() => createStyles(s, f), [f, s]);
  const [tick, setTick] = useState(0);
  const [mascotIndex, setMascotIndex] = useState(() =>
    Math.floor(Math.random() * ROUTINE_GENERATION_ASSETS.mascots.length),
  );
  const [reduceMotion, setReduceMotion] = useState(true);

  const controlledPhaseIndex =
    phaseCode === undefined
      ? -1
      : ROUTINE_GENERATION_PHASES.findIndex(
          (phase) => phase.code === phaseCode,
        );
  const phaseIndex =
    controlledPhaseIndex >= 0
      ? controlledPhaseIndex
      : Math.min(
          Math.floor(tick / PHASE_DURATION_SECONDS),
          // The API response, not an estimated timer, owns the final 95% step.
          ROUTINE_GENERATION_PHASES.length - 2,
        );
  const phase = ROUTINE_GENERATION_PHASES[phaseIndex]!;
  const phaseStartTick =
    controlledPhaseIndex >= 0 ? 0 : phaseIndex * PHASE_DURATION_SECONDS;
  const dotCount = ((tick - phaseStartTick) % 3) + 1;
  const visibleDots = '.'.repeat(dotCount);
  const reservedDots = '.'.repeat(3 - dotCount);
  const finalValidation = phase.code === 'FINAL_VALIDATION';
  const [progress] = useState(() => new Animated.Value(phase.progress));

  useEffect(() => {
    const interval = setInterval(() => {
      setTick((current) => current + 1);
    }, DOT_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (phaseCode === undefined) {
      return undefined;
    }
    const timeout = setTimeout(() => {
      setTick(0);
    }, 0);
    return () => clearTimeout(timeout);
  }, [phaseCode]);

  useEffect(() => {
    if (finalValidation) {
      return undefined;
    }
    const interval = setInterval(() => {
      setMascotIndex(nextMascotIndex);
    }, MASCOT_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [finalValidation]);

  useEffect(() => {
    let active = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (active) setReduceMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotion,
    );
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    progress.stopAnimation();
    if (reduceMotion) {
      progress.setValue(phase.progress);
      return undefined;
    }
    const animation = Animated.timing(progress, {
      duration: 450,
      easing: Easing.out(Easing.cubic),
      toValue: phase.progress,
      useNativeDriver: false,
    });
    animation.start();
    return () => animation.stop();
  }, [phase.progress, progress, reduceMotion]);

  const progressWidth = progress.interpolate({
    inputRange: [0, 100],
    outputRange: ['0%', '100%'],
  });

  return (
    <View style={styles.container} testID="routine-generation-loading">
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={styles.assetSlot}
        testID="routine-generation-asset-slot"
      >
        {asset ?? (
          <View style={styles.mascotScene}>
            {ROUTINE_GENERATION_ASSETS.bubbles.map((source, index) => (
              <Image
                key={`bubble-${index + 1}`}
                resizeMode="contain"
                source={source}
                style={[
                  styles.bubbleImage,
                  {
                    opacity: !finalValidation && dotCount === index + 1 ? 1 : 0,
                  },
                ]}
                testID={`routine-generation-bubble-${index + 1}`}
              />
            ))}
            {ROUTINE_GENERATION_ASSETS.mascots.map((source, index) => (
              <Image
                key={`mascot-${index + 1}`}
                resizeMode="contain"
                source={source}
                style={[
                  styles.mascotImage,
                  {
                    opacity: !finalValidation && mascotIndex === index ? 1 : 0,
                  },
                ]}
                testID={`routine-generation-mascot-${index + 1}`}
              />
            ))}
            <Image
              resizeMode="contain"
              source={ROUTINE_GENERATION_ASSETS.completedMascot}
              style={[
                styles.completedMascotImage,
                { opacity: finalValidation ? 1 : 0 },
              ]}
              testID="routine-generation-mascot-6"
            />
          </View>
        )}
      </View>

      <View
        accessibilityLabel="오늘의 루틴 생성 진행"
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: 100, now: phase.progress }}
        style={styles.progressTrack}
        testID="routine-generation-progress"
      >
        <Animated.View
          style={[styles.progressFill, { width: progressWidth }]}
        />
      </View>

      <Text
        accessible={false}
        importantForAccessibility="no"
        style={styles.message}
        testID="routine-generation-message"
      >
        {phase.text}
        <Text style={styles.messageDots} testID="routine-generation-dots">
          {visibleDots}
        </Text>
        <Text style={styles.messageDotsReserve}>{reservedDots}</Text>
      </Text>
      <Text accessibilityLiveRegion="polite" style={styles.accessibleMessage}>
        {phase.text}
      </Text>
    </View>
  );
}

function createStyles(
  s: (value: number) => number,
  f: (value: number) => number,
) {
  return StyleSheet.create({
    container: {
      width: '100%',
      minHeight: s(210),
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: s(18),
      paddingVertical: s(16),
    },
    assetSlot: {
      width: '100%',
      height: s(112),
      alignItems: 'center',
      justifyContent: 'center',
    },
    mascotScene: {
      position: 'relative',
      width: s(170),
      height: s(112),
    },
    bubbleImage: {
      position: 'absolute',
      top: s(2),
      right: s(8),
      width: s(52),
      height: s(54),
    },
    mascotImage: {
      position: 'absolute',
      left: s(22),
      bottom: 0,
      width: s(88),
      height: s(102),
    },
    completedMascotImage: {
      position: 'absolute',
      left: s(37),
      bottom: 0,
      width: s(96),
      height: s(106),
    },
    progressTrack: {
      width: '76%',
      height: s(16),
      overflow: 'hidden',
      marginTop: s(12),
      borderWidth: s(2),
      borderColor: '#F6BA50',
      borderRadius: 999,
      backgroundColor: '#FFFDF7',
      padding: s(2),
    },
    progressFill: {
      height: '100%',
      borderRadius: 999,
      backgroundColor: '#F6BA50',
    },
    message: {
      minHeight: f(44),
      marginTop: s(16),
      color: '#5A4636',
      fontSize: f(14),
      fontWeight: '800',
      lineHeight: f(21),
      textAlign: 'center',
    },
    messageDots: {
      color: '#5A4636',
    },
    messageDotsReserve: {
      opacity: 0,
    },
    accessibleMessage: {
      position: 'absolute',
      width: 1,
      height: 1,
      opacity: 0,
    },
  });
}
