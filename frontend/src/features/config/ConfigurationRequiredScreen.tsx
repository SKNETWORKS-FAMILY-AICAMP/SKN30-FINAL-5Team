/**
 * Fail-closed state for missing configuration.
 *
 * The app cannot reach the backend or Firebase without these values, and it
 * must not fall back to a bypass. The screen names the missing keys so the
 * tester can fix the environment, and never prints their values.
 */

import { StyleSheet, Text, View } from 'react-native';

import { Card } from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import type { EnvIssue } from '../../config/env';

export function ConfigurationRequiredScreen({
  issues,
}: {
  issues: EnvIssue[];
}) {
  return (
    <ScreenShell contentStyle={styles.content}>
      <ScreenHeading
        title="설정이 필요해요"
        subtitle="데모를 실행하려면 아래 환경변수를 설정한 뒤 앱을 다시 시작해주세요."
      />

      <Card style={styles.card}>
        {issues.map((issue) => (
          <View key={issue.key} style={styles.row}>
            <Text style={styles.key}>{issue.key}</Text>
            <Text style={styles.message}>{issue.message}</Text>
          </View>
        ))}
      </Card>

      <Card style={styles.helpCard}>
        <Text style={styles.helpTitle}>설정 위치</Text>
        <Text style={styles.helpText}>
          {'frontend/.env.local 파일에 값을 넣고 Expo 개발 서버를 다시 시작해요.\n' +
            '예: EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000'}
        </Text>
        <Text style={styles.helpNote}>
          Android 에뮬레이터는 10.0.2.2, iOS 시뮬레이터는 localhost, 실제 기기는
          개발 PC의 LAN IP를 사용해요.
        </Text>
      </Card>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: spacing.lg,
    paddingTop: 64,
  },
  card: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
  },
  row: {
    gap: 4,
  },
  key: {
    color: colors.dangerText,
    fontSize: 13,
    fontWeight: '700',
  },
  message: {
    color: colors.dangerText,
    fontSize: 13,
    lineHeight: 19,
  },
  helpCard: {
    gap: spacing.sm,
  },
  helpTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  helpText: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
  },
  helpNote: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
});
