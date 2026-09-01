/**
 * Reviewed posture and instruction content for one exercise block.
 *
 * This is catalog content, not posture detection: the copy comes from the
 * server's reviewed instruction fields and the app makes no judgement about how
 * the movement is being performed.
 */

import { useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, Text, View } from 'react-native';

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
    return <LoadingState label="자세 정보를 불러오는 중이에요" />;
  }
  if (state.status === 'error') {
    return <ErrorState message={state.message} onRetry={reload} />;
  }

  const detail = state.data;

  return (
    <View style={styles.container} testID="exercise-posture-guide">
      <ExerciseMedia
        exerciseName={detail.exercise_name}
        mediaReference={detail.media_url ?? null}
      />

      <View style={styles.instructions} testID="exercise-instruction-content">
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
    </View>
  );
}

/**
 * The backend resolves the canonical media key into a short-lived media_url.
 * Production only loads HTTPS URLs; the development gallery additionally
 * accepts Metro's localhost asset URL. Canonical S3 object keys stay inert.
 */
function ExerciseMedia({
  exerciseName,
  mediaReference,
}: {
  exerciseName: string;
  mediaReference: string | null;
}) {
  const isProductionMedia =
    mediaReference !== null && /^https:\/\//i.test(mediaReference);
  const isLocalPreviewMedia =
    __DEV__ &&
    mediaReference !== null &&
    (/^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//i.test(mediaReference) ||
      mediaReference.startsWith('/'));
  const mediaUri =
    isProductionMedia || isLocalPreviewMedia ? mediaReference : null;
  const [loadedUri, setLoadedUri] = useState<string | null>(null);
  const [failedUri, setFailedUri] = useState<string | null>(null);
  const canRender = mediaUri !== null && failedUri !== mediaUri;

  return (
    <View
      accessibilityLabel={`${exerciseName} 운동 GIF 영역`}
      style={styles.mediaSlot}
      testID="exercise-media-slot"
    >
      {canRender ? (
        <>
          <Image
            accessibilityLabel={`${exerciseName} 운동 자세 GIF`}
            accessibilityRole="image"
            onError={() => setFailedUri(mediaUri)}
            onLoad={() => setLoadedUri(mediaUri)}
            onLoadStart={() =>
              setLoadedUri((current) => (current === mediaUri ? current : null))
            }
            resizeMode="contain"
            source={{ uri: mediaUri }}
            style={styles.mediaImage}
            testID="exercise-media-image"
          />
          {loadedUri !== mediaUri ? (
            <View style={styles.mediaStatus} testID="exercise-media-loading">
              <ActivityIndicator color={colors.greenText} />
              <Text style={styles.mediaStatusText}>운동 GIF 불러오는 중</Text>
            </View>
          ) : null}
        </>
      ) : (
        <View style={styles.mediaStatus} testID="exercise-media-placeholder">
          <Text style={styles.mediaMark}>GIF</Text>
          <Text style={styles.mediaStatusText}>
            {mediaUri === null
              ? '운동 GIF가 준비되면 이곳에 표시돼요.'
              : '운동 GIF를 불러오지 못했어요.'}
          </Text>
        </View>
      )}
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
  mediaSlot: {
    width: '100%',
    maxWidth: 320,
    aspectRatio: 1,
    alignSelf: 'center',
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 20,
    backgroundColor: colors.surface,
  },
  mediaImage: {
    width: '100%',
    height: '100%',
  },
  mediaStatus: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    padding: spacing.lg,
  },
  mediaMark: {
    color: colors.greenText,
    fontSize: 18,
    fontWeight: '800',
  },
  mediaStatusText: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
  instructions: {
    gap: spacing.sm,
  },
  summary: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 24,
  },
  areas: {
    color: colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  cueRow: {
    flexDirection: 'row',
    gap: 6,
  },
  bullet: {
    color: colors.greenText,
    fontSize: 15,
    lineHeight: 23,
  },
  cue: {
    flex: 1,
    color: colors.textSub,
    fontSize: 15,
    lineHeight: 23,
  },
});
