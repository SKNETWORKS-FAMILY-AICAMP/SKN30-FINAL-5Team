import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import {
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { useScale } from '../scale';
import { colors } from '../theme';

type GradientActionButtonProps = Omit<
  PressableProps,
  'children' | 'disabled' | 'style'
> & {
  disabled?: boolean;
  label: string;
  labelStyle?: StyleProp<TextStyle>;
  showChevron?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  trailing?: ReactNode;
};

export function GradientActionButton({
  accessibilityLabel,
  accessibilityState,
  disabled = false,
  label,
  labelStyle,
  showChevron = true,
  style,
  testID,
  trailing,
  ...pressableProps
}: GradientActionButtonProps) {
  const { f, s } = useScale();
  const styles = createStyles(s, f);

  return (
    <Pressable
      {...pressableProps}
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityRole="button"
      accessibilityState={{ ...accessibilityState, disabled }}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        disabled && styles.disabled,
        pressed && !disabled && styles.pressed,
        style,
      ]}
      testID={testID}
    >
      <LinearGradient
        colors={['#FEE8B1', '#FEDA99', '#FFD790']}
        end={{ x: 0.5, y: 1 }}
        locations={[0, 0.55, 1]}
        pointerEvents="none"
        start={{ x: 0.5, y: 0 }}
        style={styles.gradient}
        testID={testID ? `${testID}-gradient` : undefined}
      />
      <Text numberOfLines={1} style={[styles.label, labelStyle]}>
        {label}
      </Text>
      {showChevron ? (
        <View
          pointerEvents="none"
          style={styles.chevron}
          testID={testID ? `${testID}-chevron` : undefined}
        >
          {trailing ?? <GradientActionChevron />}
        </View>
      ) : null}
    </Pressable>
  );
}

function GradientActionChevron() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M9 5.5L16 12l-7 6.5"
        stroke={colors.text}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function createStyles(
  s: (value: number) => number,
  f: (value: number) => number,
) {
  return StyleSheet.create({
    button: {
      position: 'relative',
      width: '100%',
      height: s(58),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: 'rgba(244, 166, 42, 0.8)',
      borderRadius: s(18),
      paddingHorizontal: s(48),
      ...Platform.select({
        ios: {
          shadowColor: '#AD741D',
          shadowOffset: { width: 0, height: s(5) },
          shadowOpacity: 0.11,
          shadowRadius: s(6),
        },
        android: { elevation: 3 },
        default: {
          shadowColor: '#AD741D',
          shadowOffset: { width: 0, height: s(5) },
          shadowOpacity: 0.11,
          shadowRadius: s(6),
        },
      }),
    },
    disabled: { opacity: 0.5 },
    pressed: { transform: [{ translateY: s(1) }] },
    gradient: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      borderRadius: s(18),
    },
    label: {
      color: colors.text,
      fontSize: f(18),
      fontWeight: '700',
      textAlign: 'center',
    },
    chevron: {
      position: 'absolute',
      right: s(20),
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
}
