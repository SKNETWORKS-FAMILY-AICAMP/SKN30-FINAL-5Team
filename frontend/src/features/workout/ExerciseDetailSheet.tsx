/**
 * Reviewed posture and instruction content for one exercise block.
 *
 * This is catalog content, not posture detection: the copy comes from the
 * server's reviewed instruction fields and the app makes no judgement about how
 * the movement is being performed.
 */

import { StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { bodyAreaLabel } from '../../api/labels';
import type { ExerciseDetailResponse } from '../../api/types';
import { useAsyncData } from '../../api/useAsync';
import { ErrorState, LoadingState } from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

export function ExerciseDetailSheet({
  api,
  exerciseId,
}: {
  api: Pick<Api, 'getExercise'>;
  exerciseId: string;
}) {
  const { state, reload } = useAsyncData<ExerciseDetailResponse>(
    (signal) => api.getExercise(exerciseId, signal),
    [api, exerciseId],
  );

  if (state.status === 'loading') {
    return <LoadingState label="설명을 불러오는 중이에요" />;
  }
  if (state.status === 'error') {
    return <ErrorState message={state.message} onRetry={reload} />;
  }

  const detail = state.data;

  return (
    <View style={styles.container}>
      <Text style={styles.summary}>{detail.instruction_summary}</Text>

      {detail.primary_body_area_codes.length > 0 ? (
        <Text style={styles.areas}>
          주요 부위:{' '}
          {detail.primary_body_area_codes.map(bodyAreaLabel).join(', ')}
        </Text>
      ) : null}

      {detail.form_cues.map((cue) => (
        <View key={cue} style={styles.cueRow}>
          <Text style={styles.bullet}>·</Text>
          <Text style={styles.cue}>{cue}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.sm,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.lg,
  },
  summary: {
    color: colors.text,
    fontSize: 13,
    lineHeight: 20,
  },
  areas: {
    color: colors.textMuted,
    fontSize: 12,
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
});
