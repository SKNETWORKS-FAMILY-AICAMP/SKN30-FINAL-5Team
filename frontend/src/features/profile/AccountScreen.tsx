/**
 * Profile view, sign out, and the account-deletion lifecycle.
 *
 * Deletion is irreversible and blocks ordinary API access immediately, so it is
 * behind an explicit confirmation and the resulting deadline is shown plainly.
 */

import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  bodyAreaLabel,
  equipmentLabel,
  locationLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type { ConsentValues, MeResponse } from '../../api/types';
import { useAsyncAction, useAsyncData } from '../../api/useAsync';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  SafetyNotice,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

/**
 * The required pair cannot be withdrawn here: revoking them means the service
 * cannot operate for this account, which is the account-deletion path below,
 * not a toggle.
 */
const OPTIONAL_CONSENTS = [
  { key: 'wearable_integration', label: '웨어러블 연동' },
  { key: 'calendar_integration', label: '캘린더 연동' },
  { key: 'marketing', label: '마케팅 정보 수신' },
] as const;

const COACHING_STYLES = [
  { code: 'SUPPORTIVE', label: '다정하게' },
  { code: 'CONCISE', label: '간결하게' },
  { code: 'ENERGETIC', label: '에너지 넘치게' },
] as const;

export function AccountScreen({
  api,
  me,
  onBack,
  onSignOut,
  onProfileUpdated,
  onOpenExerciseCatalog,
}: {
  api: Api;
  me: MeResponse;
  onBack: () => void;
  onSignOut: () => void;
  /** Called after a saved change so the flow above re-reads `/me`. */
  onProfileUpdated?: () => void;
  onOpenExerciseCatalog?: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deletedAt, setDeletedAt] = useState<string | null>(null);
  const [pendingStyle, setPendingStyle] = useState<string | null>(null);
  const [pendingDuration, setPendingDuration] = useState<number | null>(null);
  const [pendingWeeklyCount, setPendingWeeklyCount] = useState<number | null>(
    null,
  );
  const profile = me.profile;

  const saveCoachingStyle = useAsyncAction(async () => {
    if (pendingStyle === null || profile === null) {
      return;
    }
    await api.updateProfileSettings(
      { coaching_style_code: pendingStyle },
      profile.profile_version,
    );
    setPendingStyle(null);
    onProfileUpdated?.();
  });

  const saveGoals = useAsyncAction(async () => {
    if (profile === null) {
      return;
    }
    // Only the changed fields are sent; the server owns range validation and
    // these values never shorten an already-requested day retroactively.
    const body: {
      default_requested_duration_minutes?: number;
      desired_weekly_workout_count?: number;
    } = {};
    if (pendingDuration !== null) {
      body.default_requested_duration_minutes = pendingDuration;
    }
    if (pendingWeeklyCount !== null) {
      body.desired_weekly_workout_count = pendingWeeklyCount;
    }
    if (Object.keys(body).length === 0) {
      return;
    }
    await api.updateProfileSettings(body, profile.profile_version);
    setPendingDuration(null);
    setPendingWeeklyCount(null);
    onProfileUpdated?.();
  });

  const consents = useAsyncData((signal) => api.getConsents(signal), [api]);
  const [pendingConsents, setPendingConsents] = useState<ConsentValues | null>(
    null,
  );

  const storedConsents: ConsentValues | null =
    consents.state.status === 'ready' && consents.state.data.consents.length > 0
      ? (Object.fromEntries(
          consents.state.data.consents.map((item) => [
            item.consent_type_code.toLowerCase(),
            item.granted,
          ]),
        ) as unknown as ConsentValues)
      : null;

  const saveConsents = useAsyncAction(async () => {
    if (pendingConsents === null) {
      return;
    }
    await api.replaceConsents(pendingConsents);
    setPendingConsents(null);
    consents.reload();
  });

  const requestDeletion = useAsyncAction(async () => {
    const response = await api.requestAccountDeletion();
    setDeletedAt(response.operational_data_delete_by);
    setConfirming(false);
  });

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
          <StepperRow
            label="희망 운동 시간"
            value={
              pendingDuration ?? profile.default_requested_duration_minutes
            }
            unit="분"
            step={5}
            min={10}
            max={120}
            onChange={setPendingDuration}
          />
          <StepperRow
            label="주간 목표"
            value={pendingWeeklyCount ?? profile.desired_weekly_workout_count}
            unit="회"
            step={1}
            min={1}
            max={7}
            onChange={setPendingWeeklyCount}
          />
          {saveGoals.error ? (
            <InlineFeedback tone="error" message={saveGoals.error} />
          ) : null}
          {(pendingDuration !== null &&
            pendingDuration !== profile.default_requested_duration_minutes) ||
          (pendingWeeklyCount !== null &&
            pendingWeeklyCount !== profile.desired_weekly_workout_count) ? (
            <Button
              label={saveGoals.pending ? '저장 중…' : '목표 저장'}
              disabled={saveGoals.pending}
              onPress={() => void saveGoals.run()}
            />
          ) : null}
          <Row
            label="운동 장소"
            value={profile.available_location_codes
              .map(locationLabel)
              .join(', ')}
          />
          <Row
            label="장비"
            value={profile.equipment_codes.map(equipmentLabel).join(', ')}
          />
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

      {profile !== null ? (
        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>코칭 스타일</Text>
          <Text style={styles.body}>헬끼가 말을 거는 방식이 달라져요.</Text>
          <View style={styles.styleRow}>
            {COACHING_STYLES.map(({ code, label }) => {
              const selected =
                (pendingStyle ?? profile.coaching_style_code) === code;
              return (
                <Pressable
                  key={code}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() => setPendingStyle(code)}
                  style={[
                    styles.styleOption,
                    selected && styles.styleOptionSelected,
                  ]}
                >
                  <Text
                    style={[
                      styles.styleOptionText,
                      selected && styles.styleOptionTextSelected,
                    ]}
                  >
                    {label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          {saveCoachingStyle.error ? (
            <InlineFeedback tone="error" message={saveCoachingStyle.error} />
          ) : null}
          {pendingStyle !== null &&
          pendingStyle !== profile.coaching_style_code ? (
            <Button
              label={saveCoachingStyle.pending ? '저장 중…' : '저장'}
              disabled={saveCoachingStyle.pending}
              onPress={() => void saveCoachingStyle.run()}
            />
          ) : null}
        </Card>
      ) : null}

      {storedConsents !== null ? (
        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>선택 동의 관리</Text>
          <Text style={styles.body}>
            필수 동의는 서비스 이용에 필요해 여기서 바꿀 수 없어요.
          </Text>
          {OPTIONAL_CONSENTS.map(({ key, label }) => {
            const current = pendingConsents ?? storedConsents;
            const granted = current[key];
            return (
              <Pressable
                key={key}
                accessibilityRole="switch"
                accessibilityState={{ checked: granted }}
                onPress={() =>
                  setPendingConsents({ ...current, [key]: !granted })
                }
                style={styles.consentRow}
              >
                <Text style={styles.rowLabel}>{label}</Text>
                <Text
                  style={[
                    styles.consentState,
                    granted && styles.consentStateOn,
                  ]}
                >
                  {granted ? '동의함' : '동의 안 함'}
                </Text>
              </Pressable>
            );
          })}
          {saveConsents.error ? (
            <InlineFeedback tone="error" message={saveConsents.error} />
          ) : null}
          {pendingConsents !== null ? (
            <Button
              label={saveConsents.pending ? '저장 중…' : '동의 변경 저장'}
              disabled={saveConsents.pending}
              onPress={() => void saveConsents.run()}
            />
          ) : null}
        </Card>
      ) : null}

      {onOpenExerciseCatalog ? (
        <Button
          label="운동 카탈로그 둘러보기"
          tone="secondary"
          onPress={onOpenExerciseCatalog}
        />
      ) : null}

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

function StepperRow({
  label,
  value,
  unit,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  unit: string;
  step: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.stepper}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${label} 줄이기`}
          disabled={value - step < min}
          onPress={() => onChange(Math.max(min, value - step))}
          style={[
            styles.stepperButton,
            value - step < min && styles.stepperButtonDisabled,
          ]}
        >
          <Text style={styles.stepperButtonText}>−</Text>
        </Pressable>
        <Text style={styles.stepperValue}>
          {value}
          {unit}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${label} 늘리기`}
          disabled={value + step > max}
          onPress={() => onChange(Math.min(max, value + step))}
          style={[
            styles.stepperButton,
            value + step > max && styles.stepperButtonDisabled,
          ]}
        >
          <Text style={styles.stepperButtonText}>+</Text>
        </Pressable>
      </View>
    </View>
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
  sectionTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  styleRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  styleOption: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  styleOptionSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  styleOptionText: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  styleOptionTextSelected: {
    color: colors.surface,
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
  consentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
  },
  consentState: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  consentStateOn: {
    color: colors.primary,
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  stepperButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  stepperButtonDisabled: {
    opacity: 0.35,
  },
  stepperButtonText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  stepperValue: {
    minWidth: 48,
    textAlign: 'center',
    color: colors.text,
    fontSize: 13,
    fontWeight: '600',
  },
});
