/**
 * 끼끼의 집 — the mascot's home, showing the user's real standing.
 *
 * The existing MapHomeScreen carries the same idea but renders fixture
 * exercises, which would sit alongside the user's real routine and read as
 * genuine. This screen keeps the mascot-house framing and fills it from the
 * server: the active routine and the current week's target and status.
 *
 * The mascot reacts to progress but never to a shortfall. A missed or
 * unfinished week is a learning signal, so the copy stays level and no
 * disappointed state exists here.
 */

import { Image, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import { trainingTypeLabel } from '../../api/labels';
import type { RoutineResponse, WeekResponse } from '../../api/types';
import {
  localDateString,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import {
  BottomTabBar,
  MascotStage,
  useBrandFontFamily,
  type TabId,
} from '../../components/brand/BrandChrome';
import { Card } from '../../components/primitives';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';
import { imageAssets } from '../../assets';

type HouseData = {
  routine: RoutineResponse | null;
  week: WeekResponse | null;
};

export function MascotHouseScreen({
  api,
  nickname,
  onNavigate,
  timeZone,
}: {
  api: Api;
  nickname: string;
  onNavigate: (tab: TabId) => void;
  timeZone?: string;
}) {
  const family = useBrandFontFamily();
  const now = new Date();
  const localDate = localDateString(now, timeZone);
  const weekStart = weekStartString(now, timeZone);

  const { state, reload } = useAsyncData<HouseData>(
    async (signal) => {
      const routine = await api
        .getCurrentRoutine(localDate, signal)
        .catch((error: unknown) => {
          if (isApiError(error) && error.kind === 'notFound') {
            return null;
          }
          throw error;
        });
      const week = await api.getWeek(weekStart, signal).catch(() => null);
      return { routine, week };
    },
    [api, localDate, weekStart],
  );

  const tabBar = <BottomTabBar activeTab="house" onNavigate={onNavigate} />;

  if (state.status === 'loading') {
    return (
      <ScreenShell bands tallBands footer={tabBar}>
        <ScreenHeading title="끼끼의 집" onBand />
        <LoadingState />
      </ScreenShell>
    );
  }

  if (state.status === 'error') {
    return (
      <ScreenShell bands tallBands footer={tabBar}>
        <ScreenHeading title="끼끼의 집" onBand />
        <ErrorState message={state.message} onRetry={reload} />
      </ScreenShell>
    );
  }

  const { routine, week } = state.data;
  const day = routine?.days[0];

  return (
    <ScreenShell bands tallBands footer={tabBar}>
      <ScreenHeading
        title="끼끼의 집"
        subtitle={`${nickname}님과 함께한 이번 주`}
        onBand
      />

      {/*
        The only mascot artwork in the repository is the splash island, which
        shows 끼끼 in its training spot. This screen is where it fits at full
        size; the compact stages elsewhere still use the drawn mark because a
        460x307 scene does not reduce to a 64px badge.
      */}
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
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  house: {
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: radii.card,
    backgroundColor: colors.surface,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
  },
  island: {
    // Keeps the source 460x307 aspect ratio; the container caps the width.
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
