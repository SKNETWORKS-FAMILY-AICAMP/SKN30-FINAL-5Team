/**
 * Profile view, sign out, and the account-deletion lifecycle.
 *
 * Deletion is irreversible and blocks ordinary API access immediately, so it is
 * behind an explicit confirmation and the resulting deadline is shown plainly.
 */

import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { bodyAreaLabel, trainingTypeLabel } from '../../api/labels';
import type { MeResponse } from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  SafetyNotice,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

export function AccountScreen({
  api,
  me,
  onBack,
  onSignOut,
}: {
  api: Api;
  me: MeResponse;
  onBack: () => void;
  onSignOut: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deletedAt, setDeletedAt] = useState<string | null>(null);

  const requestDeletion = useAsyncAction(async () => {
    const response = await api.requestAccountDeletion();
    setDeletedAt(response.operational_data_delete_by);
    setConfirming(false);
  });

  const profile = me.profile;

  return (
    <ScreenShell bands>
      <ScreenHeading title="내 프로필" onBand />

      {profile === null ? (
        <Card style={styles.card}>
          <Text style={styles.body}>아직 온보딩을 완료하지 않았어요.</Text>
        </Card>
      ) : (
        <Card style={styles.card}>
          <Row label="닉네임" value={profile.nickname} />
          {profile.age !== null ? (
            <Row label="나이" value={`만 ${profile.age}세`} />
          ) : null}
          <Row label="시간대" value={profile.timezone} />
          <Row
            label="희망 운동 시간"
            value={`${profile.default_requested_duration_minutes}분`}
          />
          <Row
            label="주간 목표"
            value={`주 ${profile.desired_weekly_workout_count}회`}
          />
          <Row
            label="운동 장소"
            value={profile.available_location_codes.join(', ')}
          />
          <Row label="장비" value={profile.equipment_codes.join(', ')} />
          <Row
            label="선호 운동"
            value={
              profile.preferred_exercise_type_codes
                .map(trainingTypeLabel)
                .join(', ') || '지정 안 함'
            }
          />
          <Row
            label="주의 부위"
            value={
              profile.attention_area_codes.map(bodyAreaLabel).join(', ') ||
              '없음'
            }
          />
        </Card>
      )}

      {deletedAt !== null ? (
        <SafetyNotice
          title="계정 삭제를 접수했어요"
          message={`이 계정은 더 이상 사용할 수 없어요. 운영 데이터는 ${deletedAt.slice(0, 10)}까지 삭제돼요.`}
        />
      ) : (
        <Card style={styles.dangerCard}>
          <Text style={styles.dangerTitle}>계정 삭제</Text>
          <Text style={styles.dangerBody}>
            삭제를 요청하면 되돌릴 수 없고, 즉시 서비스 이용이 중단돼요.
          </Text>
          {requestDeletion.error ? (
            <InlineFeedback tone="error" message={requestDeletion.error} />
          ) : null}
          {confirming ? (
            <View style={styles.confirmRow}>
              <Button
                label={
                  requestDeletion.pending ? '요청 중…' : '삭제를 요청할게요'
                }
                disabled={requestDeletion.pending}
                onPress={() => void requestDeletion.run()}
              />
              <Button
                label="취소"
                tone="secondary"
                onPress={() => setConfirming(false)}
              />
            </View>
          ) : (
            <Button
              label="계정 삭제 요청"
              tone="secondary"
              onPress={() => setConfirming(true)}
            />
          )}
        </Card>
      )}

      <Button label="로그아웃" tone="secondary" onPress={onSignOut} />
      <Button label="돌아가기" tone="secondary" onPress={onBack} />
    </ScreenShell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  rowLabel: {
    color: colors.textMuted,
    fontSize: 13,
  },
  rowValue: {
    flex: 1,
    color: colors.text,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'right',
  },
  body: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  dangerCard: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
  },
  dangerTitle: {
    color: colors.dangerText,
    fontSize: 15,
    fontWeight: '700',
  },
  dangerBody: {
    color: colors.dangerText,
    fontSize: 13,
    lineHeight: 19,
  },
  confirmRow: {
    gap: spacing.sm,
  },
});
