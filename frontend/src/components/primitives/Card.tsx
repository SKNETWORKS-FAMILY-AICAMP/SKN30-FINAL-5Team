import type { PropsWithChildren } from 'react';
import {
  StyleSheet,
  View,
  type StyleProp,
  type ViewProps,
  type ViewStyle,
} from 'react-native';

import { colors, radii, spacing } from '../theme';

type CardProps = PropsWithChildren<
  Omit<ViewProps, 'style'> & {
    style?: StyleProp<ViewStyle>;
  }
>;

export function Card({ children, style, ...viewProps }: CardProps) {
  return (
    <View {...viewProps} style={[styles.card, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.card,
    backgroundColor: colors.surface,
    padding: spacing.xl,
  },
});
