/**
 * Onboarding profile and consent capture.
 *
 * Every code sent here is a server-approved machine code; the Korean text is
 * presentation only. Age eligibility is decided by the server from the
 * birthdate, so this screen never gates on age itself — it renders the server's
 * `403 AGE_REQUIREMENT_NOT_MET` answer.
 */

import { useCallback, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAsyncAction } from '../../api/useAsync';
import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import { BODY_AREA_OPTIONS } from '../../api/labels';
import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';

/**
 * The demo deployment approves exactly one goal and one experience level, so
 * these are fixed rather than presented as a choice the server would reject.
 */
const PRIMARY_GOAL_CODE = 'GENERAL_FITNESS';
const EXPERIENCE_LEVEL_CODE = 'BEGINNER';

const LOCATIONS = [
  { code: 'HOME', label: '집' },
  { code: 'GYM', label: '헬스장' },
];

const EQUIPMENT = [
  { code: 'BODYWEIGHT', label: '맨몸' },
  { code: 'MAT', label: '매트' },
  { code: 'RESISTANCE_BAND', label: '밴드' },
];

const DURATIONS = [20, 30, 40, 50];
const WEEKLY_COUNTS = [2, 3, 4, 5];

function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </Card>
  );
}

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export function OnboardingScreen({
  api,
  onCompleted,
  onSignOut,
}: {
  api: Api;
  onCompleted: () => void;
  /**
   * Onboarding is the first screen a signed-in account sees, so without this
   * the user is stuck: they cannot reach the profile screen to sign out and
   * cannot get back to the sign-in screen to use a different account.
   */
  onSignOut: () => void;
}) {
  const [nickname, setNickname] = useState('');
  const [birthdate, setBirthdate] = useState('');
  const [locations, setLocations] = useState<string[]>(['HOME']);
  const [equipment, setEquipment] = useState<string[]>(['BODYWEIGHT', 'MAT']);
  const [duration, setDuration] = useState(30);
  const [weeklyCount, setWeeklyCount] = useState(3);
  const [attentionAreas, setAttentionAreas] = useState<string[]>([]);
  const [sensitiveConsent, setSensitiveConsent] = useState(false);
  const [generalConsent, setGeneralConsent] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);

  const timezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul';
    } catch {
      return 'Asia/Seoul';
    }
  }, []);

  const submit = useAsyncAction(async () => {
    await api.submitOnboarding({
      nickname: nickname.trim(),
      date_of_birth: birthdate.trim(),
      primary_goal_code: PRIMARY_GOAL_CODE,
      experience_level_code: EXPERIENCE_LEVEL_CODE,
      timezone,
      preferred_location_code: locations[0] ?? 'HOME',
      available_location_codes: locations,
      default_requested_duration_minutes: duration,
      desired_weekly_workout_count: weeklyCount,
      equipment_codes: equipment,
      attention_area_codes: attentionAreas,
      preferred_exercise_type_codes: ['STRENGTH'],
      coaching_style_code: 'SUPPORTIVE',
      consents: {
        general_personal_data: generalConsent,
        sensitive_data: sensitiveConsent,
        wearable_integration: false,
        calendar_integration: false,
        marketing: false,
      },
    });
    onCompleted();
  });

  const onSubmit = useCallback(() => {
    setValidation(null);
    if (!nickname.trim()) {
      setValidation('닉네임을 입력해주세요.');
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(birthdate.trim())) {
      setValidation('생년월일을 YYYY-MM-DD 형식으로 입력해주세요.');
      return;
    }
    if (locations.length === 0) {
      setValidation('운동할 장소를 하나 이상 선택해주세요.');
      return;
    }
    if (equipment.length === 0) {
      setValidation('사용할 장비를 하나 이상 선택해주세요.');
      return;
    }
    if (!generalConsent || !sensitiveConsent) {
      setValidation('필수 동의 항목에 모두 동의해주세요.');
      return;
    }
    void submit.run();
  }, [
    birthdate,
    equipment.length,
    generalConsent,
    locations.length,
    nickname,
    sensitiveConsent,
    submit,
  ]);

  const blockedByAge =
    isApiError(submit.lastError) &&
    submit.lastError.code === 'AGE_REQUIREMENT_NOT_MET';

  return (
    <ScreenShell contentStyle={styles.content}>
      <ScreenHeading
        title="어떤 운동이 맞을지 알려주세요"
        subtitle="입력한 정보로 오늘의 루틴을 만들어요."
      />

      <Section title="기본 정보">
        <TextField
          label="닉네임"
          onChangeText={setNickname}
          placeholder="러너01"
          value={nickname}
        />
        <TextField
          label="생년월일"
          keyboardType="numbers-and-punctuation"
          onChangeText={setBirthdate}
          placeholder="1997-08-11"
          value={birthdate}
        />
        <Text style={styles.hint}>시간대: {timezone}</Text>
      </Section>

      <Section title="운동할 장소">
        <View style={styles.chipRow}>
          {LOCATIONS.map((option) => (
            <Chip
              key={option.code}
              label={option.label}
              selected={locations.includes(option.code)}
              onPress={() => setLocations((v) => toggle(v, option.code))}
            />
          ))}
        </View>
      </Section>

      <Section title="사용할 수 있는 장비">
        <View style={styles.chipRow}>
          {EQUIPMENT.map((option) => (
            <Chip
              key={option.code}
              label={option.label}
              selected={equipment.includes(option.code)}
              onPress={() => setEquipment((v) => toggle(v, option.code))}
            />
          ))}
        </View>
      </Section>

      <Section title="희망 운동 시간">
        <View style={styles.chipRow}>
          {DURATIONS.map((minutes) => (
            <Chip
              key={minutes}
              label={`${minutes}분`}
              selected={duration === minutes}
              onPress={() => setDuration(minutes)}
            />
          ))}
        </View>
      </Section>

      <Section title="주간 운동 횟수">
        <View style={styles.chipRow}>
          {WEEKLY_COUNTS.map((count) => (
            <Chip
              key={count}
              label={`주 ${count}회`}
              selected={weeklyCount === count}
              onPress={() => setWeeklyCount(count)}
            />
          ))}
        </View>
      </Section>

      <Section title="주의가 필요한 부위 (선택)">
        <View style={styles.chipRow}>
          {BODY_AREA_OPTIONS.map((option) => (
            <Chip
              key={option.code}
              label={option.label}
              selected={attentionAreas.includes(option.code)}
              onPress={() => setAttentionAreas((v) => toggle(v, option.code))}
            />
          ))}
        </View>
      </Section>

      <Section title="필수 동의">
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: generalConsent }}
          onPress={() => setGeneralConsent((v) => !v)}
          style={styles.consentRow}
        >
          <View
            style={[styles.checkbox, generalConsent && styles.checkboxOn]}
          />
          <Text style={styles.consentText}>
            개인정보 수집 및 이용에 동의합니다.
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: sensitiveConsent }}
          onPress={() => setSensitiveConsent((v) => !v)}
          style={styles.consentRow}
        >
          <View
            style={[styles.checkbox, sensitiveConsent && styles.checkboxOn]}
          />
          <Text style={styles.consentText}>
            건강 관련 민감정보 처리에 동의합니다.
          </Text>
        </Pressable>
      </Section>

      {validation ? <InlineFeedback tone="error" message={validation} /> : null}
      {submit.error && !blockedByAge ? (
        <InlineFeedback tone="error" message={submit.error} />
      ) : null}
      {blockedByAge ? (
        <InlineFeedback
          tone="error"
          message="만 14세 미만은 이용할 수 없습니다."
        />
      ) : null}

      <Button
        label={submit.pending ? '저장 중…' : '시작하기'}
        disabled={submit.pending || blockedByAge}
        onPress={onSubmit}
      />
      <Button
        label="다른 계정으로 로그인"
        tone="secondary"
        disabled={submit.pending}
        onPress={onSignOut}
      />
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: spacing.md,
    paddingTop: 40,
  },
  section: {
    gap: spacing.md,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  chipSelected: {
    borderColor: colors.green,
    backgroundColor: colors.greenTint,
  },
  chipLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  chipLabelSelected: {
    color: colors.greenText,
  },
  hint: {
    color: colors.textMuted,
    fontSize: 12,
  },
  consentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  checkbox: {
    width: 20,
    height: 20,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 6,
    backgroundColor: colors.surface,
  },
  checkboxOn: {
    borderColor: colors.green,
    backgroundColor: colors.green,
  },
  consentText: {
    flex: 1,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
});
