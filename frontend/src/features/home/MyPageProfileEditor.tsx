import { useState } from 'react';
import {
  type GestureResponderEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  equipmentLabel,
  experienceLevelLabel,
  EXTENDED_BODY_AREA_OPTIONS,
  locationLabel,
  primaryGoalLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  MeProfile,
  ProfileSettingsUpdateRequest,
  SexCode,
} from '../../api/types';
import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import {
  ONBOARDING_DURATION,
  ONBOARDING_EQUIPMENT_OPTIONS,
  ONBOARDING_EXERCISE_TYPE_OPTIONS,
  ONBOARDING_EXPERIENCE_OPTIONS,
  ONBOARDING_GOAL_OPTIONS,
  ONBOARDING_LOCATION_OPTIONS,
  ONBOARDING_WEEKLY_COUNT,
} from '../onboarding/onboardingOptions';
import {
  BirthDateField,
  latestEligibleBirthdateIso,
} from '../onboarding/BirthDateField';
import type { MyPageProfileField } from './myPageModel';

export type MyPageEditableField = MyPageProfileField | 'basic_profile';

type Props = {
  error?: string | null;
  field: MyPageEditableField;
  onChange: (body: ProfileSettingsUpdateRequest) => void;
  onClose: () => void;
  pending?: boolean;
  profile: MeProfile;
};

const TITLES: Record<MyPageEditableField, string> = {
  basic_profile: '기본 정보 수정',
  primary_goal_code: '운동 목표 수정',
  experience_level_code: '운동 경험 수정',
  preferred_exercise_type_codes: '선호 운동 수정',
  available_location_codes: '운동 장소 수정',
  equipment_codes: '장비 수정',
  default_requested_duration_minutes: '희망 시간 수정',
  desired_weekly_workout_count: '주간 목표 수정',
  attention_area_codes: '주의 부위 수정',
};

export function MyPageProfileEditor({
  error = null,
  field,
  onChange,
  onClose,
  pending = false,
  profile,
}: Props) {
  const stopPropagation = (event: GestureResponderEvent) =>
    event.stopPropagation();

  return (
    <Pressable
      accessibilityViewIsModal
      onPress={onClose}
      style={styles.overlay}
      testID="profile-editor-backdrop"
    >
      <Pressable
        onPress={stopPropagation}
        style={styles.sheet}
        testID="profile-editor-sheet"
      >
        <View style={styles.headingRow}>
          <View style={styles.headingCopy}>
            <Text accessibilityRole="header" style={styles.title}>
              {TITLES[field]}
            </Text>
            <Text style={styles.description}>
              온보딩과 같은 방식으로 선택하면 바로 반영돼요.
            </Text>
          </View>
          <Pressable
            accessibilityLabel="프로필 편집 닫기"
            accessibilityRole="button"
            onPress={onClose}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>

        <ScrollView
          contentContainerStyle={styles.editorContent}
          keyboardShouldPersistTaps="handled"
        >
          <EditorBody
            field={field}
            onChange={onChange}
            pending={pending}
            profile={profile}
          />
          {pending ? <Text style={styles.pending}>저장 중…</Text> : null}
          {error ? <InlineFeedback message={error} tone="error" /> : null}
        </ScrollView>
      </Pressable>
    </Pressable>
  );
}

function EditorBody({
  field,
  onChange,
  pending = false,
  profile,
}: Pick<Props, 'field' | 'onChange' | 'pending' | 'profile'>) {
  if (field === 'basic_profile') {
    return (
      <BasicProfileEditor
        onChange={onChange}
        pending={pending}
        profile={profile}
      />
    );
  }

  if (field === 'primary_goal_code') {
    return (
      <ChoiceCard>
        {mergeDescriptionOptions(
          ONBOARDING_GOAL_OPTIONS,
          profile.primary_goal_code,
          primaryGoalLabel,
        ).map((option) => (
          <DescriptionOption
            key={option.code}
            description={option.description}
            disabled={pending}
            label={option.label}
            selected={profile.primary_goal_code === option.code}
            onPress={() => onChange({ primary_goal_code: option.code })}
          />
        ))}
      </ChoiceCard>
    );
  }

  if (field === 'experience_level_code') {
    return (
      <ChoiceCard>
        {mergeDescriptionOptions(
          ONBOARDING_EXPERIENCE_OPTIONS,
          profile.experience_level_code,
          experienceLevelLabel,
        ).map((option) => (
          <DescriptionOption
            key={option.code}
            description={option.description}
            disabled={pending}
            label={option.label}
            selected={profile.experience_level_code === option.code}
            onPress={() => onChange({ experience_level_code: option.code })}
          />
        ))}
      </ChoiceCard>
    );
  }

  if (field === 'preferred_exercise_type_codes') {
    return (
      <MultipleChoiceEditor
        allowEmpty
        disabled={pending}
        initial={profile.preferred_exercise_type_codes}
        options={mergeOptions(
          ONBOARDING_EXERCISE_TYPE_OPTIONS,
          profile.preferred_exercise_type_codes,
          trainingTypeLabel,
        )}
        onChange={(preferred_exercise_type_codes) =>
          onChange({ preferred_exercise_type_codes })
        }
      />
    );
  }

  if (field === 'available_location_codes') {
    return (
      <LocationEditor
        disabled={pending}
        initial={profile.available_location_codes}
        initialPreferred={profile.preferred_location_code}
        options={mergeOptions(
          ONBOARDING_LOCATION_OPTIONS,
          profile.available_location_codes,
          locationLabel,
        )}
        onChange={(available_location_codes, preferred_location_code) =>
          onChange({ available_location_codes, preferred_location_code })
        }
      />
    );
  }

  if (field === 'equipment_codes') {
    return (
      <MultipleChoiceEditor
        disabled={pending}
        initial={profile.equipment_codes}
        options={mergeOptions(
          ONBOARDING_EQUIPMENT_OPTIONS,
          profile.equipment_codes,
          equipmentLabel,
        )}
        onChange={(equipment_codes) => onChange({ equipment_codes })}
      />
    );
  }

  if (field === 'attention_area_codes') {
    return (
      <AttentionAreaEditor
        disabled={pending}
        initial={profile.attention_area_codes}
        onChange={(attention_area_codes) => onChange({ attention_area_codes })}
      />
    );
  }

  if (field === 'default_requested_duration_minutes') {
    return (
      <ImmediateStepper
        decreaseLabel="운동 시간 10분 줄이기"
        increaseLabel="운동 시간 10분 늘리기"
        max={ONBOARDING_DURATION.max}
        min={ONBOARDING_DURATION.min}
        onChange={(default_requested_duration_minutes) =>
          onChange({ default_requested_duration_minutes })
        }
        pending={pending}
        step={ONBOARDING_DURATION.step}
        suffix="분"
        value={profile.default_requested_duration_minutes}
      />
    );
  }

  return (
    <ImmediateStepper
      decreaseLabel="주간 운동 횟수 1회 줄이기"
      increaseLabel="주간 운동 횟수 1회 늘리기"
      max={ONBOARDING_WEEKLY_COUNT.max}
      min={ONBOARDING_WEEKLY_COUNT.min}
      onChange={(desired_weekly_workout_count) =>
        onChange({ desired_weekly_workout_count })
      }
      pending={pending}
      prefix="주 "
      step={ONBOARDING_WEEKLY_COUNT.step}
      suffix="회"
      value={profile.desired_weekly_workout_count}
    />
  );
}

const BASIC_SEX_OPTIONS = [
  { code: 'FEMALE', label: '여성' },
  { code: 'MALE', label: '남성' },
] as const satisfies readonly { code: SexCode; label: string }[];

function BasicProfileEditor({
  onChange,
  pending,
  profile,
}: {
  onChange: (body: ProfileSettingsUpdateRequest) => void;
  pending: boolean;
  profile: MeProfile;
}) {
  const [nickname, setNickname] = useState(profile.nickname);
  const [dateOfBirth, setDateOfBirth] = useState(latestEligibleBirthdateIso);
  const [dateOfBirthChanged, setDateOfBirthChanged] = useState(false);
  const [sexCode, setSexCode] = useState<SexCode | null>(null);
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const nicknameError =
    nickname.trim().length < 1 || nickname.trim().length > 64
      ? '닉네임은 1~64자로 입력해주세요.'
      : null;
  const heightError = validateOptionalNumber(heightCm, 80, 250, '키');
  const weightError = validateOptionalNumber(weightKg, 25, 300, '체중');
  const hasChanges =
    nickname.trim() !== profile.nickname ||
    dateOfBirthChanged ||
    sexCode !== null ||
    heightCm !== '' ||
    weightKg !== '';
  const invalid = Boolean(nicknameError || heightError || weightError);

  const save = () => {
    setSubmitted(true);
    if (!hasChanges || invalid || pending) return;
    const body: ProfileSettingsUpdateRequest = {};
    const normalizedNickname = nickname.trim();
    if (normalizedNickname !== profile.nickname) {
      body.nickname = normalizedNickname;
    }
    if (dateOfBirthChanged) body.date_of_birth = dateOfBirth;
    if (sexCode) body.sex_code = sexCode;
    if (heightCm) body.height_cm = Number(heightCm);
    if (weightKg) body.weight_kg = Number(weightKg);
    onChange(body);
  };

  return (
    <View style={styles.basicForm}>
      <InlineFeedback
        message="생년월일·성별·키·체중은 개인정보 보호를 위해 기존 값을 다시 보여주지 않아요. 바꿀 항목만 입력해주세요."
        tone="warning"
      />
      <TextField
        accessibilityLabel="닉네임 입력"
        editable={!pending}
        error={submitted && nicknameError ? nicknameError : undefined}
        label="닉네임"
        maxLength={64}
        onChangeText={setNickname}
        value={nickname}
      />
      <BirthDateField
        disabled={pending}
        onChange={(value) => {
          setDateOfBirth(value);
          setDateOfBirthChanged(true);
        }}
        value={dateOfBirth}
      />
      <View style={styles.basicGroup}>
        <Text style={styles.basicLabel}>성별</Text>
        <View style={styles.basicChoices}>
          {BASIC_SEX_OPTIONS.map((option) => (
            <ChipOption
              key={option.code}
              disabled={pending}
              label={option.label}
              onPress={() => setSexCode(option.code)}
              selected={sexCode === option.code}
            />
          ))}
        </View>
      </View>
      <TextField
        accessibilityLabel="키 입력"
        editable={!pending}
        error={submitted && heightError ? heightError : undefined}
        inputMode="decimal"
        label="키(cm)"
        onChangeText={setHeightCm}
        placeholder="80~250"
        value={heightCm}
      />
      <TextField
        accessibilityLabel="체중 입력"
        editable={!pending}
        error={submitted && weightError ? weightError : undefined}
        inputMode="decimal"
        label="체중(kg)"
        onChangeText={setWeightKg}
        placeholder="25~300"
        value={weightKg}
      />
      <Button
        disabled={!hasChanges || pending}
        label={pending ? '저장 중…' : '기본 정보 저장'}
        onPress={save}
      />
    </View>
  );
}

function validateOptionalNumber(
  value: string,
  min: number,
  max: number,
  label: string,
): string | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max
    ? null
    : `${label}는 ${min}~${max} 범위로 입력해주세요.`;
}

function MultipleChoiceEditor({
  allowEmpty = false,
  disabled,
  initial,
  onChange,
  options,
}: {
  allowEmpty?: boolean;
  disabled: boolean;
  initial: readonly string[];
  onChange: (codes: string[]) => void;
  options: readonly ChoiceOption[];
}) {
  const [selected, setSelected] = useState([...initial]);

  return (
    <ChoiceCard>
      {options.map((option) => (
        <ChipOption
          key={option.code}
          disabled={disabled}
          label={option.label}
          selected={selected.includes(option.code)}
          onPress={() => {
            const next = toggle(selected, option.code);
            if (!allowEmpty && next.length === 0) return;
            setSelected(next);
            onChange(next);
          }}
        />
      ))}
    </ChoiceCard>
  );
}

function LocationEditor({
  disabled,
  initial,
  initialPreferred,
  onChange,
  options,
}: {
  disabled: boolean;
  initial: readonly string[];
  initialPreferred: string;
  onChange: (available: string[], preferred: string) => void;
  options: readonly ChoiceOption[];
}) {
  const [selected, setSelected] = useState([...initial]);
  const [preferred, setPreferred] = useState(initialPreferred);

  return (
    <View style={styles.locationEditor}>
      <ChoiceCard>
        {options.map((option) => (
          <ChipOption
            key={option.code}
            disabled={disabled}
            label={option.label}
            selected={selected.includes(option.code)}
            onPress={() => {
              const next = toggle(selected, option.code);
              if (next.length === 0) return;
              const nextPreferred = next.includes(preferred)
                ? preferred
                : (next[0] ?? preferred);
              setSelected(next);
              setPreferred(nextPreferred);
              onChange(next, nextPreferred);
            }}
          />
        ))}
      </ChoiceCard>
      <View style={styles.basicGroup}>
        <Text style={styles.basicLabel}>주로 운동할 장소</Text>
        {options
          .filter((option) => selected.includes(option.code))
          .map((option) => (
            <DescriptionOption
              key={option.code}
              description="운동 계획에서 우선 적용해요."
              disabled={disabled}
              label={option.label}
              selected={preferred === option.code}
              onPress={() => {
                setPreferred(option.code);
                onChange(selected, option.code);
              }}
            />
          ))}
      </View>
    </View>
  );
}

function AttentionAreaEditor({
  disabled,
  initial,
  onChange,
}: {
  disabled: boolean;
  initial: readonly string[];
  onChange: (codes: string[]) => void;
}) {
  const [hasAreas, setHasAreas] = useState(initial.length > 0);
  const [selected, setSelected] = useState([...initial]);
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    initial.some((code) =>
      EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );
  const selectableCodes = new Set<string>(
    [...DEFAULT_BODY_AREA_OPTIONS, ...EXTENDED_BODY_AREA_OPTIONS].map(
      (option) => option.code,
    ),
  );
  const legacySelected = selected.filter((code) => !selectableCodes.has(code));

  const toggleSelected = (code: string) => {
    const next = toggle(selected, code);
    setSelected(next);
    onChange(next);
  };

  return (
    <ChoiceCard>
      <ChipOption
        disabled={disabled}
        grow
        label="없어요"
        selected={!hasAreas}
        onPress={() => {
          setHasAreas(false);
          setSelected([]);
          if (selected.length > 0) onChange([]);
        }}
      />
      <ChipOption
        disabled={disabled}
        grow
        label="있어요"
        selected={hasAreas}
        onPress={() => setHasAreas(true)}
      />
      {hasAreas ? (
        <View style={styles.painSection}>
          <Text style={styles.painSectionTitle}>통증 부위</Text>
          <View style={styles.painChoices}>
            {DEFAULT_BODY_AREA_OPTIONS.map((option) => (
              <ChipOption
                key={option.code}
                disabled={disabled}
                label={option.label}
                selected={selected.includes(option.code)}
                onPress={() => toggleSelected(option.code)}
              />
            ))}
            <ChipOption
              disabled={disabled}
              label={showExtendedAreas ? '다른 부위 접기' : '다른 부위 더 보기'}
              selected={showExtendedAreas}
              onPress={() => setShowExtendedAreas((visible) => !visible)}
            />
            {showExtendedAreas
              ? EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                  <ChipOption
                    key={option.code}
                    disabled={disabled}
                    label={option.label}
                    selected={selected.includes(option.code)}
                    onPress={() => toggleSelected(option.code)}
                  />
                ))
              : null}
          </View>
          {legacySelected.length > 0 ? (
            <View style={styles.painSection}>
              <Text style={styles.painSectionTitle}>
                이전에 저장된 부위 (해제만 가능)
              </Text>
              <View style={styles.painChoices}>
                {legacySelected.map((code) => (
                  <ChipOption
                    key={code}
                    disabled={disabled}
                    label={bodyAreaLabel(code)}
                    selected
                    onPress={() => toggleSelected(code)}
                  />
                ))}
              </View>
            </View>
          ) : null}
        </View>
      ) : null}
    </ChoiceCard>
  );
}

function ImmediateStepper({
  decreaseLabel,
  increaseLabel,
  max,
  min,
  onChange,
  pending,
  prefix = '',
  step,
  suffix,
  value,
}: {
  decreaseLabel: string;
  increaseLabel: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  pending: boolean;
  prefix?: string;
  step: number;
  suffix: string;
  value: number;
}) {
  const [current, setCurrent] = useState(value);
  const canDecrease = !pending && current > min;
  const canIncrease = !pending && current < max;
  const update = (next: number) => {
    setCurrent(next);
    onChange(next);
  };

  return (
    <Card style={styles.counterCard}>
      <Pressable
        accessibilityLabel={decreaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canDecrease }}
        disabled={!canDecrease}
        onPress={() => update(Math.max(min, current - step))}
        style={[
          styles.counterButton,
          !canDecrease && styles.counterButtonDisabled,
        ]}
      >
        <Text style={styles.counterButtonText}>−</Text>
      </Pressable>
      <Text accessibilityLiveRegion="polite" style={styles.counterValue}>
        {prefix}
        {current}
        {suffix}
      </Text>
      <Pressable
        accessibilityLabel={increaseLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canIncrease }}
        disabled={!canIncrease}
        onPress={() => update(Math.min(max, current + step))}
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

type ChoiceOption = { code: string; label: string };

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function ChipOption({
  disabled,
  grow = false,
  label,
  onPress,
  selected,
}: {
  disabled: boolean;
  grow?: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected, disabled }}
      disabled={disabled}
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
  disabled,
  label,
  onPress,
  selected,
}: {
  description: string;
  disabled: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected, disabled }}
      disabled={disabled || selected}
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

function toggle(values: readonly string[], code: string): string[] {
  return values.includes(code)
    ? values.filter((value) => value !== code)
    : [...values, code];
}

function mergeOptions(
  options: readonly ChoiceOption[],
  current: readonly string[],
  labelFor: (code: string) => string,
): readonly ChoiceOption[] {
  const known = new Set(options.map((option) => option.code));
  return [
    ...options,
    ...current
      .filter((code) => !known.has(code))
      .map((code) => ({ code, label: labelFor(code) })),
  ];
}

function mergeDescriptionOptions(
  options: readonly { code: string; label: string; description: string }[],
  current: string,
  labelFor: (code: string) => string,
): readonly { code: string; label: string; description: string }[] {
  return options.some((option) => option.code === current)
    ? options
    : [
        { code: current, label: labelFor(current), description: '현재 선택' },
        ...options,
      ];
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20,28,16,0.5)',
    zIndex: 30,
    elevation: 30,
  },
  sheet: {
    maxHeight: '82%',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    backgroundColor: colors.canvas,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 28,
  },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  headingCopy: { flex: 1, gap: 5 },
  title: { color: colors.text, fontSize: 19, fontWeight: '800' },
  description: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  closeButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: colors.surface,
  },
  closeText: { color: colors.text, fontSize: 25, lineHeight: 26 },
  editorContent: { gap: 14, paddingTop: 20 },
  basicForm: { gap: spacing.md },
  basicGroup: { gap: spacing.sm },
  basicLabel: { color: colors.textMuted, fontSize: 13, fontWeight: '600' },
  basicChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  locationEditor: { gap: spacing.md },
  pending: { color: colors.textMuted, fontSize: 12, textAlign: 'center' },
  choiceCard: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
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
  descriptionTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  descriptionText: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  descriptionTextSelected: { color: 'rgba(255, 255, 255, 0.75)' },
  painSection: {
    width: '100%',
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  painSectionTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  painChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
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
});
