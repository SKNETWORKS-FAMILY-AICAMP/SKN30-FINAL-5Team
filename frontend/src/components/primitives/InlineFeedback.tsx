import type { ReactNode } from 'react';
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewProps,
  type ViewStyle,
} from 'react-native';

import { colors, radii, spacing, typography } from '../theme';

export type InlineFeedbackTone = 'success' | 'warning' | 'error';

type InlineFeedbackProps = Omit<ViewProps, 'style'> & {
  action?: ReactNode;
  message: string;
  style?: StyleProp<ViewStyle>;
  tone: InlineFeedbackTone;
};

export function InlineFeedback({
  action,
  message,
  style,
  tone,
  ...viewProps
}: InlineFeedbackProps) {
  const isAlert = tone === 'warning' || tone === 'error';

  return (
    <View
      {...viewProps}
      accessibilityRole={isAlert ? 'alert' : viewProps.accessibilityRole}
      style={[styles.base, toneStyles[tone].container, style]}
    >
      <Text style={[styles.message, toneStyles[tone].message]}>{message}</Text>
      {action}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.feedback,
    paddingHorizontal: 13,
    paddingVertical: 11,
  },
  message: {
    ...typography.feedback,
  },
});

const toneStyles = {
  success: StyleSheet.create({
    container: {
      borderColor: colors.successBorder,
      backgroundColor: colors.successSurface,
    },
    message: {
      color: colors.primary,
    },
  }),
  warning: StyleSheet.create({
    container: {
      borderColor: colors.warningBorder,
      backgroundColor: colors.warningSurface,
    },
    message: {
      color: colors.warningText,
    },
  }),
  error: StyleSheet.create({
    container: {
      borderColor: colors.dangerBorder,
      backgroundColor: colors.dangerSurface,
    },
    message: {
      color: colors.dangerText,
    },
  }),
} as const;
