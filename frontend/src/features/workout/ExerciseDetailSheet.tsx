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
import {
  bodyAreaLabel,
  bodyFocusLabel,
  equipmentLabel,
} from '../../api/labels';
import type {
  ExerciseDetailResponse,
  GymEquipmentStartingGuide,
  HouseholdEquipmentGuide,
} from '../../api/types';
import { useAsyncData } from '../../api/useAsync';
import { ErrorState, LoadingState } from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

export function ExerciseDetailSheet({
  api,
  exerciseId,
  guideContext,
}: {
  api: Pick<Api, 'getExercise'>;
  exerciseId: string;
  guideContext?: ExerciseGuideContext;
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
  const instructionSteps = detail.instruction_steps ?? [];
  const cautions = detail.cautions ?? detail.form_cues;
  const equipmentGuideSection = selectEquipmentGuideSection(
    detail,
    guideContext,
  );
  const representativeFocus = detail.body_focus_code
    ? bodyFocusLabel(detail.body_focus_code)
    : detail.primary_body_area_codes.map(bodyAreaLabel).join(', ');

  return (
    <View style={styles.container} testID="exercise-posture-guide">
      <ExerciseMedia
        exerciseName={detail.exercise_name}
        mediaReference={detail.media_url ?? null}
      />

      <View style={styles.instructions} testID="exercise-instruction-content">
        {representativeFocus ? (
          <View style={styles.section} testID="exercise-body-focus">
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              사용 근육
            </Text>
            <Text style={styles.areas}>{representativeFocus}</Text>
          </View>
        ) : null}

        {detail.body_focus_code && detail.primary_body_area_codes.length > 0 ? (
          <View style={styles.section} testID="exercise-primary-areas">
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              주의 부위
            </Text>
            <Text style={styles.areas}>
              {detail.primary_body_area_codes.map(bodyAreaLabel).join(', ')}
            </Text>
            <Text style={styles.areaCaution}>
              해당 부위에 통증이 있는 경우 주의가 필요해요.
            </Text>
          </View>
        ) : null}

        <View style={styles.section} testID="exercise-instruction-steps">
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            자세 설명
          </Text>
          {instructionSteps.length > 0 ? (
            instructionSteps.map((step, index) => (
              <Text key={`${index}-${step}`} style={styles.step}>
                {index + 1}. {step}
              </Text>
            ))
          ) : (
            <Text style={styles.summary}>{detail.instruction_summary}</Text>
          )}
        </View>

        {cautions.length > 0 ? (
          <View style={styles.section} testID="exercise-cautions">
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              주의사항
            </Text>
            <BulletList items={cautions} />
          </View>
        ) : null}

        {equipmentGuideSection ? (
          <View style={styles.section} testID={equipmentGuideSection.testID}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              {equipmentGuideSection.title}
            </Text>
            {equipmentGuideSection.referenceOnly ? (
              <Text style={styles.referenceNotice}>
                시작 무게는 참고값이에요. 당일 상태와 장비 사양에 맞게 무리하지
                않는 범위로 조절해요.
              </Text>
            ) : null}
            {equipmentGuideSection.guides.map((guide, index) => (
              <EquipmentGuideCard
                guide={guide}
                key={`${guide.equipment_code}-${index}`}
              />
            ))}
          </View>
        ) : null}
      </View>
    </View>
  );
}

export type ExerciseGuideContext = {
  locationCode: string | null;
  /**
   * When provided, only guides for these equipment codes are shown. Omission
   * means the caller has no client-side inventory and trusts the server-scoped
   * exercise guides; an explicit empty list hides every guide.
   */
  availableEquipmentCodes?: readonly string[];
};

type EquipmentGuide = HouseholdEquipmentGuide | GymEquipmentStartingGuide;

type EquipmentGuideSection = {
  guides: EquipmentGuide[];
  referenceOnly: boolean;
  testID: string;
  title: string;
};

export function selectEquipmentGuideSection(
  detail: ExerciseDetailResponse,
  context?: ExerciseGuideContext,
): EquipmentGuideSection | null {
  if (context?.locationCode !== 'HOME' && context?.locationCode !== 'GYM') {
    return null;
  }

  const candidates =
    context.locationCode === 'HOME'
      ? (detail.household_equipment_guides ?? [])
      : (detail.gym_equipment_starting_guides ?? []);
  const allowedCodes = context.availableEquipmentCodes;
  const guides =
    allowedCodes === undefined
      ? candidates
      : candidates.filter((guide) =>
          allowedCodes.includes(guide.equipment_code),
        );

  if (guides.length === 0) {
    return null;
  }

  return context.locationCode === 'HOME'
    ? {
        guides,
        referenceOnly: false,
        testID: 'household-equipment-guides',
        title: '집 생활도구 안내',
      }
    : {
        guides,
        referenceOnly: true,
        testID: 'gym-equipment-starting-guides',
        title: '헬스장 장비 시작 안내',
      };
}

function BulletList({ items }: { items: string[] }) {
  return items.map((item, index) => (
    <View key={`${index}-${item}`} style={styles.cueRow}>
      <Text style={styles.bullet}>·</Text>
      <Text style={styles.cue}>{item}</Text>
    </View>
  ));
}

function EquipmentGuideCard({ guide }: { guide: EquipmentGuide }) {
  return (
    <View style={styles.equipmentCard}>
      <Text style={styles.equipmentTitle}>
        {equipmentLabel(guide.equipment_code)} 활용
      </Text>
      <Text style={styles.equipmentProposal}>{guide.proposal_ko}</Text>
      {guide.examples_ko.length > 0 ? (
        <View style={styles.equipmentGroup}>
          <Text style={styles.equipmentLabel}>활용 예시</Text>
          <BulletList items={guide.examples_ko} />
        </View>
      ) : null}
      {guide.cautions_ko.length > 0 ? (
        <View style={styles.equipmentGroup}>
          <Text style={styles.equipmentLabel}>사용 시 주의사항</Text>
          <BulletList items={guide.cautions_ko} />
        </View>
      ) : null}
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
    <>
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
                setLoadedUri((current) =>
                  current === mediaUri ? current : null,
                )
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
      {/*
        Credited under the media it belongs to, on every screen that shows it:
        this component is the only render site, and the posture sheet it lives in
        is reused by home, the running workout, the session list and the catalog.
        Shown only when an actual frame is rendered -- there is nothing to
        attribute under the "GIF가 준비되면" placeholder or a failed load.
      */}
      {canRender ? (
        <Text style={styles.mediaCredit} testID="exercise-media-credit">
          © Gym visual - Aliaksandr Makatserchyk
        </Text>
      ) : null}
    </>
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
  mediaCredit: {
    marginTop: -4,
    color: colors.textMuted,
    fontSize: 10,
    lineHeight: 14,
    textAlign: 'center',
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
    gap: spacing.lg,
  },
  section: {
    gap: spacing.sm,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 24,
  },
  summary: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 24,
  },
  step: {
    color: colors.textSub,
    fontSize: 15,
    lineHeight: 23,
  },
  areas: {
    color: colors.textSub,
    fontSize: 15,
    lineHeight: 23,
  },
  areaCaution: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
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
  equipmentCard: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.surface,
    padding: spacing.md,
  },
  equipmentTitle: {
    color: colors.greenText,
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 22,
  },
  equipmentProposal: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 21,
  },
  referenceNotice: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
  },
  equipmentGroup: {
    gap: spacing.xs,
  },
  equipmentLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 21,
  },
});
