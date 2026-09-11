import { useState } from 'react';
import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../theme';

export const PAIN_INTENSITY_MIN = 1;
export const PAIN_INTENSITY_MAX = 10;

const VALUE_LABEL_WIDTH = 34;
const TRACK_EDGE_INSET = VALUE_LABEL_WIDTH / 2;

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
  const usableTrackWidth = Math.max(0, trackWidth - TRACK_EDGE_INSET * 2);
  const valueLabelLeft = progress * usableTrackWidth;

  const updateFromTrack = (locationX: number) => {
    if (disabled || usableTrackWidth <= 0) return;
    const ratio = Math.min(
      1,
      Math.max(0, (locationX - TRACK_EDGE_INSET) / usableTrackWidth),
    );
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
          adjustsFontSizeToFit
          minimumFontScale={0.82}
          numberOfLines={1}
          style={styles.scaleHint}
        >
          1~3: 약함, 4~6: 중간, 7~10: 심함
        </Text>
      </View>
      <View
        pointerEvents="none"
        style={styles.rangeLabels}
        testID={`${testIDPrefix}-pain-intensity-range-labels-${bodyArea}`}
      >
        <Text style={styles.rangeLabel}>1</Text>
        <Text style={styles.rangeLabel}>10</Text>
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
          style={[styles.valueCallout, { left: valueLabelLeft }]}
          testID={`${testIDPrefix}-pain-intensity-value-callout-${bodyArea}`}
        >
          <Text
            accessibilityLiveRegion="polite"
            style={styles.value}
            testID={`${testIDPrefix}-pain-intensity-value-${bodyArea}`}
          >
            {boundedValue}
          </Text>
          <View
            style={styles.valuePointer}
            testID={`${testIDPrefix}-pain-intensity-value-pointer-${bodyArea}`}
          />
        </View>
        <View
          pointerEvents="none"
          style={styles.track}
          testID={`${testIDPrefix}-pain-intensity-track-${bodyArea}`}
        >
          <LinearGradient
            colors={['#F6BA50', '#E06555']}
            end={{ x: 1, y: 0 }}
            locations={[0, 1]}
            start={{ x: 0, y: 0 }}
            style={styles.gradientTrack}
            testID={`${testIDPrefix}-pain-intensity-gradient-${bodyArea}`}
          />
          <View
            style={[styles.thumb, { left: `${progress * 100}%` }]}
            testID={`${testIDPrefix}-pain-intensity-thumb-${bodyArea}`}
          />
        </View>
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
    gap: 6,
  },
  label: {
    flexShrink: 0,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  scaleHint: {
    minWidth: 0,
    flex: 1,
    color: colors.textFaint,
    fontSize: 9,
    fontWeight: '400',
    lineHeight: 13,
    textAlign: 'right',
  },
  valueCallout: {
    position: 'absolute',
    top: 0,
    zIndex: 2,
    width: VALUE_LABEL_WIDTH,
    alignItems: 'center',
  },
  value: {
    width: VALUE_LABEL_WIDTH,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: 10,
    backgroundColor: colors.surface,
    color: '#8E3226',
    fontSize: 16,
    fontWeight: '400',
    lineHeight: 20,
    paddingVertical: 2,
    textAlign: 'center',
  },
  valuePointer: {
    position: 'absolute',
    bottom: -3,
    width: 8,
    height: 8,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.surface,
    transform: [{ rotate: '45deg' }],
  },
  touchTarget: {
    height: 54,
    justifyContent: 'flex-end',
    paddingHorizontal: TRACK_EDGE_INSET,
    paddingBottom: 9,
  },
  track: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
  },
  gradientTrack: {
    height: '100%',
    borderRadius: 4,
  },
  thumb: {
    position: 'absolute',
    top: -7,
    width: 18,
    height: 18,
    marginLeft: -9,
    borderWidth: 2,
    borderColor: '#A94B3D',
    borderRadius: 9,
    backgroundColor: colors.surface,
  },
  rangeLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
    paddingHorizontal: TRACK_EDGE_INSET,
  },
  rangeLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '400',
  },
});
