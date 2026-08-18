/**
 * Today's state: the active routine, whether a check-in exists, and what the
 * user can do next.
 *
 * The screen never decides what today's workout should be. It reports what the
 * server already stored and routes the user to the step that produces the next
 * server decision.
 *
 * On a rest day the mascot and every workout prompt are withheld, so the screen
 * carries no pressure to train.
 */

import { StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import { fatigueLabel, trainingTypeLabel } from '../../api/labels';
import type { DailyContextResponse, RoutineResponse } from '../../api/types';
import {
  localDateString,
  useAsyncAction,
  useAsyncData,
} from '../../api/useAsync';
import {
  BottomTabBar,
  MascotStage,
  type TabId,
} from '../../components/brand/BrandChrome';
import { Button, Card } from '../../components/primitives';
import {
  ErrorState,
  InfoNotice,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';

type TodayData = {
  routine: RoutineResponse | null;
  context: DailyContextResponse | null;
};

export function TodayScreen({
  api,
  nickname,
  restToday,
  onCheckIn,
  onTab,
  onOpenCalendar,
}: {
  api: Api;
  nickname: string;
  /** Set once the user chose REST today; suppresses any further nudging. */
  restToday: boolean;
  onCheckIn: (
    routine: RoutineResponse,
    context: DailyContextResponse | null,
  ) => void;
  onTab: (tab: TabId) => void;
  onOpenCalendar: () => void;
}) {
  const localDate = localDateString();

  const { state, reload } = useAsyncData<TodayData>(
    async (signal) => {
      const routine = await api
        .getCurrentRoutine(localDate, signal)
        .catch((error: unknown) => {
          if (isApiError(error) && error.kind === 'notFound') {
            return null;
          }
          throw error;
        });
      const context = await api
        .getDailyContext(localDate, signal)
        .catch((error: unknown) => {
          if (isApiError(error) && error.kind === 'notFound') {
            return null;
          }
          throw error;
        });
      return { routine, context };
    },
    [api, localDate],
  );

  const createRoutine = useAsyncAction(async () => {
    await api.createRoutine({
      effective_from: localDate,
      goal_code: 'GENERAL_FITNESS',
    });
    reload();
  });

  const routine = state.status === 'ready' ? state.data.routine : null;
  const context = state.status === 'ready' ? state.data.context : null;

  const tabBar = <BottomTabBar activeTab="home" onNavigate={onTab} />;

  if (state.status === 'loading') {
    return (
      <ScreenShell bands footer={tabBar}>
        <ScreenHeading title={`${nickname}님, 안녕하세요`} onBand />
        <LoadingState />
      </ScreenShell>
    );
  }

  if (state.status === 'error') {
    return (
      <ScreenShell bands footer={tabBar}>
        <ScreenHeading title={`${nickname}님, 안녕하세요`} onBand />
        <ErrorState message={state.message} onRetry={reload} />
      </ScreenShell>
    );
  }

  return (
    <ScreenShell bands footer={tabBar}>
      <ScreenHeading
        title={`${nickname}님, 안녕하세요`}
        subtitle={`오늘 ${localDate}`}
        onBand
      />

      {restToday ? null : (
        <MascotStage
          eyebrow="오늘의 헬끼"
          title={
            routine === null
              ? '루틴부터 만들어요'
              : context === null
                ? '컨디션을 알려주세요'
                : '오늘 운동 준비 완료'
          }
          caption={
            routine === null
              ? '검수된 운동만 사용해 기본 루틴을 만들어요.'
              : context === null
                ? '오늘 상태에 맞춰 최종 루틴을 정할게요.'
                : '추천을 확인하고 시작해요.'
          }
        />
      )}

      {routine === null ? (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>기본 루틴이 아직 없어요</Text>
          <Text style={styles.cardBody}>
            프로필을 바탕으로 검수된 운동만 사용해 기본 루틴을 만들어요.
          </Text>
          {createRoutine.error ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {createRoutine.error}
            </Text>
          ) : null}
          <Button
            label={createRoutine.pending ? '만드는 중…' : '기본 루틴 만들기'}
            disabled={createRoutine.pending}
            onPress={() => void createRoutine.run()}
          />
        </Card>
      ) : (
        <RoutineCard routine={routine} />
      )}

      {restToday ? (
        // The user chose rest today. Show no further prompt to work out.
        <InfoNotice
          title="오늘은 휴식하기로 했어요"
          message="푹 쉬고 내일 다시 만나요. 오늘은 더 이상 운동을 권하지 않을게요."
        />
      ) : routine !== null ? (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>
            {context === null ? '오늘 컨디션 체크인' : '체크인 완료'}
          </Text>
          <Text style={styles.cardBody}>
            {context === null
              ? '오늘 상태를 알려주면 그에 맞는 최종 루틴을 추천해요.'
              : `피로도 ${fatigueLabel(context.fatigue_level_code)} · 희망 ${context.requested_duration_minutes}분`}
          </Text>
          <Button
            label={context === null ? '체크인 하기' : '체크인 다시 하기'}
            onPress={() => onCheckIn(routine, context)}
          />
        </Card>
      ) : null}

      <View style={styles.links}>
        <Button
          label="캘린더 연동 상태"
          tone="secondary"
          onPress={onOpenCalendar}
        />
      </View>
    </ScreenShell>
  );
}

function RoutineCard({ routine }: { routine: RoutineResponse }) {
  const day = routine.days[0];
  return (
    <Card style={styles.card}>
      <Text style={styles.cardTitle}>기본 루틴 v{routine.version}</Text>
      {day ? (
        <>
          <Text style={styles.cardBody}>
            {trainingTypeLabel(day.training_type_code)} ·{' '}
            {day.requested_duration_minutes}분 · 블록 {day.items.length}개
          </Text>
          <Text style={styles.meta}>
            주 {routine.days.length}회 · 카탈로그 {routine.catalog_version}
          </Text>
        </>
      ) : (
        <Text style={styles.cardBody}>구성된 운동일이 없어요.</Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
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
  meta: {
    color: colors.textMuted,
    fontSize: 12,
  },
  error: {
    color: colors.dangerText,
    fontSize: 13,
    lineHeight: 19,
  },
  links: {
    gap: spacing.sm,
  },
});
