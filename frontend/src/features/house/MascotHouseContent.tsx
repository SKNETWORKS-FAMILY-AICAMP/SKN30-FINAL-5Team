import { Image, StyleSheet, Text, View } from 'react-native';

import { trainingTypeLabel } from '../../api/labels';
import type { RoutineResponse, WeekResponse } from '../../api/types';
import { imageAssets } from '../../assets';
import {
  MascotStage,
  useBrandFontFamily,
} from '../../components/brand/BrandChrome';
import { Card } from '../../components/primitives';
import { ScreenHeading } from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';

/**
 * The data-backed contents of the mascot house.
 *
 * Keeping this presentation separate from its API container lets Home reuse
 * the routine and week it has already loaded instead of issuing duplicate
 * requests for the same resources.
 */
export function MascotHouseContent({
  embedded = false,
  nickname,
  routine,
  week,
}: {
  embedded?: boolean;
  nickname: string;
  routine: RoutineResponse | null;
  week: WeekResponse | null;
}) {
  const family = useBrandFontFamily();
  const day = routine?.days[0];

  return (
    <View style={styles.content} testID="mascot-house-content">
      {embedded ? (
        <View style={styles.embeddedHeading}>
          <Text style={styles.embeddedTitle}>끼끼의 집</Text>
          <Text style={styles.embeddedSubtitle}>
            {nickname}님과 함께한 이번 주
          </Text>
        </View>
      ) : (
        <ScreenHeading
          title="끼끼의 집"
          subtitle={`${nickname}님과 함께한 이번 주`}
          onBand
        />
      )}

      <View style={styles.house}>
        <Image
          source={imageAssets.splashIsland}
          style={styles.island}
          resizeMode="contain"
          accessibilityLabel="끼끼와 운동 섬"
        />
        <Text
          style={[styles.houseCaption, family ? { fontFamily: family } : null]}
        >
          {routine === null
            ? '아직 루틴이 없어요. 홈에서 만들어 주세요.'
            : '오늘도 같이 움직여요.'}
        </Text>
      </View>

      <MascotStage
        eyebrow="이번 주"
        title={
          week === null
            ? '주간 정보를 불러오지 못했어요'
            : `목표 ${week.target_workout_count}회`
        }
        caption={
          week === null
            ? '잠시 후 다시 확인해 주세요.'
            : week.status_code === 'CLOSED'
              ? '마감된 주예요. 리포트를 확인할 수 있어요.'
              : '진행 중인 주예요. 편한 날에 하나씩 채워요.'
        }
      />

      {routine !== null && day ? (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>지금 내 루틴</Text>
          <Text style={styles.cardBody}>
            {trainingTypeLabel(day.training_type_code)} ·{' '}
            {day.requested_duration_minutes}분 · 블록 {day.items.length}개
          </Text>
          <View style={styles.blockList}>
            {day.items.map((item) => (
              <View key={item.id} style={styles.blockRow}>
                <Text style={styles.blockName}>{item.exercise_name}</Text>
                <Text style={styles.blockMeta}>
                  {item.sets}세트
                  {item.reps === null
                    ? ` · ${item.work_seconds_per_set ?? 0}초`
                    : ` × ${item.reps}회`}
                </Text>
              </View>
            ))}
          </View>
          <Text style={styles.meta}>
            루틴 v{routine.version} · 카탈로그 {routine.catalog_version}
          </Text>
        </Card>
      ) : (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>아직 보여줄 루틴이 없어요</Text>
          <Text style={styles.cardBody}>
            홈에서 기본 루틴을 만들면 여기에 나타나요.
          </Text>
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: spacing.md,
  },
  embeddedHeading: {
    gap: spacing.xs,
    paddingHorizontal: spacing.xs,
  },
  embeddedTitle: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '800',
  },
  embeddedSubtitle: {
    color: colors.textSub,
    fontSize: 13,
  },
  house: {
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: radii.card,
    backgroundColor: colors.surface,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
  },
  island: {
    width: '100%',
    maxWidth: 300,
    aspectRatio: 460 / 307,
  },
  houseCaption: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  card: {
    gap: spacing.md,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  cardBody: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  blockList: {
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: spacing.md,
  },
  blockRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  blockName: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
  },
  blockMeta: {
    color: colors.textMuted,
    fontSize: 12,
  },
  meta: {
    color: colors.textMuted,
    fontSize: 12,
  },
});
