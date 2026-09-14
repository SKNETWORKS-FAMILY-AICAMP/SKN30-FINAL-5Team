import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Card } from '../../components/primitives';
import { colors, shadows, spacing } from '../../components/theme';
import { PolicyDetails } from '../onboarding/PolicyDetails';

export type MyPageAccountDetail = 'privacy' | 'inquiry' | 'terms';

const PRIVACY_DOCUMENTS = [
  { documentId: 'privacy_policy' as const, label: '개인정보처리방침 확인' },
  {
    documentId: 'general_personal_data' as const,
    label: '개인정보 수집 및 이용',
  },
  {
    documentId: 'sensitive_data' as const,
    label: '건강 관련 민감정보 처리',
  },
] as const;

export function accountDetailForLabel(
  label: string,
): MyPageAccountDetail | null {
  if (label === '개인정보 처리방침 및 이용') return 'privacy';
  if (label === '문의하기') return 'inquiry';
  if (label === '이용약관') return 'terms';
  return null;
}

export function MyPageAccountDetails({
  detail,
  onBack,
}: {
  detail: MyPageAccountDetail;
  onBack: () => void;
}) {
  const title =
    detail === 'privacy'
      ? '개인정보 처리방침 및 이용'
      : detail === 'terms'
        ? '이용약관'
        : '문의하기';

  return (
    <ScrollView
      contentContainerStyle={[
        styles.content,
        detail === 'inquiry' && styles.inquiryContent,
      ]}
      showsVerticalScrollIndicator={false}
      style={styles.scroll}
    >
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="마이페이지로 돌아가기"
          accessibilityRole="button"
          hitSlop={8}
          onPress={onBack}
          style={styles.backButton}
        >
          <View style={styles.backChevron} />
        </Pressable>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        <View pointerEvents="none" style={styles.headerSpacer} />
      </View>

      {detail === 'privacy' ? (
        <View style={styles.sections}>
          {PRIVACY_DOCUMENTS.map(({ documentId, label }) => (
            <Card key={documentId} style={styles.policyCard}>
              <Text style={styles.policyLabel}>{label}</Text>
              <PolicyDetails documentId={documentId} />
            </Card>
          ))}
        </View>
      ) : detail === 'terms' ? (
        <Card style={styles.policyCard}>
          <Text style={styles.policyLabel}>서비스 이용약관 동의</Text>
          <PolicyDetails documentId="service_terms" />
        </Card>
      ) : (
        <View style={styles.inquiryBody}>
          <Card style={styles.inquiryCard}>
            <Text selectable style={styles.inquiryText}>
              SKN30th-FINAL-5team
            </Text>
            <Text selectable style={styles.inquiryText}>
              TEAM 콩닥 관리자
            </Text>
            <Text selectable style={styles.inquiryEmail}>
              qwop1651@naver.com
            </Text>
          </Card>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  content: {
    flexGrow: 1,
    gap: spacing.lg,
    paddingTop: 54,
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  inquiryContent: {
    backgroundColor: colors.canvas,
  },
  header: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  backButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 22,
    backgroundColor: colors.surface,
  },
  backChevron: {
    width: 12,
    height: 12,
    borderBottomWidth: 2.5,
    borderLeftWidth: 2.5,
    borderColor: colors.text,
    transform: [{ rotate: '45deg' }],
  },
  title: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 20,
    fontWeight: '800',
    textAlign: 'center',
  },
  headerSpacer: {
    width: 44,
    height: 44,
  },
  sections: {
    gap: spacing.md,
  },
  policyCard: {
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    paddingVertical: 10,
    ...shadows.card,
  },
  policyLabel: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  inquiryBody: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 72,
  },
  inquiryCard: {
    width: '100%',
    maxWidth: 360,
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: 22,
    paddingVertical: 30,
    ...shadows.card,
  },
  inquiryText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  inquiryEmail: {
    marginTop: 4,
    color: colors.greenText,
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
  },
});
