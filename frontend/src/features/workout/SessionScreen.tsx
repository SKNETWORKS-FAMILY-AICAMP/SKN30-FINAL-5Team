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
 *   form, and a resulting stop ends the session immediately
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  ADVERSE_REACTION_OPTIONS,
  BODY_AREA_OPTIONS,
  formatDuration,
} from '../../api/labels';
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
  SafetyNotice,
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
  const [caution, setCaution] = useState<SafetyEventResponse | null>(null);
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

  const reportSafety = useAsyncAction(
    async (bodyAreaCode: string | null, reactionCode: string | null) => {
      const event = await api.reportSafetyEvent(sessionId, {
        occurred_at: new Date().toISOString(),
        discomforts: bodyAreaCode
          ? [{ body_area_code: bodyAreaCode, severity_code: 'SEVERE' }]
          : [],
        adverse_reaction_codes: reactionCode ? [reactionCode] : [],
      });
      setSafetyOpen(false);
      if (event.session_status_code === 'STOPPED_FOR_SAFETY') {
        setRunning(false);
        onOutcome({ kind: 'safetyStop', event });
        return event;
      }
      // SHOW_CAUTION keeps the session running; the server does not rewrite an
      // in-progress plan, so the client only surfaces the reviewed wording.
      setCaution(event);
      return event;
    },
  );

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
  const serious = safetyOpen || caution !== null;

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

      {caution ? (
        <SafetyNotice title="주의 안내" message={caution.guidance} />
      ) : null}
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
        <SafetyReportSheet
          pending={reportSafety.pending}
          error={reportSafety.error}
          onCancel={() => setSafetyOpen(false)}
          onReport={(area, reaction) => void reportSafety.run(area, reaction)}
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
 * Serious-tone reporting. No mascot mark, no playful copy or colour here.
 */
function SafetyReportSheet({
  pending,
  error,
  onCancel,
  onReport,
}: {
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onReport: (bodyAreaCode: string | null, reactionCode: string | null) => void;
}) {
  const [area, setArea] = useState<string | null>(null);
  const [reaction, setReaction] = useState<string | null>(null);

  return (
    <Card style={styles.sheet}>
      <Text style={styles.sheetTitle}>지금 상태를 알려주세요</Text>
      <Text style={styles.sheetBody}>
        선택한 내용에 따라 운동을 중단하도록 안내할 수 있어요.
      </Text>

      <Text style={styles.sheetLabel}>심한 통증이 있는 부위</Text>
      <View style={styles.chipRow}>
        {BODY_AREA_OPTIONS.map((option) => (
          <Pressable
            key={option.code}
            accessibilityRole="button"
            accessibilityState={{ selected: area === option.code }}
            onPress={() =>
              setArea((current) =>
                current === option.code ? null : option.code,
              )
            }
            style={[styles.chip, area === option.code && styles.chipSelected]}
          >
            <Text style={styles.chipLabel}>{option.label}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.sheetLabel}>이상 반응</Text>
      <View style={styles.chipRow}>
        {ADVERSE_REACTION_OPTIONS.map((option) => (
          <Pressable
            key={option.code}
            accessibilityRole="button"
            accessibilityState={{ selected: reaction === option.code }}
            onPress={() =>
              setReaction((current) =>
                current === option.code ? null : option.code,
              )
            }
            style={[
              styles.chip,
              reaction === option.code && styles.chipSelected,
            ]}
          >
            <Text style={styles.chipLabel}>{option.label}</Text>
          </Pressable>
        ))}
      </View>

      {error ? <InlineFeedback tone="error" message={error} /> : null}

      <Button
        label={pending ? '전송 중…' : '알리기'}
        disabled={pending || (area === null && reaction === null)}
        onPress={() => onReport(area, reaction)}
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
