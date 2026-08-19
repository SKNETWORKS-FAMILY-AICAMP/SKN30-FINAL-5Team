/** API-backed, one-question-per-page onboarding flow. */
import { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import { BODY_AREA_OPTIONS } from '../../api/labels';
import type { SexCode } from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import {
  PROFILE_BODY_LIMITS,
  PROFILE_SEX_OPTIONS,
} from '../profile/profileModel';

const LOCATIONS = [
  { code: 'HOME', label: '집' },
  { code: 'GYM', label: '헬스장' },
] as const;
const EQUIPMENT = [
  { code: 'BODYWEIGHT', label: '맨몸' },
  { code: 'MAT', label: '매트' },
  { code: 'RESISTANCE_BAND', label: '밴드' },
] as const;
const DURATIONS = [20, 30, 40, 50] as const;
const WEEKLY_COUNTS = [2, 3, 4, 5] as const;

// The complete goal and experience code lists are not yet public API
// contracts. Keep these options to deployment-approved codes and extend them
// only when docs/API_CONTRACT.md defines the additional machine codes.
const GOAL_OPTIONS = [
  {
    code: 'GENERAL_FITNESS',
    label: '건강 유지',
    description: '꾸준히 움직이며 기초 체력을 만들고 싶어요.',
  },
] as const;
const EXPERIENCE_OPTIONS = [
  {
    code: 'BEGINNER',
    label: '입문·초급',
    description: '운동이 처음이거나 아직 정해진 루틴이 없어요.',
  },
] as const;
const EXERCISE_TYPE_OPTIONS = [
  { code: 'STRENGTH', label: '근력' },
  { code: 'CARDIO', label: '유산소' },
  { code: 'MOBILITY', label: '가동성' },
] as const;
const COACHING_STYLE_OPTIONS = [
  {
    code: 'SUPPORTIVE',
    label: '든든하게',
    description: '적당한 응원과 함께 차근차근 안내해요.',
  },
  {
    code: 'CONCISE',
    label: '간결하게',
    description: '핵심 정보와 기록을 짧고 명확하게 안내해요.',
  },
  {
    code: 'ENERGETIC',
    label: '활기차게',
    description: '밝고 힘찬 말투로 운동 흐름을 안내해요.',
  },
] as const;

export const ONBOARDING_STEPS = [
  {
    key: 'basic',
    title: '기본 정보를 알려주세요',
    intro: '앱에서 사용할 닉네임과 생년월일을 입력해주세요.',
    required: true,
  },
  {
    key: 'sex',
    title: '성별을 선택해주세요',
    intro: '운동 강도와 권장 범위를 조정하는 데 사용해요.',
    required: true,
  },
  {
    key: 'body',
    title: '키와 체중을 입력해주세요',
    intro: '맞춤 운동 강도와 예상 소모량을 계산하는 데 사용해요.',
    required: true,
  },
  {
    key: 'goal',
    title: '운동 목표는 무엇인가요?',
    intro: '현재 가장 가까운 목표를 선택해주세요.',
    required: true,
  },
  {
    key: 'experience',
    title: '운동 경험은 어느 정도인가요?',
    intro: '지금 수준에 맞는 루틴을 구성하는 데 사용해요.',
    required: true,
  },
  {
    key: 'exerciseType',
    title: '어떤 운동을 선호하나요?',
    intro:
      '좋아하는 운동 종류를 모두 선택할 수 있어요. 아직 없다면 넘어가도 돼요.',
    required: false,
  },
  {
    key: 'coachingStyle',
    title: '어떤 방식으로 안내해드릴까요?',
    intro: '선택하지 않으면 기본 안내 방식으로 시작해요.',
    required: false,
  },
  {
    key: 'location',
    title: '주로 어디에서 운동하나요?',
    intro: '여러 장소를 선택할 수 있어요.',
    required: true,
  },
  {
    key: 'equipment',
    title: '사용할 수 있는 장비가 있나요?',
    intro: '현재 사용할 수 있는 장비를 모두 골라주세요.',
    required: true,
  },
  {
    key: 'duration',
    title: '한 번에 몇 분 운동하고 싶나요?',
    intro: '기본 루틴의 운동 시간으로 사용해요.',
    required: true,
  },
  {
    key: 'frequency',
    title: '일주일에 몇 번 운동하고 싶나요?',
    intro: '희망하는 주간 운동 횟수를 선택해주세요.',
    required: true,
  },
  {
    key: 'attention',
    title: '주의가 필요한 부위가 있나요?',
    intro: '먼저 있음 또는 없음을 선택해주세요.',
    required: true,
  },
  {
    key: 'consent',
    title: '필수 항목에 동의해주세요',
    intro: '맞춤 운동 서비스를 제공하기 위해 필요한 동의예요.',
    required: true,
  },
] as const;

type Props = {
  api: Pick<Api, 'submitOnboarding'>;
  onCompleted: () => void;
  onSignOut: () => void;
  initialStep?: number;
  onStepChange?: (step: number) => void;
};

export function OnboardingScreen(props: Props) {
  const initialStep = clampStep(props.initialStep ?? 1);
  return (
    <OnboardingScreenContent
      key={initialStep}
      {...props}
      initialStep={initialStep}
    />
  );
}

function OnboardingScreenContent({
  api,
  initialStep = 1,
  onCompleted,
  onSignOut,
  onStepChange,
}: Props) {
  const [step, setStep] = useState(initialStep);
  const [nickname, setNickname] = useState('');
  const [birthdate, setBirthdate] = useState('');
  const [sexCode, setSexCode] = useState<SexCode | null>(null);
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [primaryGoalCode, setPrimaryGoalCode] = useState<
    (typeof GOAL_OPTIONS)[number]['code'] | null
  >(null);
  const [experienceLevelCode, setExperienceLevelCode] = useState<
    (typeof EXPERIENCE_OPTIONS)[number]['code'] | null
  >(null);
  const [preferredExerciseTypes, setPreferredExerciseTypes] = useState<
    (typeof EXERCISE_TYPE_OPTIONS)[number]['code'][]
  >([]);
  const [coachingStyleCode, setCoachingStyleCode] = useState<
    (typeof COACHING_STYLE_OPTIONS)[number]['code'] | null
  >(null);
  const [locations, setLocations] = useState<string[]>([]);
  const [equipment, setEquipment] = useState<string[]>([]);
  const [duration, setDuration] = useState(30);
  const [weeklyCount, setWeeklyCount] = useState(3);
  const [hasAttentionAreas, setHasAttentionAreas] = useState<boolean | null>(
    null,
  );
  const [attentionAreas, setAttentionAreas] = useState<string[]>([]);
  const [generalConsent, setGeneralConsent] = useState(false);
  const [sensitiveConsent, setSensitiveConsent] = useState(false);
  const current = ONBOARDING_STEPS[step - 1] ?? ONBOARDING_STEPS[0];
  const today = useMemo(() => new Date(), []);
  const birthdateError = getBirthdateError(birthdate, today);

  const timezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul';
    } catch {
      return 'Asia/Seoul';
    }
  }, []);

  const submit = useAsyncAction(async () => {
    const preferredLocationCode = locations[0];
    if (
      sexCode === null ||
      primaryGoalCode === null ||
      experienceLevelCode === null ||
      preferredLocationCode === undefined ||
      equipment.length === 0 ||
      hasAttentionAreas === null ||
      (hasAttentionAreas && attentionAreas.length === 0)
    ) {
      return;
    }
    try {
      await api.submitOnboarding({
        nickname: nickname.trim(),
        date_of_birth: birthdate.trim(),
        sex_code: sexCode,
        height_cm: Number(heightCm),
        weight_kg: Number(weightKg),
        primary_goal_code: primaryGoalCode,
        experience_level_code: experienceLevelCode,
        timezone,
        preferred_location_code: preferredLocationCode,
        available_location_codes: locations,
        default_requested_duration_minutes: duration,
        desired_weekly_workout_count: weeklyCount,
        equipment_codes: equipment,
        attention_area_codes: hasAttentionAreas ? attentionAreas : [],
        preferred_exercise_type_codes: preferredExerciseTypes,
        ...(coachingStyleCode === null
          ? {}
          : { coaching_style_code: coachingStyleCode }),
        consents: {
          general_personal_data: generalConsent,
          sensitive_data: sensitiveConsent,
          wearable_integration: false,
          calendar_integration: false,
          marketing: false,
        },
      });
    } catch (error) {
      const errorStep = onboardingErrorStep(error);
      if (errorStep !== null) {
        setStep(errorStep);
        onStepChange?.(errorStep);
      }
      throw error;
    }
    onCompleted();
  });

  const valid = isStepValid(current.key, {
    birthdate,
    birthdateError,
    coachingStyleCode,
    equipment,
    experienceLevelCode,
    generalConsent,
    hasAttentionAreas,
    heightCm,
    locations,
    nickname,
    attentionAreas,
    preferredExerciseTypes,
    primaryGoalCode,
    sensitiveConsent,
    sexCode,
    weightKg,
  });
  const blockedByAge =
    isApiError(submit.lastError) &&
    submit.lastError.code === 'AGE_REQUIREMENT_NOT_MET';

  const changeStep = (next: number) => {
    const bounded = clampStep(next);
    submit.clearError();
    setStep(bounded);
    onStepChange?.(bounded);
  };
  const goBack = () => (step === 1 ? onSignOut() : changeStep(step - 1));
  const goNext = () => {
    if (!valid || submit.pending) return;
    if (step === ONBOARDING_STEPS.length) void submit.run();
    else changeStep(step + 1);
  };

  const renderStep = () => {
    switch (current.key) {
      case 'basic':
        return (
          <Card style={styles.cardGroup}>
            <TextField
              accessibilityLabel="닉네임"
              label="닉네임"
              maxLength={64}
              onChangeText={(value) => {
                setNickname(value.slice(0, 64));
                submit.clearError();
              }}
              placeholder="앱에서 불릴 이름"
              style={styles.input}
              trailing={<Text style={styles.suffix}>{nickname.length}/64</Text>}
              value={nickname}
            />
            <TextField
              accessibilityLabel="생년월일"
              error={birthdate ? (birthdateError ?? undefined) : undefined}
              keyboardType="numbers-and-punctuation"
              label="생년월일"
              maxLength={10}
              onChangeText={(value) => {
                setBirthdate(value.slice(0, 10));
                submit.clearError();
              }}
              placeholder="예: 1997-08-11"
              style={styles.input}
              value={birthdate}
            />
            <Text style={styles.hint}>YYYY-MM-DD 형식 · 시간대 {timezone}</Text>
          </Card>
        );
      case 'sex':
        return (
          <ChoiceCard>
            {PROFILE_SEX_OPTIONS.map((option) => (
              <Chip
                key={option.code}
                grow
                label={option.label}
                selected={sexCode === option.code}
                onPress={() => setSexCode(option.code)}
              />
            ))}
          </ChoiceCard>
        );
      case 'body':
        return (
          <Card style={styles.cardGroup}>
            <View style={styles.bodyRow}>
              <TextField
                accessibilityLabel="키"
                containerStyle={styles.bodyField}
                inputMode="decimal"
                onChangeText={(value) => setHeightCm(onlyDecimal(value))}
                placeholder="170"
                style={styles.input}
                trailing={<Text style={styles.suffix}>cm</Text>}
                value={heightCm}
              />
              <TextField
                accessibilityLabel="체중"
                containerStyle={styles.bodyField}
                inputMode="decimal"
                onChangeText={(value) => setWeightKg(onlyDecimal(value))}
                placeholder="65"
                style={styles.input}
                trailing={<Text style={styles.suffix}>kg</Text>}
                value={weightKg}
              />
            </View>
            <Text style={styles.hint}>
              키 {PROFILE_BODY_LIMITS.heightCm.min}–
              {PROFILE_BODY_LIMITS.heightCm.max}cm · 체중{' '}
              {PROFILE_BODY_LIMITS.weightKg.min}–
              {PROFILE_BODY_LIMITS.weightKg.max}kg
            </Text>
          </Card>
        );
      case 'goal':
        return (
          <ChoiceCard>
            {GOAL_OPTIONS.map((item) => (
              <DescriptionOption
                key={item.code}
                description={item.description}
                label={item.label}
                selected={primaryGoalCode === item.code}
                onPress={() => {
                  setPrimaryGoalCode(item.code);
                  submit.clearError();
                }}
              />
            ))}
          </ChoiceCard>
        );
      case 'experience':
        return (
          <ChoiceCard>
            {EXPERIENCE_OPTIONS.map((item) => (
              <DescriptionOption
                key={item.code}
                description={item.description}
                label={item.label}
                selected={experienceLevelCode === item.code}
                onPress={() => {
                  setExperienceLevelCode(item.code);
                  submit.clearError();
                }}
              />
            ))}
          </ChoiceCard>
        );
      case 'exerciseType':
        return (
          <ChoiceCard>
            {EXERCISE_TYPE_OPTIONS.map((item) => (
              <Chip
                key={item.code}
                grow
                label={item.label}
                selected={preferredExerciseTypes.includes(item.code)}
                onPress={() => {
                  setPreferredExerciseTypes((values) =>
                    toggle(values, item.code),
                  );
                  submit.clearError();
                }}
              />
            ))}
          </ChoiceCard>
        );
      case 'coachingStyle':
        return (
          <ChoiceCard>
            {COACHING_STYLE_OPTIONS.map((item) => (
              <DescriptionOption
                key={item.code}
                description={item.description}
                label={item.label}
                selected={coachingStyleCode === item.code}
                onPress={() => {
                  setCoachingStyleCode(item.code);
                  submit.clearError();
                }}
              />
            ))}
          </ChoiceCard>
        );
      case 'location':
        return (
          <ChoiceCard>
            {LOCATIONS.map((item) => (
              <Chip
                key={item.code}
                grow
                label={item.label}
                selected={locations.includes(item.code)}
                onPress={() => setLocations((v) => toggle(v, item.code))}
              />
            ))}
          </ChoiceCard>
        );
      case 'equipment':
        return (
          <ChoiceCard>
            {EQUIPMENT.map((item) => (
              <Chip
                key={item.code}
                label={item.label}
                selected={equipment.includes(item.code)}
                onPress={() => setEquipment((v) => toggle(v, item.code))}
              />
            ))}
          </ChoiceCard>
        );
      case 'duration':
        return (
          <ChoiceCard>
            {DURATIONS.map((minutes) => (
              <Chip
                key={minutes}
                grow
                label={`${minutes}분`}
                selected={duration === minutes}
                onPress={() => setDuration(minutes)}
              />
            ))}
          </ChoiceCard>
        );
      case 'frequency':
        return (
          <ChoiceCard>
            {WEEKLY_COUNTS.map((count) => (
              <Chip
                key={count}
                grow
                label={`주 ${count}회`}
                selected={weeklyCount === count}
                onPress={() => setWeeklyCount(count)}
              />
            ))}
          </ChoiceCard>
        );
      case 'attention':
        return (
          <ChoiceCard>
            <Chip
              grow
              label="없어요"
              selected={hasAttentionAreas === false}
              onPress={() => {
                setHasAttentionAreas(false);
                setAttentionAreas([]);
                submit.clearError();
              }}
            />
            <Chip
              grow
              label="있어요"
              selected={hasAttentionAreas === true}
              onPress={() => {
                setHasAttentionAreas(true);
                submit.clearError();
              }}
            />
            {hasAttentionAreas === true
              ? BODY_AREA_OPTIONS.map((item) => (
                  <Chip
                    key={item.code}
                    label={item.label}
                    selected={attentionAreas.includes(item.code)}
                    onPress={() => {
                      setAttentionAreas((values) => toggle(values, item.code));
                      submit.clearError();
                    }}
                  />
                ))
              : null}
          </ChoiceCard>
        );
      case 'consent':
        return (
          <Card style={styles.cardGroup}>
            <ConsentRow
              checked={generalConsent}
              label="개인정보 수집 및 이용에 동의합니다."
              onPress={() => setGeneralConsent((v) => !v)}
            />
            <ConsentRow
              checked={sensitiveConsent}
              label="건강 관련 민감정보 처리에 동의합니다."
              onPress={() => setSensitiveConsent((v) => !v)}
            />
          </Card>
        );
    }
  };

  return (
    <SafeAreaView
      edges={['top', 'right', 'bottom', 'left']}
      style={styles.screen}
    >
      <StatusBar style="dark" />
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <Pressable
            accessibilityLabel="뒤로"
            accessibilityRole="button"
            onPress={goBack}
            style={styles.backButton}
          >
            <Text style={styles.backIcon}>‹</Text>
          </Pressable>
          <Text accessibilityRole="header" style={styles.headerTitle}>
            온보딩
          </Text>
          <Text style={styles.stepCounter}>
            {step} / {ONBOARDING_STEPS.length}
          </Text>
        </View>
        <View style={styles.progressTrack}>
          <View
            testID="onboarding-progress"
            style={[
              styles.progressFill,
              {
                width: `${Math.round((step / ONBOARDING_STEPS.length) * 100)}%`,
              },
            ]}
          />
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.contentContainer}
        keyboardShouldPersistTaps="handled"
        style={styles.content}
      >
        <View style={styles.stepHeading}>
          <View style={styles.titleRow}>
            <Text style={styles.stepTitle}>{current.title}</Text>
            <Text
              style={
                current.required ? styles.requiredBadge : styles.optionalBadge
              }
            >
              {current.required ? '필수' : '선택'}
            </Text>
          </View>
          <Text style={styles.stepIntro}>{current.intro}</Text>
        </View>
        {renderStep()}
        {submit.error && !blockedByAge ? (
          <InlineFeedback message={submit.error} tone="error" />
        ) : null}
        {blockedByAge ? (
          <InlineFeedback
            message="만 14세 미만은 이용할 수 없습니다."
            tone="error"
          />
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          disabled={submit.pending}
          label="이전"
          onPress={goBack}
          style={styles.previousButton}
          tone="secondary"
        />
        <Button
          disabled={!valid || submit.pending || blockedByAge}
          label={
            submit.pending
              ? '저장 중...'
              : !valid
                ? '입력이 필요해요'
                : step === ONBOARDING_STEPS.length
                  ? '시작하기'
                  : '다음'
          }
          leading={
            submit.pending ? (
              <ActivityIndicator color={colors.surface} size="small" />
            ) : undefined
          }
          onPress={goNext}
          style={styles.nextButton}
        />
      </View>
    </SafeAreaView>
  );
}

type FormState = {
  nickname: string;
  birthdate: string;
  birthdateError: string | null;
  sexCode: SexCode | null;
  heightCm: string;
  weightKg: string;
  primaryGoalCode: (typeof GOAL_OPTIONS)[number]['code'] | null;
  experienceLevelCode: (typeof EXPERIENCE_OPTIONS)[number]['code'] | null;
  preferredExerciseTypes: (typeof EXERCISE_TYPE_OPTIONS)[number]['code'][];
  coachingStyleCode: (typeof COACHING_STYLE_OPTIONS)[number]['code'] | null;
  locations: string[];
  equipment: string[];
  hasAttentionAreas: boolean | null;
  attentionAreas: string[];
  generalConsent: boolean;
  sensitiveConsent: boolean;
};

function isStepValid(
  key: (typeof ONBOARDING_STEPS)[number]['key'],
  form: FormState,
) {
  switch (key) {
    case 'basic':
      return (
        form.nickname.trim().length > 0 &&
        form.nickname.length <= 64 &&
        form.birthdate.trim().length > 0 &&
        form.birthdateError === null
      );
    case 'sex':
      return form.sexCode !== null;
    case 'body':
      return (
        isInRange(form.heightCm, PROFILE_BODY_LIMITS.heightCm) &&
        isInRange(form.weightKg, PROFILE_BODY_LIMITS.weightKg)
      );
    case 'goal':
      return form.primaryGoalCode !== null;
    case 'experience':
      return form.experienceLevelCode !== null;
    case 'exerciseType':
    case 'coachingStyle':
      return true;
    case 'location':
      return form.locations.length > 0;
    case 'equipment':
      return form.equipment.length > 0;
    case 'attention':
      return (
        form.hasAttentionAreas !== null &&
        (!form.hasAttentionAreas || form.attentionAreas.length > 0)
      );
    case 'consent':
      return form.generalConsent && form.sensitiveConsent;
    default:
      return true;
  }
}

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function Chip({
  grow = false,
  label,
  onPress,
  selected,
}: {
  grow?: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.chip,
        grow && styles.chipGrow,
        selected && styles.chipSelected,
      ]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

function DescriptionOption({
  description,
  label,
  onPress,
  selected,
}: {
  description: string;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.descriptionOption, selected && styles.chipSelected]}
    >
      <Text
        style={[styles.descriptionTitle, selected && styles.chipLabelSelected]}
      >
        {label}
      </Text>
      <Text
        style={[
          styles.descriptionText,
          selected && styles.descriptionTextSelected,
        ]}
      >
        {description}
      </Text>
    </Pressable>
  );
}

function ConsentRow({
  checked,
  label,
  onPress,
}: {
  checked: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={onPress}
      style={[styles.consentRow, checked && styles.consentRowSelected]}
    >
      <View style={[styles.checkbox, checked && styles.checkboxSelected]}>
        <Text style={[styles.checkmark, !checked && styles.checkmarkHidden]}>
          ✓
        </Text>
      </View>
      <Text style={styles.consentText}>{label}</Text>
    </Pressable>
  );
}

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function onlyDecimal(value: string) {
  const normalized = value.replace(/[^0-9.]/g, '');
  const [integer = '', ...fractions] = normalized.split('.');
  const fraction = fractions.join('').slice(0, 1);
  return `${integer.slice(0, 3)}${fractions.length > 0 ? `.${fraction}` : ''}`;
}

function isInRange(value: string, limits: { min: number; max: number }) {
  const number = Number(value);
  return (
    value.trim() !== '' &&
    Number.isFinite(number) &&
    number >= limits.min &&
    number <= limits.max
  );
}

function getBirthdateError(value: string, today: Date): string | null {
  const normalized = value.trim();
  if (!normalized) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return 'YYYY-MM-DD 형식으로 입력해주세요.';
  }

  const [yearText, monthText, dayText] = normalized.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const daysInMonth = monthDays(year, month);
  if (year < 1 || daysInMonth === 0 || day < 1 || day > daysInMonth) {
    return '달력에 있는 올바른 날짜를 입력해주세요.';
  }

  const birthNumber = year * 10_000 + month * 100 + day;
  const todayNumber =
    today.getFullYear() * 10_000 +
    (today.getMonth() + 1) * 100 +
    today.getDate();
  if (birthNumber > todayNumber) {
    return '미래 날짜는 입력할 수 없어요.';
  }

  return null;
}

function monthDays(year: number, month: number): number {
  if (month < 1 || month > 12) return 0;
  if (month === 2) {
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return leap ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function onboardingErrorStep(error: unknown): number | null {
  if (!isApiError(error)) return null;
  if (
    [
      'AGE_REQUIREMENT_NOT_MET',
      'INVALID_DATE_OF_BIRTH',
      'INVALID_TIMEZONE',
    ].includes(error.code)
  ) {
    return stepNumber('basic');
  }
  if (error.code === 'REQUIRED_CONSENT_MISSING') {
    return stepNumber('consent');
  }

  const fieldToStep: Record<string, (typeof ONBOARDING_STEPS)[number]['key']> =
    {
      nickname: 'basic',
      date_of_birth: 'basic',
      sex_code: 'sex',
      height_cm: 'body',
      weight_kg: 'body',
      primary_goal_code: 'goal',
      experience_level_code: 'experience',
      preferred_exercise_type_codes: 'exerciseType',
      coaching_style_code: 'coachingStyle',
      preferred_location_code: 'location',
      available_location_codes: 'location',
      equipment_codes: 'equipment',
      default_requested_duration_minutes: 'duration',
      desired_weekly_workout_count: 'frequency',
      attention_area_codes: 'attention',
      consents: 'consent',
    };
  for (const detail of error.details) {
    const field = detail.field?.split('.').at(-1);
    if (field && fieldToStep[field]) return stepNumber(fieldToStep[field]);
    if (detail.field?.includes('consents')) return stepNumber('consent');
  }
  return null;
}

function stepNumber(key: (typeof ONBOARDING_STEPS)[number]['key']) {
  return ONBOARDING_STEPS.findIndex((step) => step.key === key) + 1;
}

function clampStep(step: number) {
  return Math.max(1, Math.min(ONBOARDING_STEPS.length, Math.round(step)));
}

const styles = StyleSheet.create({
  screen: { flex: 1, overflow: 'hidden', backgroundColor: colors.canvas },
  header: {
    gap: spacing.md,
    paddingTop: spacing.xl,
    paddingHorizontal: 20,
    paddingBottom: spacing.md,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  backButton: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 17,
    backgroundColor: colors.surface,
  },
  backIcon: { color: colors.text, fontSize: 30, lineHeight: 32 },
  headerTitle: { flex: 1, color: colors.text, fontSize: 17, fontWeight: '700' },
  stepCounter: { color: colors.textMuted, fontSize: 13, fontWeight: '700' },
  progressTrack: {
    height: 4,
    overflow: 'hidden',
    borderRadius: 2,
    backgroundColor: colors.border,
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  content: { flex: 1 },
  contentContainer: {
    gap: 14,
    paddingTop: spacing.sm,
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  stepHeading: { gap: 6 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  stepTitle: {
    flexShrink: 1,
    color: colors.text,
    fontSize: 22,
    fontWeight: '700',
    lineHeight: 29,
  },
  stepIntro: { color: colors.textMuted, fontSize: 13, lineHeight: 20 },
  requiredBadge: {
    flexShrink: 0,
    borderRadius: 6,
    backgroundColor: colors.fieldError,
    color: colors.surface,
    fontSize: 11,
    fontWeight: '700',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  optionalBadge: {
    flexShrink: 0,
    borderRadius: 6,
    backgroundColor: '#EFEBE3',
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  cardGroup: { gap: 14 },
  input: { backgroundColor: colors.canvas },
  bodyRow: { flexDirection: 'row', gap: 10 },
  bodyField: { minWidth: 0, flex: 1 },
  suffix: { color: colors.textMuted, fontSize: 13 },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  choiceCard: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  chipGrow: { minWidth: 72, flexGrow: 1, alignItems: 'center' },
  chipSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  chipLabel: { color: colors.text, fontSize: 14, fontWeight: '600' },
  chipLabelSelected: { color: colors.surface },
  descriptionOption: {
    width: '100%',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    padding: 14,
  },
  descriptionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  descriptionText: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  descriptionTextSelected: {
    color: 'rgba(255, 255, 255, 0.75)',
  },
  consentRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    padding: 14,
  },
  consentRowSelected: { borderColor: colors.primary },
  checkbox: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 6,
    backgroundColor: colors.surface,
  },
  checkboxSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  checkmark: { color: colors.surface, fontSize: 12, fontWeight: '700' },
  checkmarkHidden: { color: 'transparent' },
  consentText: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  footer: {
    flexDirection: 'row',
    gap: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 14,
    paddingHorizontal: 20,
    paddingBottom: 44,
  },
  previousButton: { width: 96, minHeight: 52, borderRadius: radii.card },
  nextButton: { minHeight: 52, flex: 1, borderRadius: radii.card },
});
