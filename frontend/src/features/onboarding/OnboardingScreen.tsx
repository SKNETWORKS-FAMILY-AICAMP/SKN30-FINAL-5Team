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
import {
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
} from '../../api/labels';
import type { SexCode } from '../../api/types';
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
  ONBOARDING_EXPERIENCE_OPTIONS,
  ONBOARDING_GOAL_OPTIONS,
  ONBOARDING_LOCATION_OPTIONS,
  ONBOARDING_WEEKLY_COUNT,
} from './onboardingOptions';
import { BirthDateField, latestEligibleBirthdateIso } from './BirthDateField';

const SEX_OPTIONS = [
  { code: 'FEMALE', label: '여성' },
  { code: 'MALE', label: '남성' },
] as const satisfies readonly { code: SexCode; label: string }[];

const PAIN_INTENSITY_MIN = 1;
const PAIN_INTENSITY_MAX = 10;
const COACHING_STYLE_OPTIONS = [
  {
    code: 'SUPPORTIVE',
    label: '차근차근',
    description: '응원과 함께 편안하게 운동을 안내해요.',
  },
  {
    code: 'CONCISE',
    label: '딱 필요한 만큼',
    description: '꼭 필요한 내용만 간단하게 알려드려요.',
  },
  {
    code: 'ENERGETIC',
    label: '힘차게',
    description: '밝고 에너지 넘치게 운동을 함께해요.',
  },
] as const;

const CONSENT_OPTIONS = {
  general_personal_data: {
    label: '개인정보 수집 및 이용',
    description: '입력한 정보를 운동 계획을 만드는 데 활용해요.',
  },
  sensitive_data: {
    label: '건강 관련 민감정보 처리',
    description: '통증과 컨디션 정보를 안전한 운동 계획을 만드는 데 활용해요.',
  },
  wearable_integration: {
    label: '웨어러블 연동',
    description: '웨어러블 데이터를 운동 계획에 참고해요.',
  },
  marketing: {
    label: '마케팅 정보 수신',
    description: '새로운 기능과 이벤트 소식을 받아볼 수 있어요.',
  },
} as const;

export const ONBOARDING_STEPS = [
  {
    key: 'basic',
    title: '기본 정보를 알려주세요',
    intro: '',
    required: true,
  },
  {
    key: 'sex',
    title: '성별을 선택해주세요',
    intro: '',
    required: true,
  },
  {
    key: 'body',
    title: '키와 체중을 입력해주세요',
    intro: '',
    required: true,
  },
  {
    key: 'goal',
    title: '운동 목표는 무엇인가요?',
    intro: '',
    required: true,
  },
  {
    key: 'experience',
    title: '운동 경험은 어느 정도인가요?',
    intro: '',
    required: true,
  },
  {
    key: 'coachingStyle',
    title: '운동할 때 어떻게 도와드릴까요?',
    intro: '원하는 안내 스타일을 골라주세요. 언제든 바꿀 수 있어요.',
    required: false,
  },
  {
    key: 'location',
    title: '어디에서 운동할 예정인가요?',
    intro: '운동할 수 있는 장소를 모두 선택해주세요.',
    required: true,
  },
  {
    key: 'duration',
    title: '한 번에 얼마나 운동할까요?',
    intro: '선택한 시간에 맞춰 운동 계획을 만들어드려요.',
    required: true,
  },
  {
    key: 'frequency',
    title: '일주일에 몇 번 운동할까요?',
    intro: '선택한 횟수에 맞춰 운동 계획을 만들어드려요.',
    required: true,
  },
  {
    key: 'attention',
    title: '평소에 통증 부위가 있나요?',
    intro: '',
    required: true,
  },
  {
    key: 'consent',
    title: '동의 항목을 확인해주세요',
    intro: '',
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
  const [birthdate, setBirthdate] = useState(latestEligibleBirthdateIso);
  const [sexCode, setSexCode] = useState<SexCode | null>(null);
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [primaryGoalCode, setPrimaryGoalCode] = useState<
    (typeof ONBOARDING_GOAL_OPTIONS)[number]['code'] | null
  >(null);
  const [experienceLevelCode, setExperienceLevelCode] = useState<
    (typeof ONBOARDING_EXPERIENCE_OPTIONS)[number]['code']
  >(ONBOARDING_EXPERIENCE_OPTIONS[0].code);
  const [coachingStyleCode, setCoachingStyleCode] = useState<
    (typeof COACHING_STYLE_OPTIONS)[number]['code'] | null
  >(null);
  const [locations, setLocations] = useState<string[]>([]);
  const [preferredLocationCode, setPreferredLocationCode] = useState<
    string | null
  >(null);
  const [duration, setDuration] = useState(30);
  const [weeklyCount, setWeeklyCount] = useState(3);
  const [hasAttentionAreas, setHasAttentionAreas] = useState<boolean | null>(
    null,
  );
  const [attentionAreas, setAttentionAreas] = useState<string[]>([]);
  const [showExtendedAttentionAreas, setShowExtendedAttentionAreas] =
    useState(false);
  const [painIntensityScores, setPainIntensityScores] = useState<
    Partial<Record<string, number>>
  >({});
  const [generalConsent, setGeneralConsent] = useState(false);
  const [sensitiveConsent, setSensitiveConsent] = useState(false);
  const [wearableConsent, setWearableConsent] = useState(false);
  const [marketingConsent, setMarketingConsent] = useState(false);
  const current = ONBOARDING_STEPS[step - 1] ?? ONBOARDING_STEPS[0];
  const timezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul';
    } catch {
      return 'Asia/Seoul';
    }
  }, []);

  const submit = useAsyncAction(async () => {
    if (
      sexCode === null ||
      primaryGoalCode === null ||
      experienceLevelCode === null ||
      preferredLocationCode === null ||
      !locations.includes(preferredLocationCode) ||
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
        attention_area_codes: hasAttentionAreas ? attentionAreas : [],
        preferred_exercise_type_codes: [],
        ...(coachingStyleCode === null
          ? {}
          : { coaching_style_code: coachingStyleCode }),
        consents: {
          general_personal_data: generalConsent,
          sensitive_data: sensitiveConsent,
          wearable_integration: wearableConsent,
          calendar_integration: false,
          marketing: marketingConsent,
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
    experienceLevelCode,
    generalConsent,
    hasAttentionAreas,
    heightCm,
    locations,
    nickname,
    attentionAreas,
    painIntensityScores,
    preferredLocationCode,
    primaryGoalCode,
    sensitiveConsent,
    sexCode,
    weightKg,
  });
  const blockedByAge =
    isApiError(submit.lastError) &&
    submit.lastError.code === 'AGE_REQUIREMENT_NOT_MET';
  const missingRequiredConsentCount =
    Number(!generalConsent) + Number(!sensitiveConsent);

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

  const toggleAttentionArea = (code: string) => {
    setAttentionAreas((values) => {
      if (!values.includes(code)) {
        setPainIntensityScores((currentValues) => ({
          ...currentValues,
          [code]: PAIN_INTENSITY_MIN,
        }));
        return [...values, code];
      }
      setPainIntensityScores((currentValues) => {
        const next = { ...currentValues };
        delete next[code];
        return next;
      });
      return values.filter((item) => item !== code);
    });
    submit.clearError();
  };

  const toggleLocation = (code: string) => {
    const next = toggle(locations, code);
    setLocations(next);
    setPreferredLocationCode((current) => {
      if (current !== null && next.includes(current)) return current;
      return next[0] ?? null;
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
            <BirthDateField
              onChange={(value) => {
                setBirthdate(value);
                submit.clearError();
              }}
              value={birthdate}
            />
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
                onPress={() => toggleLocation(item.code)}
              />
            ))}
            {locations.length > 1 ? (
              <View style={styles.preferredLocationSection}>
                <Text style={styles.painSectionTitle}>주로 운동할 장소</Text>
                <Text style={styles.hint}>
                  선택한 장소 중 가장 자주 이용할 곳을 골라주세요.
                </Text>
                {ONBOARDING_LOCATION_OPTIONS.filter((item) =>
                  locations.includes(item.code),
                ).map((item) => (
                  <DescriptionOption
                    accessibilityLabel={`대표 운동 장소: ${item.label}`}
                    description="운동 계획을 만들 때 이 장소를 우선 반영해요."
                    key={item.code}
                    label={item.label}
                    selected={preferredLocationCode === item.code}
                    onPress={() => {
                      setPreferredLocationCode(item.code);
                      submit.clearError();
                    }}
                  />
                ))}
              </View>
            ) : null}
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
                setPainIntensityScores({});
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
                  <Text style={styles.painSectionTitle}>불편한 부위</Text>
                  <Text style={styles.hint}>
                    해당하는 부위를 모두 선택해주세요.
                  </Text>
                  <View
                    style={styles.optionGrid}
                    testID="onboarding-attention-area-grid"
                  >
                    {DEFAULT_BODY_AREA_OPTIONS.map((item) => (
                      <Chip
                        grid
                        key={item.code}
                        label={item.label}
                        selected={attentionAreas.includes(item.code)}
                        onPress={() => toggleAttentionArea(item.code)}
                      />
                    ))}
                    {showExtendedAttentionAreas
                      ? EXTENDED_BODY_AREA_OPTIONS.map((item) => (
                          <Chip
                            grid
                            key={item.code}
                            label={item.label}
                            selected={attentionAreas.includes(item.code)}
                            onPress={() => toggleAttentionArea(item.code)}
                          />
                        ))
                      : null}
                  </View>
                  <Pressable
                    accessibilityLabel={
                      showExtendedAttentionAreas
                        ? '다른 부위 접기'
                        : '다른 부위 보기'
                    }
                    accessibilityRole="button"
                    onPress={() =>
                      setShowExtendedAttentionAreas((visible) => !visible)
                    }
                    style={styles.extendedAreaToggle}
                    testID="onboarding-extended-area-toggle"
                  >
                    <Text style={styles.extendedAreaToggleLabel}>
                      {showExtendedAttentionAreas ? '접기' : '다른 부위 보기'}
                    </Text>
                    <View style={styles.extendedAreaToggleIcon}>
                      <Text style={styles.extendedAreaToggleCaret}>
                        {showExtendedAttentionAreas ? '⌃' : '⌄'}
                      </Text>
                    </View>
                  </Pressable>
                </View>
                <View
                  style={styles.painSliderList}
                  testID="onboarding-pain-slider-list"
                >
                  {attentionAreas.map((code) => {
                    const score =
                      painIntensityScores[code] ?? PAIN_INTENSITY_MIN;
                    return (
                      <View
                        key={code}
                        style={styles.painSliderCard}
                        testID={`onboarding-pain-slider-card-${bodyAreaLabel(code)}`}
                      >
                        <PainIntensitySlider
                          bodyArea={bodyAreaLabel(code)}
                          onChange={(value) => {
                            setPainIntensityScores((values) => ({
                              ...values,
                              [code]: value,
                            }));
                            submit.clearError();
                          }}
                          value={score}
                        />
                      </View>
                    );
                  })}
                </View>
              </View>
            ) : null}
          </ChoiceCard>
        );
      case 'consent':
        return (
          <View style={styles.consentGroups}>
            <Card style={styles.cardGroup}>
              <Text style={styles.fieldLabel}>필수 동의</Text>
              <ConsentRow
                checked={generalConsent}
                description={CONSENT_OPTIONS.general_personal_data.description}
                label={CONSENT_OPTIONS.general_personal_data.label}
                required
                onPress={() => setGeneralConsent((value) => !value)}
              />
              <ConsentRow
                checked={sensitiveConsent}
                description={CONSENT_OPTIONS.sensitive_data.description}
                label={CONSENT_OPTIONS.sensitive_data.label}
                required
                onPress={() => setSensitiveConsent((value) => !value)}
              />
            </Card>
            <Card style={styles.cardGroup}>
              <Text style={styles.fieldLabel}>선택 동의</Text>
              <Text style={styles.hint}>
                선택 항목은 동의하지 않아도 서비스를 이용할 수 있어요.
              </Text>
              <ConsentRow
                checked={wearableConsent}
                description={CONSENT_OPTIONS.wearable_integration.description}
                label={CONSENT_OPTIONS.wearable_integration.label}
                required={false}
                onPress={() => setWearableConsent((value) => !value)}
              />
              <ConsentRow
                checked={marketingConsent}
                description={CONSENT_OPTIONS.marketing.description}
                label={CONSENT_OPTIONS.marketing.label}
                required={false}
                onPress={() => setMarketingConsent((value) => !value)}
              />
            </Card>
          </View>
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
            <View
              pointerEvents="none"
              style={styles.backIcon}
              testID="onboarding-back-icon"
            />
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
            <Text
              adjustsFontSizeToFit
              minimumFontScale={0.75}
              numberOfLines={1}
              style={styles.stepTitle}
            >
              {current.title}
            </Text>
            <RequirementBadge compact required={current.required} />
          </View>
          {current.intro ? (
            <Text style={styles.stepIntro}>{current.intro}</Text>
          ) : null}
        </View>
        {renderStep()}
        {blockedByAge ? (
          <InlineFeedback
            message="만 14세 미만은 이용할 수 없습니다."
            tone="error"
          />
        ) : submit.error ? (
          <InlineFeedback message={submit.error} tone="error" />
        ) : current.key === 'consent' && missingRequiredConsentCount > 0 ? (
          <View style={styles.consentReminder}>
            <Text style={styles.consentReminderTitle}>
              {missingRequiredConsentCount === 2
                ? '필수 동의 항목을 확인해주세요.'
                : '필수 동의 항목이 1개 남았어요.'}
            </Text>
            <Text style={styles.consentReminderDescription}>
              {missingRequiredConsentCount === 2
                ? '운동 계획을 만들기 위해 필수 항목의 동의가 필요해요.'
                : '계속하려면 필수 항목을 확인해주세요.'}
            </Text>
          </View>
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
              ? current.key === 'consent'
                ? '온보딩 중...'
                : '저장 중...'
              : !valid
                ? current.key === 'consent'
                  ? '필수 항목에 동의해주세요'
                  : '입력이 필요해요'
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
  coachingStyleCode: (typeof COACHING_STYLE_OPTIONS)[number]['code'] | null;
  locations: string[];
  preferredLocationCode: string | null;
  hasAttentionAreas: boolean | null;
  attentionAreas: string[];
  painIntensityScores: Partial<Record<string, number>>;
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
    case 'coachingStyle':
      return true;
    case 'location':
      return (
        form.locations.length > 0 &&
        form.preferredLocationCode !== null &&
        form.locations.includes(form.preferredLocationCode)
      );
    case 'attention':
      return (
        form.hasAttentionAreas !== null &&
        (!form.hasAttentionAreas ||
          (form.attentionAreas.length > 0 &&
            form.attentionAreas.every((code) => {
              const score = form.painIntensityScores[code];
              return (
                Number.isInteger(score) &&
                score !== undefined &&
                score >= PAIN_INTENSITY_MIN &&
                score <= PAIN_INTENSITY_MAX
              );
            })))
      );
    case 'consent':
      return form.generalConsent && form.sensitiveConsent;
    default:
      return true;
  }
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
        <View pointerEvents="none" style={styles.counterIcon}>
          <View style={styles.counterIconBar} />
        </View>
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
        <View pointerEvents="none" style={styles.counterIcon}>
          <View style={styles.counterIconBar} />
          <View
            style={[styles.counterIconBar, styles.counterIconBarVertical]}
          />
        </View>
      </Pressable>
    </Card>
  );
}

function PainIntensitySlider({
  bodyArea,
  onChange,
  value,
}: {
  bodyArea: string;
  onChange: (value: number) => void;
  value: number;
}) {
  const [trackWidth, setTrackWidth] = useState(0);
  const boundedValue = Math.min(
    PAIN_INTENSITY_MAX,
    Math.max(PAIN_INTENSITY_MIN, Math.round(value)),
  );
  const progress =
    (boundedValue - PAIN_INTENSITY_MIN) /
    (PAIN_INTENSITY_MAX - PAIN_INTENSITY_MIN);
  const label = `${bodyArea} 통증 정도`;

  const updateFromTrack = (locationX: number) => {
    if (trackWidth <= 0) return;
    const ratio = Math.min(1, Math.max(0, locationX / trackWidth));
    onChange(
      Math.round(
        PAIN_INTENSITY_MIN + ratio * (PAIN_INTENSITY_MAX - PAIN_INTENSITY_MIN),
      ),
    );
  };

  const adjust = (direction: -1 | 1) => {
    onChange(
      Math.min(
        PAIN_INTENSITY_MAX,
        Math.max(PAIN_INTENSITY_MIN, boundedValue + direction),
      ),
    );
  };

  return (
    <View style={styles.painIntensityControl}>
      <View style={styles.painIntensityHeading}>
        <Text numberOfLines={1} style={styles.painIntensityLabel}>
          {label}
        </Text>
        <Text
          accessibilityLiveRegion="polite"
          style={styles.painIntensityValue}
          testID={`onboarding-pain-intensity-value-${bodyArea}`}
        >
          {boundedValue}
        </Text>
      </View>
      <View
        accessible
        accessibilityActions={[
          { name: 'increment', label: `${label} 1 높이기` },
          { name: 'decrement', label: `${label} 1 낮추기` },
        ]}
        accessibilityLabel={label}
        accessibilityRole="adjustable"
        accessibilityValue={{
          max: PAIN_INTENSITY_MAX,
          min: PAIN_INTENSITY_MIN,
          now: boundedValue,
          text: `10점 중 ${boundedValue}점`,
        }}
        onAccessibilityAction={(event) => {
          if (event.nativeEvent.actionName === 'increment') adjust(1);
          else if (event.nativeEvent.actionName === 'decrement') adjust(-1);
        }}
        onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onResponderMove={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onStartShouldSetResponder={() => true}
        style={styles.painSliderTouchTarget}
        testID={`onboarding-pain-intensity-slider-${bodyArea}`}
      >
        <View pointerEvents="none" style={styles.painSliderTrack}>
          <View
            style={[styles.painSliderFill, { width: `${progress * 100}%` }]}
          />
          <View
            style={[styles.painSliderThumb, { left: `${progress * 100}%` }]}
          />
        </View>
      </View>
      <View style={styles.painSliderRangeLabels}>
        <Text style={styles.painSliderRangeLabel}>1</Text>
        <Text style={styles.painSliderRangeLabel}>10</Text>
      </View>
    </View>
  );
}

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function Chip({
  compact = false,
  flow = false,
  fullWidth = false,
  grid = false,
  grow = false,
  label,
  onPress,
  selected,
}: {
  compact?: boolean;
  flow?: boolean;
  fullWidth?: boolean;
  grid?: boolean;
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
        flow && styles.chipFlow,
        grid && styles.chipGrid,
        fullWidth && styles.chipFullWidth,
        compact && styles.chipCompact,
        selected && styles.chipSelected,
      ]}
    >
      <Text
        adjustsFontSizeToFit={flow || grid}
        minimumFontScale={flow || grid ? 0.85 : undefined}
        numberOfLines={compact || flow || grid ? 1 : undefined}
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
  accessibilityLabel,
  description,
  label,
  onPress,
  selected,
}: {
  accessibilityLabel?: string;
  description: string;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
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
  description,
  label,
  onPress,
  required,
}: {
  checked: boolean;
  description: string;
  label: string;
  onPress: () => void;
  required: boolean;
}) {
  return (
    <Pressable
      accessibilityHint={description}
      accessibilityLabel={label}
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
      <View style={styles.consentContent}>
        <View style={styles.consentLabelRow}>
          <Text style={styles.consentText}>{label}</Text>
          <RequirementBadge required={required} />
        </View>
        <Text style={styles.hint}>{description}</Text>
      </View>
    </Pressable>
  );
}

function RequirementBadge({
  compact = false,
  required,
}: {
  compact?: boolean;
  required: boolean;
}) {
  return (
    <Text
      style={[
        styles.requirementBadge,
        compact
          ? styles.requirementBadgeCompact
          : styles.requirementBadgeInline,
        required
          ? styles.requirementBadgeRequired
          : styles.requirementBadgeOptional,
      ]}
    >
      {required ? '필수' : '선택'}
    </Text>
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
      coaching_style_code: 'coachingStyle',
      preferred_location_code: 'location',
      available_location_codes: 'location',
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
  backIcon: {
    width: 12,
    height: 12,
    borderBottomWidth: 2.5,
    borderLeftWidth: 2.5,
    borderColor: colors.text,
    transform: [{ rotate: '45deg' }],
  },
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
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  stepTitle: {
    flexShrink: 1,
    color: colors.text,
    fontSize: 22,
    fontWeight: '700',
    lineHeight: 29,
  },
  stepIntro: { color: colors.textMuted, fontSize: 13, lineHeight: 20 },
  requirementBadge: {
    flexShrink: 0,
    overflow: 'hidden',
    borderRadius: 5,
    fontWeight: '700',
    textAlign: 'center',
  },
  requirementBadgeCompact: {
    fontSize: 9,
    lineHeight: 12,
    paddingHorizontal: 5,
    paddingVertical: 2,
  },
  requirementBadgeInline: {
    fontSize: 10,
    lineHeight: 14,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  requirementBadgeRequired: {
    backgroundColor: colors.fieldError,
    color: colors.surface,
  },
  requirementBadgeOptional: {
    backgroundColor: '#EFEBE3',
    color: colors.textMuted,
  },
  cardGroup: { gap: 14 },
  input: { backgroundColor: colors.canvas },
  fieldLabel: { color: colors.text, fontSize: 13, fontWeight: '700' },
  bodyRow: { flexDirection: 'row', gap: 10 },
  bodyField: { minWidth: 0, flex: 1 },
  suffix: { color: colors.textMuted, fontSize: 13 },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  choiceCard: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  preferredLocationSection: { width: '100%', gap: spacing.sm },
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
  counterIcon: {
    position: 'relative',
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  counterIconBar: {
    position: 'absolute',
    width: 20,
    height: 2.5,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  counterIconBarVertical: {
    transform: [{ rotate: '90deg' }],
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
  chipFlow: {
    minHeight: 48,
    flexGrow: 1,
    flexShrink: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipGrid: {
    width: '48.5%',
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipFullWidth: {
    width: '100%',
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
  optionGrid: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    columnGap: spacing.sm,
    rowGap: spacing.sm,
  },
  extendedAreaToggle: {
    minHeight: 36,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  extendedAreaToggleLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  extendedAreaToggleIcon: {
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.surface,
  },
  extendedAreaToggleCaret: {
    color: colors.textMuted,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 16,
  },
  painSliderList: { gap: spacing.sm },
  painSliderCard: {
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: radii.control,
    backgroundColor: '#FBEAE7',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  painIntensityControl: { gap: spacing.xs },
  painIntensityHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  painIntensityLabel: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  painIntensityValue: {
    minWidth: 38,
    flexShrink: 0,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: 12,
    backgroundColor: colors.surface,
    color: '#8E3226',
    fontSize: 18,
    fontWeight: '400',
    lineHeight: 24,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    textAlign: 'center',
  },
  painSliderTouchTarget: {
    height: 40,
    justifyContent: 'center',
  },
  painSliderTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: 'rgba(162, 63, 42, 0.12)',
  },
  painSliderFill: {
    height: '100%',
    borderRadius: 4,
    backgroundColor: 'rgba(162, 63, 42, 0.42)',
  },
  painSliderThumb: {
    position: 'absolute',
    top: -8,
    width: 24,
    height: 24,
    marginLeft: -12,
    borderWidth: 3,
    borderColor: colors.surface,
    borderRadius: 12,
    backgroundColor: 'rgba(142, 50, 38, 0.72)',
  },
  painSliderRangeLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  painSliderRangeLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '400',
  },
  consentGroups: { gap: 14 },
  consentReminder: {
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.feedback,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 13,
    paddingVertical: 11,
  },
  consentReminderTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 20,
  },
  consentReminderDescription: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
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
  consentContent: { minWidth: 0, flex: 1, gap: 4 },
  consentLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  consentText: {
    flexShrink: 1,
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
