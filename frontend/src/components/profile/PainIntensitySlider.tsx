import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../theme';

export const PAIN_INTENSITY_MIN = 1;
export const PAIN_INTENSITY_MAX = 10;

type Props = {
  bodyArea: string;
  disabled?: boolean;
  onChange: (value: number) => void;
  testIDPrefix: string;
  value: number;
};

export function PainIntensitySlider({
  bodyArea,
  disabled = false,
  onChange,
  testIDPrefix,
  value,
}: Props) {
  const [trackWidth, setTrackWidth] = useState(0);
  const boundedValue = Math.min(
    PAIN_INTENSITY_MAX,
    Math.max(PAIN_INTENSITY_MIN, Math.round(value)),
  );
  const progress =
    (boundedValue - PAIN_INTENSITY_MIN) /
    (PAIN_INTENSITY_MAX - PAIN_INTENSITY_MIN);
  const label = `${bodyArea} 통증 정도`;

  const updateFromTrack = (locationX: number) => {
    if (disabled || trackWidth <= 0) return;
    const ratio = Math.min(1, Math.max(0, locationX / trackWidth));
    onChange(
      Math.round(
        PAIN_INTENSITY_MIN + ratio * (PAIN_INTENSITY_MAX - PAIN_INTENSITY_MIN),
      ),
    );
  };

  const adjust = (direction: -1 | 1) => {
    if (disabled) return;
    onChange(
      Math.min(
        PAIN_INTENSITY_MAX,
        Math.max(PAIN_INTENSITY_MIN, boundedValue + direction),
      ),
    );
  };

  return (
    <View style={[styles.control, disabled && styles.disabled]}>
      <View style={styles.heading}>
        <Text numberOfLines={1} style={styles.label}>
          {label}
        </Text>
        <Text
          accessibilityLiveRegion="polite"
          style={styles.value}
          testID={`${testIDPrefix}-pain-intensity-value-${bodyArea}`}
        >
          {boundedValue}
        </Text>
      </View>
      <View
        accessible
        accessibilityActions={[
          { name: 'increment', label: `${label} 1 높이기` },
          { name: 'decrement', label: `${label} 1 낮추기` },
        ]}
        accessibilityLabel={label}
        accessibilityRole="adjustable"
        accessibilityState={{ disabled }}
        accessibilityValue={{
          max: PAIN_INTENSITY_MAX,
          min: PAIN_INTENSITY_MIN,
          now: boundedValue,
          text: `10점 중 ${boundedValue}점`,
        }}
        onAccessibilityAction={(event) => {
          if (event.nativeEvent.actionName === 'increment') adjust(1);
          else if (event.nativeEvent.actionName === 'decrement') adjust(-1);
        }}
        onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
        onMoveShouldSetResponder={() => !disabled}
        onResponderGrant={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onResponderMove={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onStartShouldSetResponder={() => !disabled}
        style={styles.touchTarget}
        testID={`${testIDPrefix}-pain-intensity-slider-${bodyArea}`}
      >
        <View
          pointerEvents="none"
          style={styles.track}
          testID={`${testIDPrefix}-pain-intensity-track-${bodyArea}`}
        >
          <View style={[styles.fill, { width: `${progress * 100}%` }]} />
          <View
            style={[styles.thumb, { left: `${progress * 100}%` }]}
            testID={`${testIDPrefix}-pain-intensity-thumb-${bodyArea}`}
          />
        </View>
      </View>
      <View style={styles.rangeLabels}>
        <Text style={styles.rangeLabel}>1</Text>
        <Text style={styles.rangeLabel}>10</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  control: { gap: spacing.xs },
  disabled: { opacity: 0.5 },
  heading: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  label: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  value: {
    minWidth: 34,
    flexShrink: 0,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: 10,
    backgroundColor: colors.surface,
    color: '#8E3226',
    fontSize: 16,
    fontWeight: '400',
    lineHeight: 20,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    textAlign: 'center',
  },
  touchTarget: {
    height: 40,
    justifyContent: 'center',
  },
  track: {
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(162, 63, 42, 0.12)',
  },
  fill: {
    height: '100%',
    borderRadius: 4,
    backgroundColor: 'rgba(162, 63, 42, 0.42)',
  },
  thumb: {
    position: 'absolute',
    top: -7,
    width: 18,
    height: 18,
    marginLeft: -9,
    borderWidth: 2,
    borderColor: colors.surface,
    borderRadius: 9,
    backgroundColor: 'rgba(142, 50, 38, 0.72)',
  },
  rangeLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  rangeLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '400',
  },
});
