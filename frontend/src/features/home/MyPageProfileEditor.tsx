import { useRef, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  BODY_AREA_OPTIONS,
  equipmentLabel,
  experienceLevelLabel,
  locationLabel,
  primaryGoalLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type { MeProfile, ProfileSettingsUpdateRequest } from '../../api/types';
import { Button, InlineFeedback, TextField } from '../../components/primitives';
import { colors } from '../../components/theme';
import type { MyPageProfileField } from './myPageModel';

export type MyPageEditableField = MyPageProfileField | 'nickname';

type Props = {
  error?: string | null;
  field: MyPageEditableField;
  onChange: (body: ProfileSettingsUpdateRequest) => void;
  onClose: () => void;
  pending?: boolean;
  profile: MeProfile;
};

const TITLES: Record<MyPageEditableField, string> = {
  nickname: '닉네임 수정',
  date_of_birth: '나이 수정',
  timezone: '시간대 수정',
  primary_goal_code: '운동 목표 수정',
  experience_level_code: '운동 경험 수정',
  preferred_exercise_type_codes: '선호 운동 수정',
  available_location_codes: '운동 장소 수정',
  equipment_codes: '장비 수정',
  default_requested_duration_minutes: '희망 시간 수정',
  desired_weekly_workout_count: '주간 목표 수정',
  attention_area_codes: '주의 부위 수정',
};

const GOAL_OPTIONS = [{ code: 'GENERAL_FITNESS', label: '건강 유지' }] as const;
const EXPERIENCE_OPTIONS = [{ code: 'BEGINNER', label: '입문·초급' }] as const;
const TRAINING_OPTIONS = ['STRENGTH', 'CARDIO', 'MOBILITY'] as const;
const LOCATION_OPTIONS = ['HOME', 'GYM', 'OUTDOOR'] as const;
const EQUIPMENT_OPTIONS = [
  'BODYWEIGHT',
  'DUMBBELL',
  'BARBELL',
  'KETTLEBELL',
  'CABLE_MACHINE',
  'MACHINE',
  'HOUSEHOLD_WEIGHT',
  'BENCH',
  'PULL_UP_BAR',
  'RESISTANCE_BAND',
  'MAT',
  'STABILITY_BALL',
  'CHAIR',
] as const;

export function MyPageProfileEditor({
  error = null,
  field,
  onChange,
  onClose,
  pending = false,
  profile,
}: Props) {
  return (
    <Modal animationType="fade" onRequestClose={onClose} transparent visible>
      <View accessibilityViewIsModal style={styles.overlay}>
        <View style={styles.sheet}>
          <View style={styles.headingRow}>
            <View style={styles.headingCopy}>
              <Text accessibilityRole="header" style={styles.title}>
                {TITLES[field]}
              </Text>
              <Text style={styles.description}>
                변경하면 별도의 저장 버튼 없이 바로 반영돼요.
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
        </View>
      </View>
    </Modal>
  );
}

function EditorBody({
  field,
  onChange,
  pending = false,
  profile,
}: Pick<Props, 'field' | 'onChange' | 'pending' | 'profile'>) {
  if (field === 'nickname') {
    return (
      <ImmediateTextEditor
        accessibilityLabel="닉네임 입력"
        initialValue={profile.nickname}
        onCommit={(nickname) => onChange({ nickname })}
        pending={pending}
        placeholder="닉네임"
      />
    );
  }

  if (field === 'date_of_birth') {
    return (
      <ImmediateTextEditor
        accessibilityLabel="생년월일 입력"
        helper="개인정보 보호를 위해 기존 생년월일은 표시하지 않아요. YYYY-MM-DD 형식으로 새 값을 입력하면 나이가 갱신돼요."
        initialValue=""
        onCommit={(date_of_birth) => onChange({ date_of_birth })}
        pending={pending}
        placeholder="예: 1997-08-19"
      />
    );
  }

  if (field === 'timezone') {
    return (
      <ImmediateTextEditor
        accessibilityLabel="시간대 입력"
        helper="IANA 시간대 이름을 입력해주세요."
        initialValue={profile.timezone}
        onCommit={(timezone) => onChange({ timezone })}
        pending={pending}
        placeholder="예: Asia/Seoul"
      />
    );
  }

  if (field === 'primary_goal_code') {
    return (
      <OptionList
        current={[profile.primary_goal_code]}
        disabled={pending}
        options={withCurrentOption(
          GOAL_OPTIONS,
          profile.primary_goal_code,
          primaryGoalLabel(profile.primary_goal_code),
        )}
        onPress={(code) => onChange({ primary_goal_code: code })}
      />
    );
  }

  if (field === 'experience_level_code') {
    return (
      <OptionList
        current={[profile.experience_level_code]}
        disabled={pending}
        options={withCurrentOption(
          EXPERIENCE_OPTIONS,
          profile.experience_level_code,
          experienceLevelLabel(profile.experience_level_code),
        )}
        onPress={(code) => onChange({ experience_level_code: code })}
      />
    );
  }

  if (field === 'preferred_exercise_type_codes') {
    return (
      <OptionList
        current={profile.preferred_exercise_type_codes}
        disabled={pending}
        multiple
        options={TRAINING_OPTIONS.map((code) => ({
          code,
          label: trainingTypeLabel(code),
        }))}
        onPress={(code) =>
          onChange({
            preferred_exercise_type_codes: toggled(
              profile.preferred_exercise_type_codes,
              code,
            ),
          })
        }
      />
    );
  }

  if (field === 'available_location_codes') {
    return (
      <OptionList
        current={profile.available_location_codes}
        disabled={pending}
        multiple
        options={LOCATION_OPTIONS.map((code) => ({
          code,
          label: locationLabel(code),
        }))}
        onPress={(code) => {
          const next = toggled(profile.available_location_codes, code);
          if (next.length === 0) return;
          onChange({
            available_location_codes: next,
            preferred_location_code: next.includes(
              profile.preferred_location_code,
            )
              ? profile.preferred_location_code
              : next[0],
          });
        }}
      />
    );
  }

  if (field === 'equipment_codes') {
    return (
      <OptionList
        current={profile.equipment_codes}
        disabled={pending}
        multiple
        options={EQUIPMENT_OPTIONS.map((code) => ({
          code,
          label: equipmentLabel(code),
        }))}
        onPress={(code) => {
          const next = toggled(profile.equipment_codes, code);
          if (next.length > 0) onChange({ equipment_codes: next });
        }}
      />
    );
  }

  if (field === 'attention_area_codes') {
    return (
      <OptionList
        current={profile.attention_area_codes}
        disabled={pending}
        multiple
        options={BODY_AREA_OPTIONS}
        onPress={(code) =>
          onChange({
            attention_area_codes: toggled(profile.attention_area_codes, code),
          })
        }
      />
    );
  }

  if (field === 'default_requested_duration_minutes') {
    return (
      <ImmediateStepper
        label="희망 운동 시간"
        max={120}
        min={10}
        onChange={(default_requested_duration_minutes) =>
          onChange({ default_requested_duration_minutes })
        }
        pending={pending}
        step={5}
        unit="분"
        value={profile.default_requested_duration_minutes}
      />
    );
  }

  return (
    <ImmediateStepper
      label="주간 목표"
      max={7}
      min={1}
      onChange={(desired_weekly_workout_count) =>
        onChange({ desired_weekly_workout_count })
      }
      pending={pending}
      step={1}
      unit="회"
      value={profile.desired_weekly_workout_count}
    />
  );
}

function ImmediateTextEditor({
  accessibilityLabel,
  helper,
  initialValue,
  onCommit,
  pending,
  placeholder,
}: {
  accessibilityLabel: string;
  helper?: string;
  initialValue: string;
  onCommit: (value: string) => void;
  pending: boolean;
  placeholder: string;
}) {
  const [value, setValue] = useState(initialValue);
  const lastCommitted = useRef(initialValue);
  const commit = () => {
    const normalized = value.trim();
    if (!normalized || normalized === lastCommitted.current || pending) return;
    lastCommitted.current = normalized;
    onCommit(normalized);
  };

  return (
    <View style={styles.textEditor}>
      {helper ? <Text style={styles.helper}>{helper}</Text> : null}
      <TextField
        accessibilityLabel={accessibilityLabel}
        autoCapitalize="none"
        editable={!pending}
        onBlur={commit}
        onChangeText={setValue}
        onSubmitEditing={commit}
        placeholder={placeholder}
        returnKeyType="done"
        value={value}
      />
    </View>
  );
}

function OptionList({
  current,
  disabled,
  multiple = false,
  onPress,
  options,
}: {
  current: readonly string[];
  disabled: boolean;
  multiple?: boolean;
  onPress: (code: string) => void;
  options: readonly { code: string; label: string }[];
}) {
  return (
    <View style={styles.options}>
      {options.map((option) => {
        const selected = current.includes(option.code);
        return (
          <Pressable
            key={option.code}
            accessibilityRole={multiple ? 'checkbox' : 'radio'}
            accessibilityState={{ checked: selected, disabled }}
            disabled={disabled || (!multiple && selected)}
            onPress={() => onPress(option.code)}
            style={[styles.option, selected && styles.optionSelected]}
          >
            <Text
              style={[styles.optionText, selected && styles.optionTextSelected]}
            >
              {option.label}
            </Text>
            <Text style={styles.optionMark}>{selected ? '✓' : ''}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function ImmediateStepper({
  label,
  max,
  min,
  onChange,
  pending,
  step,
  unit,
  value,
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  pending: boolean;
  step: number;
  unit: string;
  value: number;
}) {
  return (
    <View style={styles.stepper}>
      <Button
        disabled={pending || value - step < min}
        label={`${label} 줄이기`}
        onPress={() => onChange(Math.max(min, value - step))}
        tone="secondary"
      />
      <Text style={styles.stepperValue}>
        {value}
        {unit}
      </Text>
      <Button
        disabled={pending || value + step > max}
        label={`${label} 늘리기`}
        onPress={() => onChange(Math.min(max, value + step))}
        tone="secondary"
      />
    </View>
  );
}

function toggled(values: readonly string[], code: string): string[] {
  return values.includes(code)
    ? values.filter((value) => value !== code)
    : [...values, code];
}

function withCurrentOption(
  options: readonly { code: string; label: string }[],
  currentCode: string,
  currentLabel: string,
): readonly { code: string; label: string }[] {
  return options.some((option) => option.code === currentCode)
    ? options
    : [{ code: currentCode, label: currentLabel }, ...options];
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20,28,16,0.5)',
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
  textEditor: { gap: 10 },
  helper: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  pending: { color: colors.textMuted, fontSize: 12, textAlign: 'center' },
  options: { gap: 9 },
  option: {
    minHeight: 50,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#D8E3C8',
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
  },
  optionSelected: { borderColor: colors.primary, backgroundColor: '#F1F6E7' },
  optionText: { color: colors.text, fontSize: 14, fontWeight: '700' },
  optionTextSelected: { color: '#3E7A32' },
  optionMark: { color: colors.primary, fontSize: 16, fontWeight: '900' },
  stepper: { gap: 12, alignItems: 'stretch' },
  stepperValue: {
    color: colors.text,
    fontSize: 28,
    fontWeight: '900',
    textAlign: 'center',
  },
});
