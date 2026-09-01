/**
 * The loading / empty / error states every API-backed screen must be able to
 * show, in the existing card-on-canvas visual language.
 *
 * `SafetyNotice` is deliberately separate from `InlineFeedback`: pain and
 * adverse-response messages use a serious tone and must never sit next to
 * playful presentation.
 */

import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BackgroundBands, useBrandFontFamily } from '../brand/BrandChrome';
import { Button, Card } from '../primitives';
import { colors, radii, spacing } from '../theme';

export function ScreenShell({
  children,
  contentStyle,
  scroll = true,
  bands = false,
  tallBands = false,
  footer,
}: {
  children: React.ReactNode;
  contentStyle?: StyleProp<ViewStyle>;
  scroll?: boolean;
  /** Green brand bands behind the content, as on the main product screens. */
  bands?: boolean;
  tallBands?: boolean;
  /** Rendered outside the scroll area, for the bottom tab bar. */
  footer?: React.ReactNode;
}) {
  return (
    <SafeAreaView
      style={styles.screen}
      edges={footer ? ['top'] : ['top', 'bottom']}
      testID="screen-shell-safe-area"
    >
      {bands ? <BackgroundBands tall={tallBands} /> : null}
      {scroll ? (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={[styles.scrollContent, contentStyle]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.scrollContent, styles.flex, contentStyle]}>
          {children}
        </View>
      )}
      {footer}
    </SafeAreaView>
  );
}

export function ScreenHeading({
  title,
  subtitle,
  /** Set on banded screens, where the heading sits on the green field. */
  onBand = false,
}: {
  title: string;
  subtitle?: string;
  onBand?: boolean;
}) {
  const family = useBrandFontFamily();
  return (
    <View style={styles.heading}>
      <Text
        accessibilityRole="header"
        style={[
          styles.title,
          family ? { fontFamily: family } : null,
          onBand && styles.titleOnBand,
        ]}
      >
        {title}
      </Text>
      {subtitle ? (
        <Text style={[styles.subtitle, onBand && styles.subtitleOnBand]}>
          {subtitle}
        </Text>
      ) : null}
    </View>
  );
}

export function LoadingState({
  label = '불러오는 중이에요',
}: {
  label?: string;
}) {
  return (
    <Card style={styles.centered}>
      <ActivityIndicator color={colors.primary} />
      <Text style={styles.stateText}>{label}</Text>
    </Card>
  );
}

export function EmptyState({
  message,
  actionLabel,
  onAction,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <Card style={styles.centered}>
      <Text style={styles.stateText}>{message}</Text>
      {actionLabel && onAction ? (
        <Button label={actionLabel} onPress={onAction} style={styles.action} />
      ) : null}
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
  retryLabel = '다시 시도',
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <Card style={styles.errorCard}>
      <Text accessibilityRole="alert" style={styles.errorText}>
        {message}
      </Text>
      {onRetry ? (
        <Button
          label={retryLabel}
          onPress={onRetry}
          tone="secondary"
          style={styles.action}
        />
      ) : null}
    </Card>
  );
}

/**
 * Serious-tone notice for safety stops. No mascot, no celebratory colour.
 */
export function SafetyNotice({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <View accessibilityRole="alert" style={styles.safety}>
      <Text style={styles.safetyTitle}>{title}</Text>
      <Text style={styles.safetyMessage}>{message}</Text>
    </View>
  );
}

export function InfoNotice({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <View style={styles.info}>
      <Text style={styles.infoTitle}>{title}</Text>
      <Text style={styles.infoMessage}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  flex: {
    flex: 1,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    gap: 14,
    paddingHorizontal: 18,
    paddingTop: 24,
    paddingBottom: 40,
  },
  heading: {
    gap: 6,
    paddingHorizontal: 4,
  },
  title: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '700',
  },
  titleOnBand: {
    color: colors.text,
  },
  subtitleOnBand: {
    color: colors.textSub,
  },
  subtitle: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  centered: {
    alignItems: 'center',
    gap: spacing.md,
  },
  errorCard: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
  },
  stateText: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  errorText: {
    color: colors.dangerText,
    fontSize: 14,
    lineHeight: 20,
  },
  action: {
    alignSelf: 'stretch',
  },
  safety: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: radii.card,
    backgroundColor: colors.dangerSurface,
    padding: spacing.xl,
  },
  safetyTitle: {
    color: colors.dangerText,
    fontSize: 16,
    fontWeight: '700',
  },
  safetyMessage: {
    color: colors.dangerText,
    fontSize: 14,
    lineHeight: 21,
  },
  info: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.greenBorder,
    borderRadius: radii.card,
    backgroundColor: colors.greenTint,
    padding: spacing.xl,
  },
  infoTitle: {
    color: colors.greenText,
    fontSize: 15,
    fontWeight: '700',
  },
  infoMessage: {
    color: colors.primary,
    fontSize: 13,
    lineHeight: 20,
  },
});
