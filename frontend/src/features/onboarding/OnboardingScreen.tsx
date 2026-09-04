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
import Svg, { Path } from 'react-native-svg';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import {
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  orderBodyAreaCodes,
} from '../../api/labels';
import { useAsyncAction } from '../../api/useAsync';
import {
  Button,
  Card,
  InlineFeedback,
  StepCounter,
  TextField,
} from '../../components/primitives';
import {
  PAIN_INTENSITY_MAX,
  PAIN_INTENSITY_MIN,
  PainIntensitySlider,
} from '../../components/profile/PainIntensitySlider';
import { useScale } from '../../components/scale';
import { colors, radii, spacing } from '../../components/theme';
import { PROFILE_BODY_LIMITS } from '../profile/profileModel';
import {
  ONBOARDING_COACHING_STYLE_OPTIONS,
  ONBOARDING_EXPERIENCE_OPTIONS,
  ONBOARDING_GOAL_OPTIONS,
  ONBOARDING_WEEKLY_COUNT,
} from './onboardingOptions';
import { BirthDateField, latestEligibleBirthdateIso } from './BirthDateField';

const CURRENT_TERMS_VERSION = 'terms-v1.0.0';

const CONSENT_OPTIONS = {
  service_terms: {
    label: '서비스 이용약관 동의',
    description: '서비스 지원 범위와 이용 기준을 확인하고 동의해요.',
  },
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
    key: 'eligibility',
    title: '운동 지원 범위를 확인해주세요',
    intro: '안전한 운동 계획을 위해 현재 서비스가 지원하는 범위인지 확인해요.',
    required: true,
  },
  {
    key: 'body',
    title: '현재 체중을 입력해주세요',
    intro: '체중은 예상 소모 칼로리 계산에만 사용해요.',
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
    intro: '선택한 정보는 매일 컨디션 확인의 초기값으로만 사용해요.',
    required: false,
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
  const [medicalExerciseRestriction, setMedicalExerciseRestriction] = useState<
    boolean | null
  >(null);
  const [weightKg, setWeightKg] = useState('');
  const [primaryGoalCode, setPrimaryGoalCode] = useState<
    (typeof ONBOARDING_GOAL_OPTIONS)[number]['code'] | null
  >(null);
  const [experienceLevelCode, setExperienceLevelCode] = useState<
    (typeof ONBOARDING_EXPERIENCE_OPTIONS)[number]['code']
  >(ONBOARDING_EXPERIENCE_OPTIONS[0].code);
  const [coachingStyleCode, setCoachingStyleCode] = useState<
    (typeof ONBOARDING_COACHING_STYLE_OPTIONS)[number]['code']
  >(ONBOARDING_COACHING_STYLE_OPTIONS[0].code);
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
  const [termsConsent, setTermsConsent] = useState(false);
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
      medicalExerciseRestriction !== false ||
      primaryGoalCode === null ||
      (hasAttentionAreas && attentionAreas.length === 0)
    ) {
      return;
    }
    try {
      await api.submitOnboarding({
        nickname: nickname.trim(),
        date_of_birth: birthdate.trim(),
        medical_exercise_restriction: medicalExerciseRestriction,
        weight_kg: Number(weightKg),
        primary_goal_code: primaryGoalCode,
        experience_level_code: experienceLevelCode,
        timezone,
        weekly_target_sessions: weeklyCount,
        coaching_style_code: coachingStyleCode,
        terms_version: CURRENT_TERMS_VERSION,
        persistent_pains:
          hasAttentionAreas === true
            ? attentionAreas.map((code) => ({
                body_area_code: code,
                intensity_score:
                  painIntensityScores[code] ?? PAIN_INTENSITY_MIN,
              }))
            : [],
        consents: {
          general_personal_data: generalConsent,
          sensitive_data: sensitiveConsent,
          wearable_integration: wearableConsent,
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
    medicalExerciseRestriction,
    nickname,
    attentionAreas,
    painIntensityScores,
    primaryGoalCode,
    sensitiveConsent,
    termsConsent,
    weightKg,
  });
  const blockedByAge =
    isApiError(submit.lastError) &&
    ['AGE_REQUIREMENT_NOT_MET', 'OUT_OF_SCOPE_AGE'].includes(
      submit.lastError.code,
    );
  const missingRequiredConsentCount =
    Number(!termsConsent) + Number(!generalConsent) + Number(!sensitiveConsent);

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
        return orderBodyAreaCodes([...values, code]);
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
      case 'eligibility':
        return (
          <View style={styles.consentGroups}>
            <ChoiceCard>
              <Text style={styles.hint}>
                현재 질환·임신 등으로 개별적인 운동 관리가 필요하거나 의료진에게
                운동 제한·주의 안내를 받은 상태인가요?
              </Text>
              <Chip
                grow
                label="아니요"
                selected={medicalExerciseRestriction === false}
                onPress={() => {
                  setMedicalExerciseRestriction(false);
                  submit.clearError();
                }}
              />
              <Chip
                grow
                label="예"
                selected={medicalExerciseRestriction === true}
                onPress={() => {
                  setMedicalExerciseRestriction(true);
                  submit.clearError();
                }}
              />
            </ChoiceCard>
            {medicalExerciseRestriction === true ? (
              <InlineFeedback
                message="현재 상태에 맞는 개별 운동 관리는 의료진 또는 자격을 갖춘 전문가와 상의해주세요."
                tone="warning"
              />
            ) : null}
          </View>
        );
      case 'body':
        return (
          <Card style={styles.cardGroup}>
            <TextField
              accessibilityLabel="체중"
              inputMode="decimal"
              onChangeText={(value) => setWeightKg(onlyDecimal(value))}
              placeholder="65"
              style={styles.input}
              trailing={<Text style={styles.suffix}>kg</Text>}
              value={weightKg}
            />
            <Text style={styles.hint}>
              입력 범위 {PROFILE_BODY_LIMITS.weightKg.min}–
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
            {ONBOARDING_COACHING_STYLE_OPTIONS.map((item) => (
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
                      <View
                        style={
                          showExtendedAttentionAreas
                            ? styles.extendedAreaToggleCaretUp
                            : undefined
                        }
                        testID="onboarding-extended-area-caret"
                      >
                        <Svg
                          aria-hidden
                          fill="none"
                          height={14}
                          viewBox="0 0 24 24"
                          width={14}
                        >
                          <Path
                            d="M6 9l6 6 6-6"
                            stroke={colors.textMuted}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2.4}
                          />
                        </Svg>
                      </View>
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
                          testIDPrefix="onboarding"
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
                checked={termsConsent}
                description={CONSENT_OPTIONS.service_terms.description}
                label={CONSENT_OPTIONS.service_terms.label}
                required
                onPress={() => setTermsConsent((value) => !value)}
              />
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
            message="만 18세 미만이거나 만 65세 이상이면 이용할 수 없습니다."
            tone="error"
          />
        ) : submit.error ? (
          <InlineFeedback message={submit.error} tone="error" />
        ) : current.key === 'consent' && missingRequiredConsentCount > 0 ? (
          <View style={styles.consentReminder}>
            <Text style={styles.consentReminderTitle}>
              {missingRequiredConsentCount === 3
                ? '필수 동의 항목을 확인해주세요.'
                : `필수 동의 항목이 ${missingRequiredConsentCount}개 남았어요.`}
            </Text>
            <Text style={styles.consentReminderDescription}>
              {missingRequiredConsentCount === 3
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
              ? '온보딩 중...'
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
  medicalExerciseRestriction: boolean | null;
  weightKg: string;
  primaryGoalCode: (typeof ONBOARDING_GOAL_OPTIONS)[number]['code'] | null;
  experienceLevelCode:
    (typeof ONBOARDING_EXPERIENCE_OPTIONS)[number]['code'] | null;
  coachingStyleCode:
    (typeof ONBOARDING_COACHING_STYLE_OPTIONS)[number]['code'] | null;
  hasAttentionAreas: boolean | null;
  attentionAreas: string[];
  painIntensityScores: Partial<Record<string, number>>;
  generalConsent: boolean;
  sensitiveConsent: boolean;
  termsConsent: boolean;
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
    case 'eligibility':
      return form.medicalExerciseRestriction === false;
    case 'body':
      return isInRange(form.weightKg, PROFILE_BODY_LIMITS.weightKg);
    case 'goal':
      return form.primaryGoalCode !== null;
    case 'experience':
      return form.experienceLevelCode !== null;
    case 'coachingStyle':
      return form.coachingStyleCode !== null;
    case 'attention':
      return (
        form.hasAttentionAreas !== true ||
        (form.attentionAreas.length > 0 &&
          form.attentionAreas.every((code) => {
            const score = form.painIntensityScores[code];
            return (
              Number.isInteger(score) &&
              score !== undefined &&
              score >= PAIN_INTENSITY_MIN &&
              score <= PAIN_INTENSITY_MAX
            );
          }))
      );
    case 'consent':
      return form.termsConsent && form.generalConsent && form.sensitiveConsent;
    default:
      return true;
  }
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
      'OUT_OF_SCOPE_AGE',
      'INVALID_DATE_OF_BIRTH',
      'INVALID_TIMEZONE',
    ].includes(error.code)
  ) {
    return stepNumber('basic');
  }
  if (error.code === 'REQUIRED_CONSENT_MISSING') {
    return stepNumber('consent');
  }
  if (error.code === 'OUT_OF_SCOPE_MEDICAL_MANAGEMENT') {
    return stepNumber('eligibility');
  }
  if (error.code === 'TERMS_VERSION_MISMATCH') {
    return stepNumber('consent');
  }

  const fieldToStep: Record<string, (typeof ONBOARDING_STEPS)[number]['key']> =
    {
      nickname: 'basic',
      date_of_birth: 'basic',
      medical_exercise_restriction: 'eligibility',
      weight_kg: 'body',
      primary_goal_code: 'goal',
      experience_level_code: 'experience',
      coaching_style_code: 'coachingStyle',
      weekly_target_sessions: 'frequency',
      persistent_pains: 'attention',
      terms_version: 'consent',
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
  extendedAreaToggleCaretUp: {
    transform: [{ rotate: '180deg' }],
  },
  painSliderList: { gap: spacing.sm },
  painSliderCard: {
    borderWidth: 1,
    borderColor: '#E8C3B8',
    borderRadius: 14,
    backgroundColor: '#FFFDFC',
    paddingVertical: 12,
    paddingHorizontal: 14,
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
