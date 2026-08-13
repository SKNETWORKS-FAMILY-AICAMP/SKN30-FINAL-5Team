import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import {
  CARE_OPTIONS,
  COACH_OPTIONS,
  EQUIPMENT_OPTIONS,
  FREQUENCY_OPTIONS,
  GOAL_OPTIONS,
  LEVEL_OPTIONS,
  PLACE_OPTIONS,
  PROFILE_INITIAL_FORM,
  PROFILE_STEPS,
  type ProfileForm,
  type ProfilePreviewState,
  TYPE_OPTIONS,
} from './profileModel';

export const PROFILE_LAYOUT = {
  headerHorizontalPadding: 20,
  contentHorizontalPadding: 20,
  contentGap: 14,
  footerHorizontalPadding: 20,
  footerBottomPadding: 44,
  previousButtonWidth: 96,
} as const;

type ProfileScreenProps = {
  initialStep?: number;
  onExit?: () => void;
  onFinish?: () => void;
  onStepChange?: (step: number) => void;
  previewState?: ProfilePreviewState;
};

export function ProfileScreen({ ...props }: ProfileScreenProps) {
  const initialStep = clampStep(props.initialStep ?? 1);
  const previewState = props.previewState ?? 'editing';

  return (
    <ProfileScreenContent
      key={`${initialStep}:${previewState}`}
      {...props}
      initialStep={initialStep}
      previewState={previewState}
    />
  );
}

function ProfileScreenContent({
  initialStep = 1,
  onExit,
  onFinish,
  onStepChange,
  previewState = 'editing',
}: ProfileScreenProps) {
  const forcedSummary = ['saving', 'save-error', 'done'].includes(previewState);
  const [step, setStep] = useState(
    forcedSummary ? PROFILE_STEPS.length : initialStep,
  );
  const [form, setForm] = useState<ProfileForm>(() => ({
    ...PROFILE_INITIAL_FORM,
    ...(previewState === 'validation-error'
      ? { height: '', weight: '', birth: '991332', adult: false }
      : null),
  }));
  const current = PROFILE_STEPS[step - 1] ?? PROFILE_STEPS[0];
  const isSaving = previewState === 'saving';
  const isValid = isStepValid(current.key, form);

  const changeStep = (nextStep: number) => {
    const bounded = clampStep(nextStep);
    setStep(bounded);
    onStepChange?.(bounded);
  };

  const handleBack = () => {
    if (step === 1) {
      onExit?.();
      return;
    }
    changeStep(step - 1);
  };

  const handleNext = () => {
    if (!isValid || isSaving) return;
    if (step === PROFILE_STEPS.length) {
      onFinish?.();
      return;
    }
    changeStep(step + 1);
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
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            onPress={handleBack}
            style={styles.backButton}
          >
            <Text style={styles.backIcon}>‹</Text>
          </Pressable>
          <Text accessibilityRole="header" style={styles.headerTitle}>
            프로필 등록
          </Text>
          <Text style={styles.stepCounter}>
            {step} / {PROFILE_STEPS.length}
          </Text>
        </View>
        <View style={styles.progressTrack}>
          <View
            testID="profile-progress"
            style={[
              styles.progressFill,
              { width: `${Math.round((step / PROFILE_STEPS.length) * 100)}%` },
            ]}
          />
        </View>
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
        style={styles.content}
        contentContainerStyle={styles.contentContainer}
      >
        {previewState === 'reason' && step === 1 ? (
          <InlineFeedback
            message="계정이 만들어졌어요. 필수 프로필을 등록하면 가입이 완료돼요."
            tone="success"
          />
        ) : null}

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

        <StepContent
          form={form}
          onChange={setForm}
          onEditStep={changeStep}
          showValidation={previewState === 'validation-error'}
          step={step}
        />

        {previewState === 'save-error' ? (
          <InlineFeedback
            action={
              <Button
                label="다시 시도"
                labelStyle={styles.retryLabel}
                onPress={handleNext}
                style={styles.retryButton}
                tone="secondary"
              />
            }
            message="프로필 저장에 실패했어요. 저장이 완료되지 않으면 홈을 이용할 수 없어요."
            tone="error"
          />
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          label="이전"
          onPress={handleBack}
          style={styles.previousButton}
          tone="secondary"
        />
        <Button
          disabled={!isValid || isSaving}
          label={getNextLabel({
            currentKey: current.key,
            form,
            isSaving,
            step,
          })}
          labelStyle={isSaving ? styles.savingLabel : undefined}
          leading={
            isSaving ? (
              <ActivityIndicator color={colors.surface} size="small" />
            ) : undefined
          }
          onPress={handleNext}
          style={[styles.nextButton, isSaving && styles.savingButton]}
        />
      </View>

      {previewState === 'exit' ? (
        <ModalOverlay>
          <Text style={styles.modalTitle}>등록을 중단할까요?</Text>
          <Text style={styles.modalMessage}>
            키·체중 등 필수 프로필을 등록하지 않으면 홈을 이용할 수 없어요. 지금
            나가면 입력한 내용은 저장되지 않아요.
          </Text>
          <View style={styles.modalActions}>
            <Button label="계속 등록하기" />
            <Button
              label="나가기 (로그인 화면으로)"
              labelStyle={styles.exitLabel}
              onPress={onExit}
              tone="secondary"
            />
          </View>
        </ModalOverlay>
      ) : null}

      {previewState === 'done' ? (
        <ModalOverlay alignCenter>
          <View style={styles.doneMark}>
            <Text style={styles.doneMarkLabel}>✓</Text>
          </View>
          <Text style={styles.doneTitle}>프로필 등록 완료</Text>
          <Text style={[styles.modalMessage, styles.doneMessage]}>
            가입한 계정으로 로그인하면 홈으로 이동해요. 비밀번호는 저장하지
            않아요.
          </Text>
          <Button
            label="로그인 화면으로"
            onPress={onFinish}
            style={styles.doneButton}
          />
        </ModalOverlay>
      ) : null}
    </SafeAreaView>
  );
}

function StepContent({
  form,
  onChange,
  onEditStep,
  showValidation,
  step,
}: {
  form: ProfileForm;
  onChange: (form: ProfileForm) => void;
  onEditStep: (step: number) => void;
  showValidation: boolean;
  step: number;
}) {
  const update = <K extends keyof ProfileForm>(
    key: K,
    value: ProfileForm[K],
  ) => {
    onChange({ ...form, [key]: value });
  };

  const toggleMulti = (
    key: 'types' | 'equipment' | 'care',
    label: string,
    exclusive?: string,
  ) => {
    const current = form[key];
    if (exclusive && label === exclusive) {
      update(key, [label]);
      return;
    }
    const withoutExclusive = exclusive
      ? current.filter((item) => item !== exclusive)
      : current;
    const next = withoutExclusive.includes(label)
      ? withoutExclusive.filter((item) => item !== label)
      : [...withoutExclusive, label];
    update(key, next.length > 0 ? next : exclusive ? [exclusive] : []);
  };

  switch (step) {
    case 1:
      return (
        <Card>
          <TextField
            accessibilityLabel="닉네임"
            label="닉네임"
            onChangeText={(value) => update('nickname', value)}
            placeholder="앱에서 불릴 이름"
            style={styles.profileField}
            value={form.nickname}
          />
        </Card>
      );
    case 2: {
      const birthInvalid = showValidation || !isBirthValid(form.birth);
      return (
        <Card style={styles.cardGroup}>
          <TextField
            accessibilityLabel="생년월일 6자리"
            error={birthInvalid ? 'YYMMDD 형식으로 입력해주세요.' : undefined}
            inputMode="numeric"
            label="주민등록번호 앞 6자리"
            maxLength={6}
            onChangeText={(value) => update('birth', onlyDigits(value, 6))}
            placeholder="예: 990312"
            style={styles.profileField}
            trailing={
              <Text style={styles.fieldSuffix}>{form.birth.length}/6</Text>
            }
            value={form.birth}
          />
          <Pressable
            accessibilityRole="checkbox"
            accessibilityState={{ checked: form.adult }}
            onPress={() => update('adult', !form.adult)}
            style={[styles.consentRow, form.adult && styles.consentRowSelected]}
          >
            <View
              style={[styles.checkBox, form.adult && styles.checkBoxSelected]}
            >
              <Text
                style={[
                  styles.checkMark,
                  !form.adult && styles.checkMarkHidden,
                ]}
              >
                ✓
              </Text>
            </View>
            <Text style={styles.consentLabel}>만 14세 이상입니다</Text>
          </Pressable>
        </Card>
      );
    }
    case 3:
      return (
        <ChoiceCard>
          <ChoiceRow
            grow
            options={['여성', '남성', '선택 안 함']}
            selected={[form.gender]}
            onSelect={(value) => update('gender', value)}
          />
        </ChoiceCard>
      );
    case 4: {
      const bodyInvalid = showValidation || !form.height || !form.weight;
      return (
        <Card style={[styles.bodyCard, bodyInvalid && styles.bodyCardInvalid]}>
          <View style={styles.bodyRow}>
            <TextField
              accessibilityLabel="키"
              containerStyle={styles.bodyField}
              inputMode="decimal"
              onChangeText={(value) => update('height', onlyDecimal(value, 5))}
              placeholder="키"
              style={[styles.profileField, bodyInvalid && styles.fieldInvalid]}
              trailing={<Text style={styles.fieldSuffix}>cm</Text>}
              value={form.height}
            />
            <TextField
              accessibilityLabel="체중"
              containerStyle={styles.bodyField}
              inputMode="decimal"
              onChangeText={(value) => update('weight', onlyDecimal(value, 5))}
              placeholder="체중"
              style={[styles.profileField, bodyInvalid && styles.fieldInvalid]}
              trailing={<Text style={styles.fieldSuffix}>kg</Text>}
              value={form.weight}
            />
          </View>
          <Text
            style={[styles.bodyHint, bodyInvalid && styles.bodyHintInvalid]}
          >
            {bodyInvalid
              ? '키와 체중을 입력해야 등록을 완료할 수 있어요.'
              : '운동 강도 계산에 사용해요.'}
          </Text>
        </Card>
      );
    }
    case 5:
      return (
        <ChoiceCard>
          <ChoiceRow
            options={GOAL_OPTIONS}
            selected={[form.goal]}
            onSelect={(value) => update('goal', value)}
          />
        </ChoiceCard>
      );
    case 6:
      return (
        <ChoiceCard>
          <DescriptionChoices
            options={LEVEL_OPTIONS}
            selected={form.level}
            onSelect={(value) => update('level', value)}
          />
        </ChoiceCard>
      );
    case 7:
      return (
        <ChoiceCard>
          <ChoiceRow
            options={TYPE_OPTIONS}
            selected={form.types}
            onSelect={(value) => toggleMulti('types', value)}
          />
        </ChoiceCard>
      );
    case 8:
      return (
        <ChoiceCard>
          <DescriptionChoices
            options={COACH_OPTIONS}
            selected={form.coach}
            onSelect={(value) => update('coach', value)}
          />
        </ChoiceCard>
      );
    case 9:
      return (
        <ChoiceCard>
          <ChoiceRow
            grow
            options={PLACE_OPTIONS}
            selected={[form.place]}
            onSelect={(value) => update('place', value)}
          />
        </ChoiceCard>
      );
    case 10:
      return (
        <ChoiceCard>
          <ChoiceRow
            options={EQUIPMENT_OPTIONS}
            selected={form.equipment}
            onSelect={(value) => toggleMulti('equipment', value, '맨몸만')}
          />
        </ChoiceCard>
      );
    case 11:
      return (
        <Card>
          <TextField
            accessibilityLabel="운동 시간"
            inputMode="numeric"
            maxLength={3}
            onChangeText={(value) => update('duration', onlyDigits(value, 3))}
            placeholder="예: 30"
            style={styles.profileField}
            trailing={<Text style={styles.fieldSuffix}>분</Text>}
            value={form.duration}
          />
        </Card>
      );
    case 12:
      return (
        <ChoiceCard>
          <ChoiceRow
            grow
            options={FREQUENCY_OPTIONS}
            selected={[form.frequency]}
            onSelect={(value) => update('frequency', value)}
          />
        </ChoiceCard>
      );
    case 13:
      return (
        <ChoiceCard>
          <ChoiceRow
            options={CARE_OPTIONS}
            selected={form.care}
            onSelect={(value) => toggleMulti('care', value, '없음')}
          />
          {form.care.includes('기타') ? (
            <TextField
              accessibilityLabel="기타 부위 또는 증상"
              containerStyle={styles.otherField}
              label="기타 부위·증상"
              onChangeText={(value) => update('careEtc', value)}
              placeholder="예: 왼쪽 골반이 뻐근해요"
              style={styles.profileField}
              value={form.careEtc}
            />
          ) : null}
        </ChoiceCard>
      );
    case 14:
      return <SummaryCard form={form} onEditStep={onEditStep} />;
    default:
      return null;
  }
}

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function ChoiceRow({
  grow = false,
  onSelect,
  options,
  selected,
}: {
  grow?: boolean;
  onSelect: (value: string) => void;
  options: readonly string[];
  selected: string[];
}) {
  return (
    <View style={styles.choiceRow}>
      {options.map((option) => {
        const active = selected.includes(option);
        return (
          <Pressable
            key={option}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            onPress={() => onSelect(option)}
            style={[
              styles.choice,
              grow && styles.choiceGrow,
              active && styles.choiceSelected,
            ]}
          >
            <Text
              style={[styles.choiceLabel, active && styles.choiceLabelSelected]}
            >
              {option}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function DescriptionChoices({
  onSelect,
  options,
  selected,
}: {
  onSelect: (value: string) => void;
  options: readonly { label: string; description: string }[];
  selected: string;
}) {
  return (
    <View style={styles.descriptionChoices}>
      {options.map((option) => {
        const active = selected === option.label;
        return (
          <Pressable
            key={option.label}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            onPress={() => onSelect(option.label)}
            style={[styles.descriptionChoice, active && styles.choiceSelected]}
          >
            <Text
              style={[
                styles.descriptionTitle,
                active && styles.choiceLabelSelected,
              ]}
            >
              {option.label}
            </Text>
            <Text
              style={[
                styles.descriptionText,
                active && styles.descriptionTextSelected,
              ]}
            >
              {option.description}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function SummaryCard({
  form,
  onEditStep,
}: {
  form: ProfileForm;
  onEditStep: (step: number) => void;
}) {
  const rows = [
    ['닉네임', form.nickname || '미입력'],
    ['생년월일', form.birth || '미입력'],
    ['성별', form.gender || '미선택'],
    [
      '키 · 체중 (필수)',
      `${form.height || '미입력'}cm · ${form.weight || '미입력'}kg`,
    ],
    ['목표', form.goal || '미선택'],
    ['경험 수준', form.level || '미선택'],
    ['선호 운동', joinValues(form.types, '미선택')],
    ['코칭 스타일', form.coach || '미선택'],
    ['운동 장소', form.place || '미선택'],
    ['기구', joinValues(form.equipment, '미선택')],
    ['운동 시간', form.duration ? `${form.duration}분` : '미입력'],
    ['주간 횟수', form.frequency || '미선택'],
    [
      '주의 부위',
      `${joinValues(form.care, '없음')}${
        form.care.includes('기타') && form.careEtc ? ` (${form.careEtc})` : ''
      }`,
    ],
  ] as const;

  return (
    <Card>
      {rows.map(([label, value], index) => (
        <Pressable
          key={label}
          accessibilityRole="button"
          accessibilityLabel={`${label} 수정`}
          onPress={() => onEditStep(index + 1)}
          style={styles.summaryRow}
        >
          <Text style={styles.summaryLabel}>{label}</Text>
          <Text style={styles.summaryValue}>{value}</Text>
        </Pressable>
      ))}
      <Text style={styles.summaryHint}>
        항목을 누르면 해당 페이지로 이동해요.
      </Text>
    </Card>
  );
}

function ModalOverlay({
  alignCenter = false,
  children,
}: {
  alignCenter?: boolean;
  children: React.ReactNode;
}) {
  return (
    <View accessibilityViewIsModal style={styles.modalOverlay}>
      <Card style={[styles.modalCard, alignCenter && styles.modalCardCenter]}>
        {children}
      </Card>
    </View>
  );
}

function clampStep(step: number) {
  return Math.max(1, Math.min(PROFILE_STEPS.length, Math.round(step)));
}

function onlyDigits(value: string, maxLength: number) {
  return value.replace(/[^0-9]/g, '').slice(0, maxLength);
}

function onlyDecimal(value: string, maxLength: number) {
  return value.replace(/[^0-9.]/g, '').slice(0, maxLength);
}

function isBirthValid(value: string) {
  if (!/^\d{6}$/.test(value)) return false;
  const month = Number(value.slice(2, 4));
  const day = Number(value.slice(4, 6));
  return month >= 1 && month <= 12 && day >= 1 && day <= 31;
}

function isStepValid(
  key: (typeof PROFILE_STEPS)[number]['key'],
  form: ProfileForm,
) {
  switch (key) {
    case 'nickname':
      return form.nickname.trim().length > 0;
    case 'birth':
      return isBirthValid(form.birth) && form.adult;
    case 'gender':
      return form.gender.length > 0;
    case 'body':
      return Number(form.height) > 0 && Number(form.weight) > 0;
    case 'goal':
      return form.goal.length > 0;
    case 'level':
      return form.level.length > 0;
    case 'types':
      return form.types.length > 0;
    case 'coach':
      return form.coach.length > 0;
    case 'place':
      return form.place.length > 0;
    case 'equipment':
      return form.equipment.length > 0;
    default:
      return true;
  }
}

function getNextLabel({
  currentKey,
  form,
  isSaving,
  step,
}: {
  currentKey: (typeof PROFILE_STEPS)[number]['key'];
  form: ProfileForm;
  isSaving: boolean;
  step: number;
}) {
  if (isSaving) return '저장 중...';
  if (!isStepValid(currentKey, form)) {
    return currentKey === 'birth'
      ? '생년월일과 동의가 필요해요'
      : '입력이 필요해요';
  }
  if (step === PROFILE_STEPS.length) return '프로필 등록 완료';
  if (
    (currentKey === 'duration' && !form.duration) ||
    (currentKey === 'frequency' && !form.frequency)
  ) {
    return '건너뛰기';
  }
  return '다음';
}

function joinValues(values: string[], fallback: string) {
  return values.length > 0 ? values.join(', ') : fallback;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  header: {
    gap: spacing.md,
    backgroundColor: colors.canvas,
    paddingTop: spacing.xl,
    paddingHorizontal: PROFILE_LAYOUT.headerHorizontalPadding,
    paddingBottom: spacing.md,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  backButton: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 17,
    backgroundColor: colors.surface,
  },
  backIcon: {
    color: colors.text,
    fontSize: 30,
    lineHeight: 32,
  },
  headerTitle: {
    flex: 1,
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  stepCounter: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
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
  content: {
    flex: 1,
  },
  contentContainer: {
    gap: PROFILE_LAYOUT.contentGap,
    paddingTop: spacing.sm,
    paddingHorizontal: PROFILE_LAYOUT.contentHorizontalPadding,
    paddingBottom: 20,
  },
  stepHeading: {
    gap: 6,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
  },
  stepTitle: {
    flexShrink: 1,
    color: colors.text,
    fontSize: 22,
    fontWeight: '700',
    lineHeight: 29,
  },
  stepIntro: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
  },
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
  profileField: {
    backgroundColor: colors.canvas,
  },
  fieldSuffix: {
    color: colors.textMuted,
    fontSize: 13,
  },
  cardGroup: {
    gap: 14,
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
  consentRowSelected: {
    borderColor: colors.primary,
  },
  checkBox: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#D5D0C6',
    borderRadius: 6,
    backgroundColor: colors.surface,
  },
  checkBoxSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  checkMark: {
    color: colors.surface,
    fontSize: 12,
    fontWeight: '700',
  },
  checkMarkHidden: {
    color: 'transparent',
  },
  consentLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
  },
  choiceCard: {
    gap: 14,
  },
  choiceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  choice: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  choiceGrow: {
    minWidth: 52,
    flexGrow: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
  },
  choiceSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  choiceLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
  },
  choiceLabelSelected: {
    color: colors.surface,
  },
  descriptionChoices: {
    gap: spacing.sm,
  },
  descriptionChoice: {
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
  bodyCard: {
    gap: 10,
    borderWidth: 1.5,
    borderColor: 'transparent',
  },
  bodyCardInvalid: {
    borderColor: colors.dangerBorder,
  },
  bodyRow: {
    flexDirection: 'row',
    gap: 10,
  },
  bodyField: {
    flex: 1,
  },
  fieldInvalid: {
    borderColor: colors.fieldError,
  },
  bodyHint: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
  },
  bodyHintInvalid: {
    color: colors.fieldError,
  },
  otherField: {
    marginTop: 14,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: '#F0EDE6',
    paddingVertical: 11,
  },
  summaryLabel: {
    width: 96,
    flexShrink: 0,
    color: colors.textMuted,
    fontSize: 13,
  },
  summaryValue: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
    textAlign: 'right',
  },
  summaryHint: {
    marginTop: spacing.md,
    color: '#A8A49C',
    fontSize: 12,
    lineHeight: 18,
  },
  footer: {
    flexDirection: 'row',
    gap: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.canvas,
    paddingTop: 14,
    paddingHorizontal: PROFILE_LAYOUT.footerHorizontalPadding,
    paddingBottom: PROFILE_LAYOUT.footerBottomPadding,
  },
  previousButton: {
    width: PROFILE_LAYOUT.previousButtonWidth,
    minHeight: 52,
    borderRadius: radii.card,
  },
  nextButton: {
    minHeight: 52,
    flex: 1,
    borderRadius: radii.card,
  },
  savingButton: {
    backgroundColor: colors.primaryBusy,
  },
  savingLabel: {
    color: colors.surface,
  },
  retryButton: {
    minHeight: 36,
    alignSelf: 'flex-start',
    borderColor: colors.dangerText,
    borderRadius: 10,
    paddingHorizontal: 13,
  },
  retryLabel: {
    color: colors.dangerText,
    fontSize: 12.5,
  },
  modalOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 30,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(20, 28, 16, 0.5)',
    padding: 26,
  },
  modalCard: {
    width: '100%',
    gap: 10,
    borderRadius: 20,
    backgroundColor: colors.canvas,
    padding: 22,
  },
  modalCardCenter: {
    alignItems: 'center',
    padding: 24,
  },
  modalTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  modalMessage: {
    color: colors.textMuted,
    fontSize: 13.5,
    lineHeight: 21,
  },
  modalActions: {
    gap: spacing.sm,
    marginTop: 6,
  },
  exitLabel: {
    color: colors.textMuted,
    fontSize: 14,
  },
  doneMark: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: colors.primary,
  },
  doneMarkLabel: {
    color: colors.surface,
    fontSize: 22,
    fontWeight: '700',
  },
  doneTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '700',
  },
  doneMessage: {
    textAlign: 'center',
  },
  doneButton: {
    width: '100%',
    marginTop: spacing.sm,
  },
});
