/**
 * Calendar integration status for Wave 9C-2A.
 *
 * 9C-2A is the persistence foundation only. There is no Google OAuth flow, no
 * provider adapter, no freeBusy call and no public calendar route in the
 * backend router, so this screen must not present a connect action or any
 * availability data as if it worked.
 *
 * What it does show is the accepted policy boundary (ADR-0010), which is real
 * and verifiable. It displays no event titles, descriptions, attendees,
 * locations, links, raw payloads or tokens — none of which the system stores.
 */

import { StyleSheet, Text, View } from 'react-native';

import { Button, Card } from '../../components/primitives';
import {
  InfoNotice,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

const POLICY_POINTS = [
  '빈 시간(freeBusy) 구간만 사용하고 일정 제목·설명·참석자·장소·링크는 조회하지 않아요.',
  '운동 일정은 앱이 만든 보조 캘린더에만 등록해요.',
  '캘린더 정보는 오늘의 추천, 안전 판단, 운동 완료 상태를 바꾸지 않아요.',
  '연동을 해제해도 이미 만들어진 일정은 사용자의 캘린더에 남아요.',
];

export function CalendarStatusScreen({ onBack }: { onBack: () => void }) {
  return (
    <ScreenShell bands>
      <ScreenHeading
        title="캘린더 연동"
        subtitle="external-context-policy-v2 · ADR-0010"
        onBand
      />

      <Card style={styles.statusCard}>
        <Text style={styles.statusBadge}>연동 준비 중</Text>
        <Text style={styles.statusTitle}>아직 연결할 수 없어요</Text>
        <Text style={styles.statusBody}>
          현재 단계(9C-2A)는 저장 구조만 준비된 상태예요. Google 연동, 빈 시간
          조회, 일정 등록은 아직 서버에 구현되어 있지 않아 이 데모에서는 연결
          버튼을 제공하지 않아요.
        </Text>
      </Card>

      <Card style={styles.policyCard}>
        <Text style={styles.policyTitle}>연동이 열리면 이렇게 동작해요</Text>
        {POLICY_POINTS.map((point) => (
          <View key={point} style={styles.policyRow}>
            <Text style={styles.bullet}>·</Text>
            <Text style={styles.policyText}>{point}</Text>
          </View>
        ))}
      </Card>

      <InfoNotice
        title="운동 완료 기준은 그대로예요"
        message="캘린더가 연결되더라도 공식 완료는 앱에서 운동 블록을 직접 체크할 때만 정해져요."
      />

      <Button label="돌아가기" tone="secondary" onPress={onBack} />
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  statusCard: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.warningBorder,
    backgroundColor: colors.warningSurface,
  },
  statusBadge: {
    alignSelf: 'flex-start',
    overflow: 'hidden',
    borderRadius: 999,
    backgroundColor: colors.warningBorder,
    paddingHorizontal: 10,
    paddingVertical: 4,
    color: colors.warningText,
    fontSize: 11,
    fontWeight: '700',
  },
  statusTitle: {
    color: colors.warningText,
    fontSize: 16,
    fontWeight: '700',
  },
  statusBody: {
    color: colors.warningText,
    fontSize: 13,
    lineHeight: 20,
  },
  policyCard: {
    gap: spacing.sm,
  },
  policyTitle: {
    marginBottom: 2,
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  policyRow: {
    flexDirection: 'row',
    gap: 6,
  },
  bullet: {
    color: colors.greenText,
    fontSize: 13,
  },
  policyText: {
    flex: 1,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
  },
});
