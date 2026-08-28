/**
 * Read-only equipment variants from the reviewed catalog.
 *
 * This UI never changes the active routine or workout session. The backend
 * owns which equipment requirements and EQUIPMENT relationships are approved.
 * The action is available for any exercise with required equipment, while the
 * variant section is rendered only when reviewed variants exist.
 */

import { useEffect, useRef } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import type { Api } from '../../api/endpoints';
import { equipmentLabel } from '../../api/labels';
import type { ExerciseVariantsResponse } from '../../api/types';
import { useAsyncData } from '../../api/useAsync';
import { colors, spacing } from '../../components/theme';

type VariantApi = Partial<Pick<Api, 'getExerciseVariants'>>;

export function ExerciseVariantsAction({
  actionStyle,
  actionTextStyle,
  api,
  exerciseId,
  exerciseName,
  autoOpen = false,
  label = '장비',
  onOpen,
  presentation = 'pill',
}: {
  actionStyle?: StyleProp<ViewStyle>;
  actionTextStyle?: StyleProp<TextStyle>;
  api: VariantApi;
  exerciseId: string;
  exerciseName: string;
  autoOpen?: boolean;
  label?: string;
  onOpen: (response: ExerciseVariantsResponse) => void;
  presentation?: 'pill' | 'text';
}) {
  const getExerciseVariants = api.getExerciseVariants;
  const openedAutomatically = useRef(false);
  const { state, reload } = useAsyncData<ExerciseVariantsResponse>(
    (signal) =>
      getExerciseVariants
        ? getExerciseVariants(exerciseId, signal)
        : Promise.resolve(emptyVariants(exerciseId)),
    [getExerciseVariants, exerciseId],
  );

  useEffect(() => {
    if (
      !autoOpen ||
      openedAutomatically.current ||
      state.status !== 'ready' ||
      !hasRequiredEquipment(state.data.source_required_equipment_codes)
    ) {
      return;
    }

    openedAutomatically.current = true;
    onOpen(state.data);
  }, [autoOpen, onOpen, state]);

  // Supports a staggered frontend/backend rollout without inventing a
  // fallback endpoint or showing a control that cannot work.
  if (!getExerciseVariants) {
    return null;
  }

  if (state.status === 'loading') {
    return (
      <Text
        accessibilityLabel={`${exerciseName} 장비 안내 확인 중`}
        style={styles.loadingText}
        testID={`exercise-variants-loading-${exerciseId}`}
      >
        장비 확인 중…
      </Text>
    );
  }

  if (state.status === 'error') {
    return (
      <Pressable
        accessibilityHint={state.message}
        accessibilityLabel={`${exerciseName} 장비 안내 다시 확인`}
        accessibilityRole="button"
        onPress={reload}
        style={({ pressed }) => [
          presentation === 'pill' ? styles.action : styles.textAction,
          presentation === 'pill' && styles.retryAction,
          actionStyle,
          pressed && styles.pressed,
        ]}
      >
        <Text style={[styles.actionText, styles.retryText, actionTextStyle]}>
          다시 확인
        </Text>
      </Pressable>
    );
  }

  if (!hasRequiredEquipment(state.data.source_required_equipment_codes)) {
    return null;
  }

  return (
    <Pressable
      accessibilityLabel={`${exerciseName} ${label} 보기`}
      accessibilityRole="button"
      onPress={() => onOpen(state.data)}
      style={({ pressed }) => [
        presentation === 'pill' ? styles.action : styles.textAction,
        actionStyle,
        pressed && styles.pressed,
      ]}
      testID={`exercise-variants-action-${exerciseId}`}
    >
      <Text style={[styles.actionText, actionTextStyle]}>{label}</Text>
    </Pressable>
  );
}

export function ExerciseVariantsContent({
  response,
}: {
  response: ExerciseVariantsResponse;
}) {
  const hasVariants = response.items.length > 0;

  return (
    <View style={styles.content} testID="exercise-variants-content">
      <View style={styles.sourceCard}>
        <Text style={styles.sectionTitle}>원래 운동의 필요 장비</Text>
        <Text style={styles.equipmentText}>
          {equipmentSummary(response.source_required_equipment_codes)}
        </Text>
      </View>

      {hasVariants ? (
        <View style={styles.variantSection} testID="exercise-variants-list">
          <Text style={styles.intro}>
            장비가 없을 때 아래 방법으로 동작을 변형할 수 있어요.
          </Text>

          {response.items.map((item) => (
            <View key={item.exercise_id} style={styles.variantCard}>
              <Text style={styles.variantName}>{item.exercise_name}</Text>
              <Text style={styles.variantEquipment}>
                필요 장비: {equipmentSummary(item.required_equipment_codes)}
              </Text>
              <Text style={styles.summary}>{item.instruction_summary}</Text>
              {item.form_cues.map((cue, index) => (
                <View
                  key={`${item.exercise_id}-${index}`}
                  style={styles.cueRow}
                >
                  <Text style={styles.bullet}>·</Text>
                  <Text style={styles.cue}>{cue}</Text>
                </View>
              ))}
            </View>
          ))}

          <Text style={styles.notice}>
            이 안내는 운동을 교체하지 않으며 현재 루틴과 수행 기록도 바꾸지
            않아요.
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function emptyVariants(exerciseId: string): ExerciseVariantsResponse {
  return {
    source_exercise_id: exerciseId,
    source_required_equipment_codes: [],
    items: [],
    catalog_version: '',
    alternative_set_version: null,
  };
}

function equipmentSummary(codes: readonly string[]): string {
  const equipmentCodes = codes.filter((code) => code !== 'BODYWEIGHT');
  if (equipmentCodes.length === 0) {
    return '별도 장비 없음';
  }
  return equipmentCodes.map(equipmentLabel).join(', ');
}

function hasRequiredEquipment(codes: readonly string[]): boolean {
  return codes.some((code) => code !== 'BODYWEIGHT');
}

const styles = StyleSheet.create({
  action: {
    borderWidth: 1,
    borderColor: colors.greenBorder,
    borderRadius: 999,
    backgroundColor: colors.greenTint,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  retryAction: {
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
  },
  pressed: {
    opacity: 0.72,
  },
  actionText: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
  },
  textAction: {
    alignSelf: 'flex-start',
    justifyContent: 'center',
    minHeight: 32,
    paddingHorizontal: 0,
  },
  retryText: {
    color: colors.dangerText,
  },
  loadingText: {
    color: colors.textMuted,
    fontSize: 11,
  },
  content: {
    gap: spacing.md,
  },
  variantSection: {
    gap: spacing.md,
  },
  sourceCard: {
    gap: spacing.xs,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.lg,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  equipmentText: {
    color: colors.textSub,
    fontSize: 13,
  },
  intro: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
  },
  variantCard: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.greenBorder,
    borderRadius: 14,
    backgroundColor: colors.surface,
    padding: spacing.lg,
  },
  variantName: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  variantEquipment: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
  },
  summary: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
  },
  cueRow: {
    flexDirection: 'row',
    gap: 6,
  },
  bullet: {
    color: colors.greenText,
    fontSize: 13,
  },
  cue: {
    flex: 1,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  notice: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
});
