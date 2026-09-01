/**
 * Shared −/value/+ control for duration and weekly-count settings.
 *
 * Onboarding and my page ask for the same values, so they use this one control
 * instead of two look-alike implementations.
 */

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../theme';
import { Card } from './Card';

type StepCounterProps = {
  decreaseLabel: string;
  disabled?: boolean;
  increaseLabel: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  prefix?: string;
  step?: number;
  suffix: string;
  value: number;
};

export function StepCounter({
  decreaseLabel,
  disabled = false,
  increaseLabel,
  max,
  min,
  onChange,
  prefix = '',
  step = 1,
  suffix,
  value,
}: StepCounterProps) {
  const canDecrease = !disabled && value > min;
  const canIncrease = !disabled && value < max;

  return (
    <Card style={styles.counterCard}>
      <Pressable
        accessibilityLabel={decreaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canDecrease }}
        disabled={!canDecrease}
        onPress={() => onChange(Math.max(min, value - step))}
        style={[
          styles.counterButton,
          !canDecrease && styles.counterButtonDisabled,
        ]}
      >
        <View pointerEvents="none" style={styles.counterIcon}>
          <View style={styles.counterIconBar} />
        </View>
      </Pressable>
      <Text accessibilityLiveRegion="polite" style={styles.counterValue}>
        {prefix}
        {value}
        {suffix}
      </Text>
      <Pressable
        accessibilityLabel={increaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canIncrease }}
        disabled={!canIncrease}
        onPress={() => onChange(Math.min(max, value + step))}
        style={[
          styles.counterButton,
          !canIncrease && styles.counterButtonDisabled,
        ]}
      >
        <View pointerEvents="none" style={styles.counterIcon}>
          <View style={styles.counterIconBar} />
          <View
            style={[styles.counterIconBar, styles.counterIconBarVertical]}
          />
        </View>
      </Pressable>
    </Card>
  );
}

const styles = StyleSheet.create({
  counterCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.lg,
  },
  counterButton: {
    width: 56,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.primary,
    borderRadius: 28,
    backgroundColor: colors.surface,
  },
  counterButtonDisabled: { borderColor: colors.border, opacity: 0.4 },
  counterIcon: {
    position: 'relative',
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  counterIconBar: {
    position: 'absolute',
    width: 20,
    height: 2.5,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  counterIconBarVertical: {
    transform: [{ rotate: '90deg' }],
  },
  counterValue: {
    minWidth: 100,
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
  },
});
