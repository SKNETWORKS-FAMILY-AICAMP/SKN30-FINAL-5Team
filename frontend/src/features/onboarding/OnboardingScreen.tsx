/** API-backed, one-question-per-page onboarding flow. */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
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
import {
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
} from '../../api/labels';
import type { DiscomfortSeverityCode, SexCode } from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { useScale } from '../../components/scale';
import { colors, radii, spacing } from '../../components/theme';
import { PROFILE_BODY_LIMITS } from '../profile/profileModel';
import {
  ONBOARDING_DURATION,
  ONBOARDING_EQUIPMENT_OPTIONS,
  ONBOARDING_EXERCISE_TYPE_OPTIONS,
  ONBOARDING_EXPERIENCE_OPTIONS,
  ONBOARDING_GOAL_OPTIONS,
  ONBOARDING_LOCATION_OPTIONS,
  ONBOARDING_WEEKLY_COUNT,
} from './onboardingOptions';

const MINIMUM_AGE = 14;
const MIN_BIRTH_YEAR = 1900;
const WHEEL_ITEM_HEIGHT = 44;
const WEB_WHEEL_GESTURE_IDLE_MS = 45;
const WEB_WHEEL_SINGLE_ITEM_DELTA = 240;
const WEB_WHEEL_ACCELERATION_DELTA = 70;
const WEB_WHEEL_MAX_ITEMS_PER_GESTURE = 18;

const SEX_OPTIONS = [
  { code: 'FEMALE', label: '여성' },
  { code: 'MALE', label: '남성' },
] as const satisfies readonly { code: SexCode; label: string }[];

const PAIN_SEVERITY_OPTIONS = [
  { code: 'MILD', label: '조금 아픔' },
  { code: 'MODERATE', label: '중간 정도 아픔' },
  { code: 'SEVERE', label: '많이 아픔' },
] as const satisfies readonly {
  code: DiscomfortSeverityCode;
  label: string;
}[];
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
  const today = useMemo(() => new Date(), []);
  const latestEligibleBirthdate = useMemo(
    () => getLatestEligibleBirthdate(today),
    [today],
  );
  const [birthYear, setBirthYear] = useState(() =>
    latestEligibleBirthdate.getFullYear(),
  );
  const [birthMonth, setBirthMonth] = useState(
    () => latestEligibleBirthdate.getMonth() + 1,
  );
  const [birthDay, setBirthDay] = useState(() =>
    latestEligibleBirthdate.getDate(),
  );
  const [sexCode, setSexCode] = useState<SexCode | null>(null);
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [primaryGoalCode, setPrimaryGoalCode] = useState<
    (typeof ONBOARDING_GOAL_OPTIONS)[number]['code'] | null
  >(null);
  const [experienceLevelCode, setExperienceLevelCode] = useState<
    (typeof ONBOARDING_EXPERIENCE_OPTIONS)[number]['code'] | null
  >(null);
  const [preferredExerciseTypes, setPreferredExerciseTypes] = useState<
    (typeof ONBOARDING_EXERCISE_TYPE_OPTIONS)[number]['code'][]
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
  const [showExtendedAttentionAreas, setShowExtendedAttentionAreas] =
    useState(false);
  const [attentionSeverities, setAttentionSeverities] = useState<
    Partial<Record<string, DiscomfortSeverityCode>>
  >({});
  const [generalConsent, setGeneralConsent] = useState(false);
  const [sensitiveConsent, setSensitiveConsent] = useState(false);
  const current = ONBOARDING_STEPS[step - 1] ?? ONBOARDING_STEPS[0];
  const birthdate = toIsoDate(birthYear, birthMonth, birthDay);
  const birthYears = useMemo(
    () =>
      numberRange(
        MIN_BIRTH_YEAR,
        latestEligibleBirthdate.getFullYear(),
      ).reverse(),
    [latestEligibleBirthdate],
  );
  const birthMonths = useMemo(() => {
    const lastMonth =
      birthYear === latestEligibleBirthdate.getFullYear()
        ? latestEligibleBirthdate.getMonth() + 1
        : 12;
    return numberRange(1, lastMonth);
  }, [birthYear, latestEligibleBirthdate]);
  const birthDays = useMemo(() => {
    const lastDay =
      birthYear === latestEligibleBirthdate.getFullYear() &&
      birthMonth === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(birthYear, birthMonth);
    return numberRange(1, lastDay);
  }, [birthMonth, birthYear, latestEligibleBirthdate]);

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
    coachingStyleCode,
    equipment,
    experienceLevelCode,
    generalConsent,
    hasAttentionAreas,
    heightCm,
    locations,
    nickname,
    attentionAreas,
    attentionSeverities,
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

  const changeBirthYear = (value: number) => {
    const latestYear = latestEligibleBirthdate.getFullYear();
    const nextMonth = Math.min(
      birthMonth,
      value === latestYear ? latestEligibleBirthdate.getMonth() + 1 : 12,
    );
    const nextMaximumDay =
      value === latestYear &&
      nextMonth === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(value, nextMonth);
    setBirthYear(value);
    setBirthMonth(nextMonth);
    setBirthDay((currentDay) => Math.min(currentDay, nextMaximumDay));
    submit.clearError();
  };
  const changeBirthMonth = (value: number) => {
    const maximumDay =
      birthYear === latestEligibleBirthdate.getFullYear() &&
      value === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(birthYear, value);
    setBirthMonth(value);
    setBirthDay((currentDay) => Math.min(currentDay, maximumDay));
    submit.clearError();
  };
  const changeBirthDay = (value: number) => {
    setBirthDay(value);
    submit.clearError();
  };

  const toggleAttentionArea = (code: string) => {
    setAttentionAreas((values) => {
      if (!values.includes(code)) return [...values, code];
      setAttentionSeverities((currentValues) => {
        const next = { ...currentValues };
        delete next[code];
        return next;
      });
      return values.filter((item) => item !== code);
    });
    submit.clearError();
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
            <View
              accessibilityLabel="생년월일 선택"
              style={styles.birthdateBlock}
            >
              <Text style={styles.fieldLabel}>생년월일</Text>
              <View style={styles.wheelRow}>
                <WheelColumn
                  label="연도"
                  options={birthYears}
                  selected={birthYear}
                  suffix="년"
                  onChange={changeBirthYear}
                />
                <WheelColumn
                  label="월"
                  options={birthMonths}
                  selected={birthMonth}
                  suffix="월"
                  onChange={changeBirthMonth}
                />
                <WheelColumn
                  label="일"
                  options={birthDays}
                  selected={birthDay}
                  suffix="일"
                  onChange={changeBirthDay}
                />
              </View>
              <Text style={styles.hint}>
                만 {MINIMUM_AGE}세 이상만 선택할 수 있어요. 선택 가능한 최근
                날짜는 {formatDate(latestEligibleBirthdate)}예요.
              </Text>
            </View>
          </Card>
        );
      case 'sex':
        return (
          <ChoiceCard>
            {SEX_OPTIONS.map((option) => (
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
            {ONBOARDING_GOAL_OPTIONS.map((item) => (
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
            {ONBOARDING_EXPERIENCE_OPTIONS.map((item) => (
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
            {ONBOARDING_EXERCISE_TYPE_OPTIONS.map((item) => (
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
            {ONBOARDING_LOCATION_OPTIONS.map((item) => (
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
            {ONBOARDING_EQUIPMENT_OPTIONS.map((item) => (
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
          <StepCounter
            decreaseLabel="운동 시간 10분 줄이기"
            increaseLabel="운동 시간 10분 늘리기"
            max={ONBOARDING_DURATION.max}
            min={ONBOARDING_DURATION.min}
            suffix="분"
            value={duration}
            onChange={setDuration}
            step={ONBOARDING_DURATION.step}
          />
        );
      case 'frequency':
        return (
          <StepCounter
            decreaseLabel="주간 운동 횟수 1회 줄이기"
            increaseLabel="주간 운동 횟수 1회 늘리기"
            max={ONBOARDING_WEEKLY_COUNT.max}
            min={ONBOARDING_WEEKLY_COUNT.min}
            prefix="주 "
            suffix="회"
            value={weeklyCount}
            onChange={setWeeklyCount}
          />
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
                setAttentionSeverities({});
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
            {hasAttentionAreas === true ? (
              <View style={styles.painDetails}>
                <View style={styles.painSection}>
                  <Text style={styles.painSectionTitle}>통증 부위</Text>
                  <View style={styles.painChoices}>
                    {DEFAULT_BODY_AREA_OPTIONS.map((item) => (
                      <Chip
                        key={item.code}
                        label={item.label}
                        selected={attentionAreas.includes(item.code)}
                        onPress={() => toggleAttentionArea(item.code)}
                      />
                    ))}
                    <Chip
                      label={
                        showExtendedAttentionAreas
                          ? '다른 부위 접기'
                          : '다른 부위 더 보기'
                      }
                      selected={showExtendedAttentionAreas}
                      onPress={() =>
                        setShowExtendedAttentionAreas((visible) => !visible)
                      }
                    />
                    {showExtendedAttentionAreas
                      ? EXTENDED_BODY_AREA_OPTIONS.map((item) => (
                          <Chip
                            key={item.code}
                            label={item.label}
                            selected={attentionAreas.includes(item.code)}
                            onPress={() => toggleAttentionArea(item.code)}
                          />
                        ))
                      : null}
                  </View>
                </View>
                {attentionAreas.map((code) => {
                  return (
                    <View key={code} style={styles.painSection}>
                      <Text style={styles.painSectionTitle}>
                        {bodyAreaLabel(code)} 통증 정도
                      </Text>
                      <View
                        style={styles.painSeverityChoices}
                        testID={`onboarding-pain-severity-options-${code}`}
                      >
                        {PAIN_SEVERITY_OPTIONS.map((severity) => (
                          <Chip
                            compact
                            key={severity.code}
                            label={severity.label}
                            selected={
                              attentionSeverities[code] === severity.code
                            }
                            onPress={() => {
                              setAttentionSeverities((values) => ({
                                ...values,
                                [code]: severity.code,
                              }));
                              submit.clearError();
                            }}
                          />
                        ))}
                      </View>
                    </View>
                  );
                })}
                {attentionAreas.length > 0 ? (
                  <Text style={styles.hint}>
                    통증 정도는 온보딩 중 확인용이며, 현재 서버에는 부위만
                    저장돼요.
                  </Text>
                ) : null}
              </View>
            ) : null}
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
  sexCode: SexCode | null;
  heightCm: string;
  weightKg: string;
  primaryGoalCode: (typeof ONBOARDING_GOAL_OPTIONS)[number]['code'] | null;
  experienceLevelCode:
    (typeof ONBOARDING_EXPERIENCE_OPTIONS)[number]['code'] | null;
  preferredExerciseTypes: (typeof ONBOARDING_EXERCISE_TYPE_OPTIONS)[number]['code'][];
  coachingStyleCode: (typeof COACHING_STYLE_OPTIONS)[number]['code'] | null;
  locations: string[];
  equipment: string[];
  hasAttentionAreas: boolean | null;
  attentionAreas: string[];
  attentionSeverities: Partial<Record<string, DiscomfortSeverityCode>>;
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
        form.birthdate.length > 0
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
        (!form.hasAttentionAreas ||
          (form.attentionAreas.length > 0 &&
            form.attentionAreas.every(
              (code) => form.attentionSeverities[code] !== undefined,
            )))
      );
    case 'consent':
      return form.generalConsent && form.sensitiveConsent;
    default:
      return true;
  }
}

function WheelColumn({
  label,
  onChange,
  options,
  selected,
  suffix,
}: {
  label: string;
  onChange: (value: number) => void;
  options: number[];
  selected: number;
  suffix: string;
}) {
  const scrollRef = useRef<ScrollView>(null);
  const selectedIndex = Math.max(0, options.indexOf(selected));
  const currentIndexRef = useRef(selectedIndex);
  const pendingInternalSelectionRef = useRef<number | null>(null);
  const webSettleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const webWheelGestureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const webWheelDeltaRef = useRef(0);
  const draggingRef = useRef(false);

  const clearWebSettleTimer = () => {
    if (webSettleTimerRef.current !== null) {
      clearTimeout(webSettleTimerRef.current);
      webSettleTimerRef.current = null;
    }
  };

  const clearWebWheelGestureTimer = () => {
    if (webWheelGestureTimerRef.current !== null) {
      clearTimeout(webWheelGestureTimerRef.current);
      webWheelGestureTimerRef.current = null;
    }
  };

  const scrollToIndex = (index: number, animated: boolean) => {
    scrollRef.current?.scrollTo({
      animated,
      y: index * WHEEL_ITEM_HEIGHT,
    });
  };

  const commitIndex = (index: number) => {
    const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
    const value = options[boundedIndex];
    if (value === undefined) return;
    currentIndexRef.current = boundedIndex;
    if (value !== selected) {
      pendingInternalSelectionRef.current = value;
      onChange(value);
    }
  };

  const selectIndex = (index: number, animated = true) => {
    const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
    scrollToIndex(boundedIndex, animated);
    commitIndex(boundedIndex);
  };

  const settleAtOffset = (offsetY: number, align = true) => {
    const index = Math.max(
      0,
      Math.min(options.length - 1, Math.round(offsetY / WHEEL_ITEM_HEIGHT)),
    );
    const targetOffset = index * WHEEL_ITEM_HEIGHT;
    if (align && Math.abs(offsetY - targetOffset) > 1) {
      scrollToIndex(index, true);
    }
    commitIndex(index);
  };

  useEffect(() => {
    currentIndexRef.current = selectedIndex;
    // Let a tap or scroll finish its animation; hard-align only external changes.
    if (pendingInternalSelectionRef.current === selected) {
      pendingInternalSelectionRef.current = null;
      return;
    }
    pendingInternalSelectionRef.current = null;
    scrollToIndex(selectedIndex, false);
  }, [options, selected, selectedIndex]);

  useEffect(
    () => () => {
      clearWebSettleTimer();
      clearWebWheelGestureTimer();
    },
    [],
  );

  const settleFromScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    clearWebSettleTimer();
    draggingRef.current = false;
    // Momentum and snapToInterval already performed the final alignment.
    settleAtOffset(event.nativeEvent.contentOffset.y, false);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (Platform.OS !== 'web' || draggingRef.current) return;
    const offsetY = event.nativeEvent.contentOffset.y;
    clearWebSettleTimer();
    webSettleTimerRef.current = setTimeout(() => {
      settleAtOffset(offsetY);
      webSettleTimerRef.current = null;
    }, 90);
  };

  const handleWheel = (
    event: NativeSyntheticEvent<{
      deltaMode?: number;
      deltaY: number;
    }>,
  ) => {
    event.preventDefault();
    queueWheelDelta(event.nativeEvent.deltaY, event.nativeEvent.deltaMode);
  };

  // Recreate this handler with the current options and selection, then rebind it below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const queueWheelDelta = (deltaY: number, deltaMode = 0) => {
    clearWebSettleTimer();
    if (deltaY === 0) return;
    const modeMultiplier =
      deltaMode === 1 ? 16 : deltaMode === 2 ? WHEEL_ITEM_HEIGHT * 3 : 1;
    const normalizedDelta = deltaY * modeMultiplier;
    if (
      webWheelDeltaRef.current !== 0 &&
      Math.sign(webWheelDeltaRef.current) !== Math.sign(normalizedDelta)
    ) {
      webWheelDeltaRef.current = 0;
    }
    webWheelDeltaRef.current += normalizedDelta;
    clearWebWheelGestureTimer();
    webWheelGestureTimerRef.current = setTimeout(() => {
      const accumulatedDelta = webWheelDeltaRef.current;
      webWheelDeltaRef.current = 0;
      webWheelGestureTimerRef.current = null;
      const magnitude = Math.abs(accumulatedDelta);
      const steps =
        magnitude <= WEB_WHEEL_SINGLE_ITEM_DELTA
          ? 1
          : Math.min(
              WEB_WHEEL_MAX_ITEMS_PER_GESTURE,
              1 +
                Math.round(
                  (magnitude - WEB_WHEEL_SINGLE_ITEM_DELTA) /
                    WEB_WHEEL_ACCELERATION_DELTA,
                ),
            );
      selectIndex(
        currentIndexRef.current + Math.sign(accumulatedDelta) * steps,
      );
    }, WEB_WHEEL_GESTURE_IDLE_MS);
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || scrollRef.current === null) return;

    const scrollNode = scrollRef.current.getScrollableNode?.() as
      HTMLElement | undefined;
    if (scrollNode?.addEventListener === undefined) return;

    const preventNativeWheelScroll = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      queueWheelDelta(event.deltaY, event.deltaMode);
    };

    scrollNode.addEventListener('wheel', preventNativeWheelScroll, {
      passive: false,
    });
    return () => {
      scrollNode.removeEventListener('wheel', preventNativeWheelScroll);
    };
  }, [queueWheelDelta]);

  const webWheelProps =
    Platform.OS === 'web' ? { onWheel: handleWheel } : undefined;

  return (
    <View style={styles.wheelColumn}>
      <Text style={styles.wheelLabel}>{label}</Text>
      <View style={styles.wheelViewport}>
        <View pointerEvents="none" style={styles.wheelSelection} />
        <ScrollView
          ref={scrollRef}
          accessibilityLabel={`${label} 선택 스크롤`}
          decelerationRate="fast"
          disableIntervalMomentum
          nestedScrollEnabled
          onMomentumScrollBegin={() => {
            draggingRef.current = true;
            clearWebSettleTimer();
          }}
          onMomentumScrollEnd={settleFromScroll}
          onScroll={handleScroll}
          onScrollBeginDrag={() => {
            draggingRef.current = true;
            clearWebSettleTimer();
          }}
          onScrollEndDrag={(event) => {
            draggingRef.current = false;
            const velocity = event.nativeEvent.velocity?.y;
            if (velocity !== undefined && Math.abs(velocity) < 0.1) {
              settleFromScroll(event);
              return;
            }
            const offsetY = event.nativeEvent.contentOffset.y;
            clearWebSettleTimer();
            webSettleTimerRef.current = setTimeout(() => {
              settleAtOffset(offsetY);
              webSettleTimerRef.current = null;
            }, 120);
          }}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
          snapToAlignment="start"
          snapToInterval={WHEEL_ITEM_HEIGHT}
          style={styles.wheelScroll}
          contentContainerStyle={styles.wheelContent}
          {...webWheelProps}
        >
          {options.map((value, index) => {
            const selectedOption = selected === value;
            const optionLabel = `${value}${suffix}`;
            return (
              <Pressable
                accessibilityLabel={`${label} ${optionLabel}`}
                accessibilityRole="button"
                accessibilityState={{ selected: selectedOption }}
                key={value}
                onPress={() => {
                  selectIndex(index);
                }}
                style={styles.wheelItem}
              >
                <Text
                  style={[
                    styles.wheelItemText,
                    selectedOption && styles.wheelItemTextSelected,
                  ]}
                >
                  {optionLabel}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

function StepCounter({
  decreaseLabel,
  increaseLabel,
  max,
  min,
  onChange,
  prefix = '',
  step = 1,
  suffix,
  value,
}: {
  decreaseLabel: string;
  increaseLabel: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  prefix?: string;
  step?: number;
  suffix: string;
  value: number;
}) {
  const canDecrease = value > min;
  const canIncrease = value < max;
  return (
    <Card style={styles.counterCard}>
      <Pressable
        accessibilityLabel={decreaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canDecrease }}
        disabled={!canDecrease}
        onPress={() => onChange(Math.max(min, value - step))}
        style={[
          styles.counterButton,
          !canDecrease && styles.counterButtonDisabled,
        ]}
      >
        <Text style={styles.counterButtonText}>−</Text>
      </Pressable>
      <Text accessibilityLiveRegion="polite" style={styles.counterValue}>
        {prefix}
        {value}
        {suffix}
      </Text>
      <Pressable
        accessibilityLabel={increaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canIncrease }}
        disabled={!canIncrease}
        onPress={() => onChange(Math.min(max, value + step))}
        style={[
          styles.counterButton,
          !canIncrease && styles.counterButtonDisabled,
        ]}
      >
        <Text style={styles.counterButtonText}>+</Text>
      </Pressable>
    </Card>
  );
}

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function Chip({
  compact = false,
  grow = false,
  label,
  onPress,
  selected,
}: {
  compact?: boolean;
  grow?: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  const { f } = useScale();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.chip,
        grow && styles.chipGrow,
        compact && styles.chipCompact,
        selected && styles.chipSelected,
      ]}
    >
      <Text
        numberOfLines={compact ? 1 : undefined}
        style={[
          styles.chipLabel,
          compact && styles.chipCompactLabel,
          compact && { fontSize: Math.max(10, f(11)) },
          selected && styles.chipLabelSelected,
        ]}
      >
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

function getLatestEligibleBirthdate(today: Date) {
  const eligibleYear = today.getFullYear() - MINIMUM_AGE;
  const lastDay = monthDays(eligibleYear, today.getMonth() + 1);
  return new Date(
    eligibleYear,
    today.getMonth(),
    Math.min(today.getDate(), lastDay),
  );
}

function toIsoDate(
  year: number | null,
  month: number | null,
  day: number | null,
) {
  if (year === null || month === null || day === null) return '';
  return `${year.toString().padStart(4, '0')}-${month
    .toString()
    .padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
}

function formatDate(value: Date) {
  return toIsoDate(value.getFullYear(), value.getMonth() + 1, value.getDate());
}

function numberRange(start: number, end: number) {
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) =>
    Number(start + index),
  );
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
  birthdateBlock: { gap: spacing.sm },
  fieldLabel: { color: colors.text, fontSize: 13, fontWeight: '700' },
  wheelRow: { flexDirection: 'row', gap: spacing.sm },
  wheelColumn: { minWidth: 0, flex: 1, gap: 5 },
  wheelDisabled: { opacity: 0.45 },
  wheelLabel: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
  },
  wheelViewport: {
    height: WHEEL_ITEM_HEIGHT * 3,
    overflow: 'hidden',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
  },
  wheelScroll: { zIndex: 1 },
  wheelContent: { paddingVertical: WHEEL_ITEM_HEIGHT },
  wheelSelection: {
    position: 'absolute',
    top: WHEEL_ITEM_HEIGHT,
    right: 5,
    left: 5,
    height: WHEEL_ITEM_HEIGHT,
    borderRadius: 9,
    backgroundColor: '#E8F2E4',
  },
  wheelItem: {
    height: WHEEL_ITEM_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wheelItemText: { color: colors.textMuted, fontSize: 16 },
  wheelItemTextSelected: {
    color: colors.primary,
    fontWeight: '800',
  },
  bodyRow: { flexDirection: 'row', gap: 10 },
  bodyField: { minWidth: 0, flex: 1 },
  suffix: { color: colors.textMuted, fontSize: 13 },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  choiceCard: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  counterCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.lg,
  },
  counterButton: {
    width: 56,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.primary,
    borderRadius: 28,
    backgroundColor: colors.surface,
  },
  counterButtonDisabled: { borderColor: colors.border, opacity: 0.4 },
  counterButtonText: {
    color: colors.primary,
    fontSize: 30,
    fontWeight: '500',
    lineHeight: 34,
  },
  counterValue: {
    minWidth: 100,
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  chipGrow: { minWidth: 72, flexGrow: 1, alignItems: 'center' },
  chipCompact: {
    minWidth: 0,
    flexGrow: 1,
    flexShrink: 0,
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  chipCompactLabel: { letterSpacing: -0.4 },
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
  painDetails: { width: '100%', gap: spacing.md },
  painSection: {
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  painSectionTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  painChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  painSeverityChoices: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: spacing.xs,
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
