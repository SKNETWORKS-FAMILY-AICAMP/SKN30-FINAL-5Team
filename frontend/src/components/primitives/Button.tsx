import type { ReactNode } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  type PressableProps,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import { colors, radii, spacing, typography } from '../theme';

type ButtonTone = 'primary' | 'secondary';

type ButtonProps = Omit<PressableProps, 'children' | 'style'> & {
  label: string;
  labelStyle?: StyleProp<TextStyle>;
  leading?: ReactNode;
  tone?: ButtonTone;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  accessibilityState,
  disabled = false,
  label,
  labelStyle,
  leading,
  style,
  tone = 'primary',
  ...pressableProps
}: ButtonProps) {
  const isDisabled = disabled === true;

  return (
    <Pressable
      {...pressableProps}
      accessibilityRole="button"
      accessibilityState={{ ...accessibilityState, disabled: isDisabled }}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        tone === 'primary' ? styles.primary : styles.secondary,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
        style,
      ]}
    >
      {leading}
      <Text
        style={[
          styles.label,
          tone === 'primary' ? styles.primaryLabel : styles.secondaryLabel,
          isDisabled && styles.disabledLabel,
          labelStyle,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 50,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderRadius: radii.button,
    paddingHorizontal: spacing.lg,
  },
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  disabled: {
    borderColor: colors.disabledFill,
    backgroundColor: colors.disabledFill,
  },
  pressed: {
    opacity: 0.84,
  },
  label: {
    ...typography.buttonLabel,
    textAlign: 'center',
  },
  primaryLabel: {
    color: colors.canvas,
  },
  secondaryLabel: {
    color: colors.text,
  },
  disabledLabel: {
    color: colors.textMuted,
  },
});
