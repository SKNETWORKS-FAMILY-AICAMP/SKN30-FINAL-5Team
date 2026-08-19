/**
 * One-at-a-time exercise block carousel.
 *
 * The current block sits centred at the bottom of the screen. Completing it
 * slides the track left so the finished card leaves to the left and the next
 * block arrives in the centre from the right.
 *
 * The animation is driven by `currentIndex`, which the session screen derives
 * from the server's item states. Sliding is therefore a consequence of a
 * confirmed completion, never a substitute for one: nothing here calls the
 * completion API or infers progress from position.
 */

import { useEffect, useState } from 'react';
import {
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { SessionItem, WorkoutPlanItem } from '../../api/types';
import { useBrandFontFamily } from '../../components/brand/BrandChrome';
import { colors, radii, shadows, spacing } from '../../components/theme';
import { WORKOUT_CAROUSEL } from './workoutModel';

const USE_NATIVE_DRIVER = Platform.OS !== 'web';

export function SessionCarousel({
  items,
  states,
  currentIndex,
  pending,
  onToggle,
  onOpenDetail,
  detailFor,
  detail,
}: {
  items: readonly WorkoutPlanItem[];
  states: readonly SessionItem[];
  currentIndex: number;
  pending: boolean;
  onToggle: (planItemId: string, next: 'PENDING' | 'COMPLETED') => void;
  onOpenDetail: (exerciseId: string | null) => void;
  detailFor: string | null;
  detail: React.ReactNode;
}) {
  const [viewportWidth, setViewportWidth] = useState(0);
  // Held in state, not a ref: the value is read during render to build the
  // per-card interpolations, which a ref must not be used for.
  const [translateX] = useState(() => new Animated.Value(0));
  const family = useBrandFontFamily();

  useEffect(() => {
    Animated.spring(translateX, {
      toValue: -currentIndex * WORKOUT_CAROUSEL.STRIDE,
      useNativeDriver: USE_NATIVE_DRIVER,
      friction: 9,
      tension: 60,
    }).start();
  }, [currentIndex, translateX]);

  const leadingOffset = Math.max(
    (viewportWidth - WORKOUT_CAROUSEL.CARD_WIDTH) / 2,
    0,
  );

  return (
    <View
      style={styles.viewport}
      onLayout={(event) => setViewportWidth(event.nativeEvent.layout.width)}
    >
      <Animated.View
        style={[
          styles.track,
          { paddingLeft: leadingOffset, transform: [{ translateX }] },
        ]}
      >
        {items.map((item, index) => {
          const state = states.find(
            (candidate) => candidate.plan_item_id === item.plan_item_id,
          );
          const done = state?.status_code === 'COMPLETED';
          const centre = -index * WORKOUT_CAROUSEL.STRIDE;
          const inputRange = [
            centre - WORKOUT_CAROUSEL.STRIDE,
            centre,
            centre + WORKOUT_CAROUSEL.STRIDE,
          ];

          return (
            <Animated.View
              key={item.plan_item_id}
              style={[
                styles.card,
                done && styles.cardDone,
                {
                  opacity: translateX.interpolate({
                    inputRange,
                    outputRange: [0.35, 1, 0.35],
                    extrapolate: 'clamp',
                  }),
                  transform: [
                    {
                      scale: translateX.interpolate({
                        inputRange,
                        outputRange: [0.86, 1, 0.86],
                        extrapolate: 'clamp',
                      }),
                    },
                  ],
                },
              ]}
            >
              <View style={styles.cardHeader}>
                <Text style={styles.sequence}>
                  {item.sequence} / {items.length}
                </Text>
                {done ? <Text style={styles.doneBadge}>완료</Text> : null}
              </View>

              <Text
                style={[styles.name, family ? { fontFamily: family } : null]}
              >
                {item.exercise_name}
              </Text>
              <Text style={styles.meta}>
                {item.sets}세트
                {item.reps === null
                  ? ` · ${item.work_seconds}초`
                  : ` × ${item.reps}회`}
              </Text>
              {item.rest_seconds > 0 ? (
                <Text style={styles.rest}>휴식 {item.rest_seconds}초</Text>
              ) : null}

              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${item.exercise_name} 자세와 설명`}
                onPress={() =>
                  onOpenDetail(
                    detailFor === item.exercise_id ? null : item.exercise_id,
                  )
                }
                style={styles.detailToggle}
              >
                <Text style={styles.detailToggleLabel}>
                  {detailFor === item.exercise_id ? '설명 접기' : '자세 보기'}
                </Text>
              </Pressable>

              {detailFor === item.exercise_id ? (
                <View style={styles.detail}>{detail}</View>
              ) : null}

              <Pressable
                accessibilityRole="button"
                accessibilityState={{ checked: done, disabled: pending }}
                disabled={pending}
                onPress={() =>
                  onToggle(item.plan_item_id, done ? 'PENDING' : 'COMPLETED')
                }
                style={[styles.checkButton, done && styles.checkButtonDone]}
              >
                <Text
                  style={[
                    styles.checkLabel,
                    done && styles.checkLabelDone,
                    family ? { fontFamily: family } : null,
                  ]}
                >
                  {done ? '완료 취소' : '완료 체크'}
                </Text>
              </Pressable>
            </Animated.View>
          );
        })}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  viewport: {
    overflow: 'hidden',
    paddingVertical: spacing.md,
  },
  track: {
    flexDirection: 'row',
    gap: WORKOUT_CAROUSEL.GAP,
  },
  card: {
    width: WORKOUT_CAROUSEL.CARD_WIDTH,
    gap: 6,
    borderRadius: radii.card,
    backgroundColor: colors.surface,
    padding: spacing.xl,
    ...shadows.card,
  },
  cardDone: {
    backgroundColor: colors.successSurface,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sequence: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  doneBadge: {
    overflow: 'hidden',
    borderRadius: 999,
    backgroundColor: colors.greenBand,
    paddingHorizontal: 8,
    paddingVertical: 3,
    color: colors.primary,
    fontSize: 11,
    fontWeight: '700',
  },
  name: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '700',
  },
  meta: {
    color: colors.textSub,
    fontSize: 13,
  },
  rest: {
    color: colors.textMuted,
    fontSize: 12,
  },
  detailToggle: {
    alignSelf: 'flex-start',
    paddingVertical: 2,
  },
  detailToggleLabel: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
  },
  detail: {
    marginTop: 2,
  },
  checkButton: {
    marginTop: spacing.sm,
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.button,
    backgroundColor: colors.primary,
  },
  checkButtonDone: {
    borderWidth: 1.5,
    borderColor: colors.greenBorder,
    backgroundColor: colors.surface,
  },
  checkLabel: {
    color: colors.canvas,
    fontSize: 15,
    fontWeight: '700',
  },
  checkLabelDone: {
    color: colors.greenText,
  },
});
