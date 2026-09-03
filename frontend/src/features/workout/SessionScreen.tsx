/**
 * Live workout session: count-up timer on top, mascot in the centre, and the
 * exercise blocks as a one-at-a-time carousel along the bottom, matching the
 * layout fixed in docs/ARCHITECTURE.md section 9.
 *
 * Completion rules this screen must not bend:
 *
 * - the elapsed timer counts up from zero and is informational only; it never
 *   completes a block or the session
 * - a block becomes COMPLETED only through the item API, and the server's
 *   response is the source of truth for progress and for which block is current
 * - `/finish` is only offered once the server reports at least one completed
 *   block; otherwise the user is routed to the not-completed reason flow
 * - reporting pain or an adverse response switches the mascot to its serious
 *   form and ends the session without collecting symptom details
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import { formatDuration } from '../../api/labels';
import type {
  SafetyEventResponse,
  SessionFinishResponse,
  SessionItem,
  SessionNotCompletedResponse,
  WorkoutPlan,
} from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import { orderedWorkoutPlanItems } from '../../api/workoutPlan';
import {
  MascotStage,
  useBrandFontFamily,
} from '../../components/brand/BrandChrome';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';
import { ExerciseDetailSheet } from './ExerciseDetailSheet';
import { NotCompletedSheet } from './NotCompletedSheet';
import { SessionCarousel } from './SessionCarousel';

export type SessionOutcome =
  | { kind: 'finished'; result: SessionFinishResponse }
  | { kind: 'notCompleted'; result: SessionNotCompletedResponse }
  | { kind: 'safetyStop'; event: SafetyEventResponse };

export function SessionScreen({
  api,
  sessionId,
  plan,
  onOutcome,
}: {
  api: Api;
  sessionId: string;
  plan: WorkoutPlan;
  onOutcome: (outcome: SessionOutcome) => void;
}) {
  const [items, setItems] = useState<SessionItem[] | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const [openDetailId, setOpenDetailId] = useState<string | null>(null);
  const [safetyOpen, setSafetyOpen] = useState(false);
  const [notCompletedOpen, setNotCompletedOpen] = useState(false);
  const started = useRef(false);
  const family = useBrandFontFamily();
  const orderedPlanItems = useMemo(
    () => orderedWorkoutPlanItems(plan.items),
    [plan.items],
  );

  const start = useAsyncAction(async () => {
    const response = await api.startSession(
      sessionId,
      new Date().toISOString(),
    );
    setItems(response.items);
    setRunning(true);
  });

  useEffect(() => {
    if (started.current) {
      return;
    }
    started.current = true;
    void start.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Informational counter only. It never triggers a completion call.
  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const toggleItem = useAsyncAction(
    async (planItemId: string, next: 'PENDING' | 'COMPLETED') => {
      const response = await api.updateSessionItem(
        sessionId,
        planItemId,
        next,
        new Date().toISOString(),
      );
      // Trust the server's view of the item rather than the local guess.
      setItems((current) =>
        (current ?? []).map((item) =>
          item.plan_item_id === planItemId ? response.item : item,
        ),
      );
      setOpenDetailId(null);
    },
  );

  const finish = useAsyncAction(async () => {
    const result = await api.finishSession(
      sessionId,
      new Date().toISOString(),
      elapsed,
    );
    setRunning(false);
    onOutcome({ kind: 'finished', result });
  });

  const reportSafety = useAsyncAction(async () => {
    const event = await api.reportSafetyEvent(sessionId, {
      stop_reason_code: 'PAIN_OR_ABNORMAL_RESPONSE',
    });
    if (
      event.execution_state_code !== 'STOPPED_SAFETY' ||
      event.is_resumable !== false
    ) {
      throw new ApiError({
        kind: 'server',
        code: 'INVALID_SAFETY_EVENT_RESPONSE',
        status: 500,
        message: '안전 중단 응답을 확인할 수 없습니다. 운동을 계속하지 마세요.',
      });
    }
    setSafetyOpen(false);
    setRunning(false);
    onOutcome({ kind: 'safetyStop', event });
    return event;
  });

  const markNotCompleted = useAsyncAction(async (reasonCode: string) => {
    const result = await api.markNotCompleted(
      sessionId,
      new Date().toISOString(),
      reasonCode as SessionNotCompletedResponse['reason_code'],
    );
    setRunning(false);
    setNotCompletedOpen(false);
    onOutcome({ kind: 'notCompleted', result });
  });

  const togglePause = useCallback(() => {
    setRunning((current) => {
      void api
        .recordTimerEvent(
          sessionId,
          current ? 'PAUSE' : 'RESUME',
          new Date().toISOString(),
        )
        .catch(() => {
          // Timer history is analytics only; losing an event must not
          // interrupt the workout or change block state.
        });
      return !current;
    });
  }, [api, sessionId]);

  // The centred card is the first block the server still reports as PENDING,
  // falling back to the last block once everything is done.
  const currentIndex = useMemo(() => {
    if (items === null) {
      return 0;
    }
    const pendingIndex = orderedPlanItems.findIndex(
      (item) =>
        items.find((state) => state.plan_item_id === item.plan_item_id)
          ?.status_code !== 'COMPLETED',
    );
    return pendingIndex === -1
      ? Math.max(orderedPlanItems.length - 1, 0)
      : pendingIndex;
  }, [items, orderedPlanItems]);

  if (start.pending || items === null) {
    return (
      <ScreenShell bands>
        <ScreenHeading title="운동 준비 중" onBand />
        {start.error ? (
          <InlineFeedback tone="error" message={start.error} />
        ) : (
          <Card>
            <Text style={styles.loading}>세션을 시작하고 있어요…</Text>
          </Card>
        )}
      </ScreenShell>
    );
  }

  const completedCount = items.filter(
    (item) => item.status_code === 'COMPLETED',
  ).length;
  const canFinish = completedCount > 0;
  const allDone = completedCount === items.length;
  const currentItem = orderedPlanItems[currentIndex];
  const serious = safetyOpen;

  return (
    <ScreenShell bands tallBands contentStyle={styles.content}>
      <View style={styles.timerBlock}>
        <Text
          style={[styles.timer, family ? { fontFamily: family } : null]}
          accessibilityLabel={`경과 시간 ${formatDuration(elapsed)}`}
        >
          {formatDuration(elapsed)}
        </Text>
        <Text style={styles.timerNote}>
          경과 시간은 기록용이에요. 완료는 블록 체크로만 정해져요.
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={togglePause}
          style={styles.pause}
        >
          <Text style={styles.pauseLabel}>
            {running ? '일시정지' : '이어서 하기'}
          </Text>
        </Pressable>
      </View>

      <MascotStage
        serious={serious}
        eyebrow={
          serious
            ? '안전을 먼저 확인해주세요'
            : allDone
              ? '모든 블록 완료'
              : '지금 할 운동'
        }
        title={
          serious
            ? '주의해서 진행해주세요'
            : allDone
              ? '운동을 마무리해요'
              : (currentItem?.exercise_name ?? '운동')
        }
        caption={
          serious
            ? '안내를 확인한 뒤 무리하지 말고 진행해주세요.'
            : `${completedCount} / ${items.length} 블록 완료`
        }
      />

      {toggleItem.error ? (
        <InlineFeedback tone="error" message={toggleItem.error} />
      ) : null}

      <SessionCarousel
        items={orderedPlanItems}
        states={items}
        currentIndex={currentIndex}
        pending={toggleItem.pending}
        onToggle={(planItemId, next) => void toggleItem.run(planItemId, next)}
        onOpenDetail={setOpenDetailId}
        detailFor={openDetailId}
        detail={
          openDetailId ? (
            <ExerciseDetailSheet api={api} exerciseId={openDetailId} />
          ) : null
        }
      />

      {finish.error ? (
        <InlineFeedback tone="error" message={finish.error} />
      ) : null}

      <View style={styles.footer}>
        <Button
          label={finish.pending ? '저장 중…' : '운동 마치기'}
          disabled={!canFinish || finish.pending}
          onPress={() => void finish.run()}
        />
        {!canFinish ? (
          <Text style={styles.footerNote}>
            완료한 블록이 하나도 없어요. 블록을 체크하거나 미수행으로 기록해요.
          </Text>
        ) : null}
        <Button
          label="오늘은 못 했어요"
          tone="secondary"
          onPress={() => setNotCompletedOpen(true)}
        />
        <Button
          label="통증·이상 반응 알리기"
          tone="secondary"
          onPress={() => setSafetyOpen(true)}
        />
      </View>

      {safetyOpen ? (
        <SafetyStopConfirmation
          pending={reportSafety.pending}
          error={reportSafety.error}
          onCancel={() => setSafetyOpen(false)}
          onConfirm={() => void reportSafety.run()}
        />
      ) : null}

      {notCompletedOpen ? (
        <NotCompletedSheet
          pending={markNotCompleted.pending}
          error={markNotCompleted.error}
          onCancel={() => setNotCompletedOpen(false)}
          onSubmit={(reason) => void markNotCompleted.run(reason)}
        />
      ) : null}
    </ScreenShell>
  );
}

/**
 * Serious-tone confirmation. The workout safety endpoint intentionally does
 * not collect symptom, body-area or pain-score details.
 */
function SafetyStopConfirmation({
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Card style={styles.sheet}>
      <Text style={styles.sheetTitle}>안전을 위해 운동을 중단할게요</Text>
      <Text style={styles.sheetBody}>
        통증 또는 이상 반응이 있다면 오늘 운동은 여기서 종료되며 다시 이어할 수
        없습니다.
      </Text>

      {error ? <InlineFeedback tone="error" message={error} /> : null}

      <Button
        label={pending ? '중단 처리 중…' : '안전하게 운동 중단하기'}
        disabled={pending}
        onPress={onConfirm}
      />
      <Button label="닫기" tone="secondary" onPress={onCancel} />
    </Card>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingTop: spacing.lg,
  },
  timerBlock: {
    alignItems: 'center',
    gap: 6,
    paddingVertical: spacing.md,
  },
  timer: {
    color: colors.surface,
    fontSize: 52,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  timerNote: {
    color: colors.greenTint,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
  pause: {
    marginTop: spacing.sm,
    borderWidth: 1.5,
    borderColor: colors.surface,
    borderRadius: radii.control,
    paddingHorizontal: 18,
    paddingVertical: 8,
  },
  pauseLabel: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: '700',
  },
  footer: {
    gap: spacing.sm,
  },
  footerNote: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  loading: {
    color: colors.textSub,
    fontSize: 14,
  },
  sheet: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
  },
  sheetTitle: {
    color: colors.dangerText,
    fontSize: 16,
    fontWeight: '700',
  },
  sheetBody: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  sheetLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipSelected: {
    borderColor: colors.danger,
    backgroundColor: colors.dangerBg,
  },
  chipLabel: {
    color: colors.textSub,
    fontSize: 12,
    fontWeight: '600',
  },
});
