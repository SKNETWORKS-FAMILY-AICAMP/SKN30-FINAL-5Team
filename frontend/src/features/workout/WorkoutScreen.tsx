import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { Api } from '../../api/endpoints';
import { messageForError } from '../../api/errors';
import {
  ADVERSE_REACTION_OPTIONS,
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  formatExercisePrescription,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  NotCompletedReasonCode,
  SessionItem,
  WorkoutPlan,
} from '../../api/types';
import { orderedWorkoutPlanItems } from '../../api/workoutPlan';
import { imageAssets } from '../../assets';
import { colors, shadows } from '../../components/theme';
import { useScale } from '../../components/scale';
import { ExerciseDetailSheet } from './ExerciseDetailSheet';
import type { SessionOutcome } from './SessionScreen';
import {
  NOT_COMPLETED_REASONS,
  SAFETY_GUIDANCE,
  getWorkoutResponsiveLayout,
  WORKOUT_ARC,
  WORKOUT_BLOCKS,
  WORKOUT_CAROUSEL,
  WORKOUT_SEVERITIES,
  WORKOUT_SYMPTOMS,
  type WorkoutBlock,
  type WorkoutBlockStatus,
  type WorkoutPreviewState,
  type WorkoutResponsiveLayout,
  type WorkoutSafetyInstruction,
  type WorkoutSafetyReport,
} from './workoutModel';

export const WORKOUT_LAYOUT = {
  headerHorizontalPadding: 18,
  headerTopPadding: 54,
  contentHorizontalPadding: 18,
  sheetHorizontalPadding: 18,
  sheetBottomPadding: 28,
} as const;

type WorkoutOverlay =
  | 'none'
  | 'rest'
  | 'not-completed'
  | 'safety'
  | 'symptom'
  | 'api-safety'
  | 'api-guidance'
  | 'additional';
type WorkoutResult = 'none' | 'completed' | 'stopped';

const ADDITIONAL_ACTIVITY_TYPES = [
  { code: 'WALKING', label: '걷기' },
  { code: 'CYCLING', label: '자전거' },
] as const;

const ACTIVITY_INTENSITIES = [
  { code: 'LOW', label: '가볍게' },
  { code: 'MODERATE', label: '보통' },
  { code: 'VIGOROUS', label: '강하게' },
] as const;

type WorkoutFixture = {
  completedBlockIds: readonly string[];
  elapsedSeconds: number;
  instruction?: WorkoutSafetyInstruction;
  offline: boolean;
  overlay: WorkoutOverlay;
  reportNote?: string;
  result: WorkoutResult;
  safetyReport?: WorkoutSafetyReport;
};

type WorkoutViewBlock = WorkoutBlock & {
  exerciseId?: string;
  instructionAvailable?: boolean;
  status: WorkoutBlockStatus;
};

type WorkoutPreviewProps = {
  onBackHome?: () => void;
  onBlockStatusChange?: (blockId: string, status: WorkoutBlockStatus) => void;
  onNotCompleted?: (reasonCode: string) => void;
  onPauseChange?: (paused: boolean) => void;
  onRestChange?: (open: boolean) => void;
  onSafetyEvent?: (
    report: WorkoutSafetyReport,
    instruction: WorkoutSafetyInstruction,
  ) => void;
  onSafetyStopRequest?: () => void;
  previewState?: WorkoutPreviewState;
};

type WorkoutApiProps = {
  api: Api;
  sessionId: string;
  plan: WorkoutPlan;
  onOutcome: (outcome: SessionOutcome) => void;
};

type WorkoutScreenProps = WorkoutPreviewProps | WorkoutApiProps;

export function formatWorkoutTime(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
}

export function clampWorkoutPageIndex(
  offsetX: number,
  blockCount: number,
  stride: number = WORKOUT_CAROUSEL.STRIDE,
) {
  if (blockCount <= 0) {
    return 0;
  }
  const nearest = Math.round(offsetX / stride);
  return Math.max(0, Math.min(blockCount - 1, nearest));
}

export function WorkoutScreen(props: WorkoutScreenProps) {
  if ('api' in props) {
    return (
      <WorkoutScreenContent
        key={props.sessionId}
        apiConfig={props}
        fixture={getWorkoutFixture('active')}
      />
    );
  }
  const { previewState = 'active', ...previewProps } = props;
  return (
    <WorkoutScreenContent
      key={previewState}
      {...previewProps}
      fixture={getWorkoutFixture(previewState)}
    />
  );
}

function WorkoutScreenContent({
  apiConfig,
  fixture,
  onBackHome,
  onBlockStatusChange,
  onNotCompleted,
  onPauseChange,
  onRestChange,
  onSafetyEvent,
  onSafetyStopRequest,
}: Omit<WorkoutPreviewProps, 'previewState'> & {
  apiConfig?: WorkoutApiProps;
  fixture: WorkoutFixture;
}) {
  const brandFonts = useBrandFonts();
  const { height: viewportHeight, width: viewportWidth } = useScale();
  const responsiveLayout = useMemo(
    () =>
      getWorkoutResponsiveLayout({
        height: viewportHeight,
        width: viewportWidth,
      }),
    [viewportHeight, viewportWidth],
  );
  const carouselRef = useRef<ScrollView | null>(null);
  const [scrollX] = useState(() => new Animated.Value(0));
  const [burstOpacity] = useState(() => new Animated.Value(0));
  const [burstScale] = useState(() => new Animated.Value(0.7));
  const [elapsedSeconds, setElapsedSeconds] = useState(fixture.elapsedSeconds);
  const [previewResult, setPreviewResult] = useState<WorkoutResult>(
    fixture.result,
  );
  const [paused, setPaused] = useState(false);
  const [overlay, setOverlay] = useState<WorkoutOverlay>(fixture.overlay);
  const [completedBlockIds, setCompletedBlockIds] = useState<readonly string[]>(
    fixture.completedBlockIds,
  );
  const [detailBlockId, setDetailBlockId] = useState<string | null>(null);
  const [restSeconds, setRestSeconds] = useState(60);
  const [carouselWidth, setCarouselWidth] = useState(0);
  const [visiblePageIndex, setVisiblePageIndex] = useState(() =>
    firstPendingIndex(WORKOUT_BLOCKS, fixture.completedBlockIds),
  );
  const [burstKey, setBurstKey] = useState(0);
  const [selectedSymptom, setSelectedSymptom] = useState(
    fixture.safetyReport?.symptomCode ?? 'PAIN',
  );
  const [selectedSeverity, setSelectedSeverity] = useState(
    fixture.safetyReport?.severityCode ?? 'MILD',
  );
  const [selectedBodySeverities, setSelectedBodySeverities] = useState<
    Readonly<Record<string, WorkoutSafetyReport['severityCode']>>
  >({});
  const [selectedReactions, setSelectedReactions] = useState<readonly string[]>(
    [],
  );
  const [sessionReady, setSessionReady] = useState(apiConfig === undefined);
  const [actionPending, setActionPending] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [apiGuidance, setApiGuidance] = useState<string | null>(null);
  const [additionalDurationMinutes, setAdditionalDurationMinutes] =
    useState(10);
  const [additionalActivityType, setAdditionalActivityType] =
    useState<string>('WALKING');
  const [additionalIntensity, setAdditionalIntensity] =
    useState<string>('MODERATE');
  const [additionalNote, setAdditionalNote] = useState('');
  const [additionalSaved, setAdditionalSaved] = useState(false);
  const useJua = brandFonts.loaded && !brandFonts.failed;
  const selectedBodyAreas = Object.keys(selectedBodySeverities);
  const sourceBlocks = useMemo<readonly WorkoutViewBlock[]>(() => {
    if (apiConfig === undefined) {
      return WORKOUT_BLOCKS.map((block) => ({ ...block, status: 'PENDING' }));
    }
    return orderedWorkoutPlanItems(apiConfig.plan.items).map((item) => ({
      id: item.plan_item_id,
      exerciseId: item.exercise_id,
      instructionAvailable: item.instruction_available,
      name: item.exercise_name,
      meta: formatExercisePrescription({
        reps: item.reps,
        sets: item.sets,
        workSeconds: item.work_seconds,
      }),
      tips: [],
      status: 'PENDING',
    }));
  }, [apiConfig]);
  const blocks = useMemo(
    () =>
      sourceBlocks.map((block) => ({
        ...block,
        status: completedBlockIds.includes(block.id)
          ? ('COMPLETED' as const)
          : ('PENDING' as const),
      })),
    [completedBlockIds, sourceBlocks],
  );
  const pendingIndex = blocks.findIndex((block) => block.status === 'PENDING');
  const allBlocksCompleted = pendingIndex === -1;
  const currentIndex = allBlocksCompleted
    ? Math.max(0, blocks.length - 1)
    : pendingIndex;
  const currentBlock = blocks[currentIndex] ?? blocks[0]!;
  const detailBlock =
    blocks.find((block) => block.id === detailBlockId) ?? null;
  const completedCount = completedBlockIds.length;
  const isSafetyState =
    overlay === 'safety' ||
    overlay === 'symptom' ||
    overlay === 'api-safety' ||
    overlay === 'api-guidance';
  const carouselPadding = Math.max(
    0,
    (carouselWidth - responsiveLayout.cardWidth) / 2,
  );
  const timerCaption =
    overlay === 'rest'
      ? '휴식 중 · 타이머 정지'
      : paused
        ? '일시정지됨 · 기록용'
        : '전체 경과 · 기록용';
  const canSmash =
    !allBlocksCompleted &&
    visiblePageIndex === currentIndex &&
    overlay === 'none' &&
    sessionReady &&
    !actionPending;
  const canFinish =
    apiConfig !== undefined &&
    allBlocksCompleted &&
    overlay === 'none' &&
    sessionReady &&
    !actionPending;

  const recordTimerChange = useCallback(
    (eventCode: 'PAUSE' | 'RESUME') => {
      if (apiConfig === undefined) {
        return;
      }
      void apiConfig.api
        .recordTimerEvent(
          apiConfig.sessionId,
          eventCode,
          new Date().toISOString(),
        )
        .catch(() => undefined);
    },
    [apiConfig],
  );

  useEffect(() => {
    if (apiConfig === undefined) {
      return undefined;
    }
    const controller = new AbortController();
    let active = true;

    const load = async () => {
      try {
        const detail = await apiConfig.api.getWorkoutSession(
          apiConfig.sessionId,
          controller.signal,
        );
        let items: readonly SessionItem[];
        if (detail.status_code === 'PLANNED') {
          const started = await apiConfig.api.startSession(
            apiConfig.sessionId,
            new Date().toISOString(),
          );
          items = started.items;
          void apiConfig.api
            .recordTimerEvent(
              apiConfig.sessionId,
              'START',
              new Date().toISOString(),
            )
            .catch(() => undefined);
        } else if (detail.status_code === 'IN_PROGRESS') {
          items = detail.items.map((item) => ({
            plan_item_id: item.plan_item_id,
            status_code: item.status_code,
            completed_at: item.completed_at,
          }));
        } else {
          throw new Error('terminal workout session');
        }
        if (!active) {
          return;
        }
        setCompletedBlockIds(
          items
            .filter((item) => item.status_code === 'COMPLETED')
            .map((item) => item.plan_item_id),
        );
        setVisiblePageIndex(
          firstPendingIndex(
            sourceBlocks,
            items
              .filter((item) => item.status_code === 'COMPLETED')
              .map((item) => item.plan_item_id),
          ),
        );
        setSessionReady(true);
      } catch (error) {
        if (
          active &&
          !(error instanceof Error && error.name === 'AbortError')
        ) {
          setApiError(messageForError(error));
        }
      }
    };

    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [apiConfig, sourceBlocks]);

  useEffect(() => {
    if (
      paused ||
      overlay !== 'none' ||
      previewResult !== 'none' ||
      !sessionReady
    ) {
      return undefined;
    }
    const timer = setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [overlay, paused, previewResult, sessionReady]);

  useEffect(() => {
    if (overlay !== 'rest') {
      return undefined;
    }
    const timer = setInterval(() => {
      setRestSeconds((current) => {
        if (current <= 1) {
          setOverlay('none');
          setPaused(false);
          recordTimerChange('RESUME');
          onRestChange?.(false);
          return 0;
        }
        return current - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [onRestChange, overlay, recordTimerChange]);

  useEffect(() => {
    if (carouselWidth <= 0) {
      return;
    }
    carouselRef.current?.scrollTo({
      x: currentIndex * responsiveLayout.stride,
      animated: true,
    });
  }, [carouselWidth, currentIndex, responsiveLayout.stride]);

  useEffect(() => {
    if (burstKey === 0) {
      return undefined;
    }
    burstOpacity.stopAnimation();
    burstScale.stopAnimation();
    burstOpacity.setValue(0);
    burstScale.setValue(0.7);
    const animation = Animated.parallel([
      Animated.sequence([
        Animated.timing(burstOpacity, {
          duration: 245,
          toValue: 1,
          useNativeDriver: true,
        }),
        Animated.timing(burstOpacity, {
          duration: 455,
          toValue: 0,
          useNativeDriver: true,
        }),
      ]),
      Animated.sequence([
        Animated.timing(burstScale, {
          duration: 245,
          toValue: 1.06,
          useNativeDriver: true,
        }),
        Animated.timing(burstScale, {
          duration: 455,
          toValue: 1.3,
          useNativeDriver: true,
        }),
      ]),
    ]);
    animation.start();
    return () => animation.stop();
  }, [burstKey, burstOpacity, burstScale]);

  const togglePaused = () => {
    setPaused((current) => {
      recordTimerChange(current ? 'RESUME' : 'PAUSE');
      onPauseChange?.(!current);
      return !current;
    });
  };

  const finalizeServerSession = async () => {
    if (apiConfig === undefined) return;
    const endedAt = new Date().toISOString();
    await apiConfig.api
      .recordTimerEvent(apiConfig.sessionId, 'END', endedAt)
      .catch(() => undefined);
    const result = await apiConfig.api.finishSession(
      apiConfig.sessionId,
      endedAt,
      elapsedSeconds,
    );
    setPaused(true);
    apiConfig.onOutcome({ kind: 'finished', result });
  };

  const applyCompletedBlock = (
    block: WorkoutViewBlock,
    nextPendingPlanItemId?: string | null,
  ) => {
    setCompletedBlockIds((current) =>
      current.includes(block.id) ? current : [...current, block.id],
    );
    const serverNextIndex =
      nextPendingPlanItemId === undefined || nextPendingPlanItemId === null
        ? -1
        : blocks.findIndex((item) => item.id === nextPendingPlanItemId);
    const nextIndex =
      serverNextIndex >= 0
        ? serverNextIndex
        : Math.min(currentIndex + 1, blocks.length - 1);
    setVisiblePageIndex(nextIndex);
    carouselRef.current?.scrollTo({
      x: nextIndex * responsiveLayout.stride,
      animated: true,
    });
    setBurstKey((current) => current + 1);
    onBlockStatusChange?.(block.id, 'COMPLETED');
  };

  const applyPendingBlock = (block: WorkoutViewBlock) => {
    const blockIndex = blocks.findIndex((item) => item.id === block.id);
    setCompletedBlockIds((current) =>
      current.filter((completedId) => completedId !== block.id),
    );
    if (blockIndex >= 0) {
      setVisiblePageIndex(blockIndex);
      carouselRef.current?.scrollTo({
        x: blockIndex * responsiveLayout.stride,
        animated: true,
      });
    }
    onBlockStatusChange?.(block.id, 'PENDING');
  };

  const smashCurrentBlock = async () => {
    if (!canSmash) {
      return;
    }
    const block = blocks[currentIndex];
    if (!block || completedBlockIds.includes(block.id)) {
      return;
    }
    if (apiConfig === undefined) {
      applyCompletedBlock(block);
      if (completedBlockIds.length + 1 === blocks.length) {
        setPaused(true);
        setPreviewResult('completed');
      }
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      const response = await apiConfig.api.updateSessionItem(
        apiConfig.sessionId,
        block.id,
        'COMPLETED',
        new Date().toISOString(),
      );
      if (response.item.status_code === 'COMPLETED') {
        applyCompletedBlock(block, response.next_pending_plan_item_id);
        if (response.completed_item_count === response.total_item_count) {
          await finalizeServerSession();
        }
      }
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const reopenBlock = async (block: WorkoutViewBlock) => {
    if (
      !completedBlockIds.includes(block.id) ||
      overlay !== 'none' ||
      actionPending ||
      !sessionReady
    ) {
      return;
    }
    if (apiConfig === undefined) {
      applyPendingBlock(block);
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      const response = await apiConfig.api.updateSessionItem(
        apiConfig.sessionId,
        block.id,
        'PENDING',
        new Date().toISOString(),
      );
      if (response.item.status_code === 'PENDING') {
        applyPendingBlock(block);
      }
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const openRest = () => {
    setRestSeconds(60);
    setPaused(true);
    setOverlay('rest');
    recordTimerChange('PAUSE');
    onPauseChange?.(true);
    onRestChange?.(true);
  };

  const closeRest = () => {
    setRestSeconds(0);
    setOverlay('none');
    setPaused(false);
    recordTimerChange('RESUME');
    onPauseChange?.(false);
    onRestChange?.(false);
  };

  const openSafety = () => {
    setApiError(null);
    setPaused(true);
    setOverlay('safety');
    recordTimerChange('PAUSE');
    onPauseChange?.(true);
  };

  const closeSheets = () => {
    setOverlay('none');
    setPaused(false);
    recordTimerChange('RESUME');
    onPauseChange?.(false);
  };

  const finishWorkout = async () => {
    if (apiConfig === undefined || actionPending || !sessionReady) {
      onSafetyStopRequest?.();
      return;
    }
    if (completedCount === 0) {
      setOverlay('not-completed');
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      await finalizeServerSession();
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const submitNotCompleted = async (reasonCode: string) => {
    onNotCompleted?.(reasonCode);
    if (apiConfig === undefined) {
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      const result = await apiConfig.api.markNotCompleted(
        apiConfig.sessionId,
        new Date().toISOString(),
        reasonCode as NotCompletedReasonCode,
      );
      setPaused(true);
      apiConfig.onOutcome({ kind: 'notCompleted', result });
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const submitApiSafetyEvent = async () => {
    if (
      apiConfig === undefined ||
      (selectedBodyAreas.length === 0 && selectedReactions.length === 0)
    ) {
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      const event = await apiConfig.api.reportSafetyEvent(apiConfig.sessionId, {
        occurred_at: new Date().toISOString(),
        discomforts: selectedBodyAreas.map((bodyAreaCode) => ({
          body_area_code: bodyAreaCode,
          severity_code: selectedBodySeverities[bodyAreaCode] ?? 'MILD',
        })),
        adverse_reaction_codes: [...selectedReactions],
      });
      if (event.session_status_code === 'STOPPED_FOR_SAFETY') {
        setPaused(true);
        apiConfig.onOutcome({ kind: 'safetyStop', event });
        return;
      }
      setApiGuidance(event.guidance);
      setOverlay('api-guidance');
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const submitAdditionalActivity = async () => {
    if (apiConfig === undefined) {
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      await apiConfig.api.recordAdditionalActivity(apiConfig.sessionId, {
        activity_type_code: additionalActivityType,
        duration_seconds: additionalDurationMinutes * 60,
        intensity_code: additionalIntensity,
        note: additionalNote.trim() === '' ? null : additionalNote.trim(),
      });
      setAdditionalSaved(true);
      setOverlay('none');
      setPaused(false);
      recordTimerChange('RESUME');
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const toggleBodyArea = (code: string) => {
    setSelectedBodySeverities((current) => {
      if (current[code] !== undefined) {
        const remaining = { ...current };
        delete remaining[code];
        return remaining;
      }
      return { ...current, [code]: 'MILD' };
    });
  };

  const selectBodySeverity = (
    code: string,
    severity: WorkoutSafetyReport['severityCode'],
  ) => {
    setSelectedBodySeverities((current) => ({
      ...current,
      [code]: severity,
    }));
  };

  const toggleReaction = (code: string) => {
    setSelectedReactions((current) =>
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code],
    );
  };

  const submitSafetyEvent = () => {
    const report: WorkoutSafetyReport = {
      symptomCode: selectedSymptom,
      severityCode: selectedSeverity,
    };
    const instruction = fixture.instruction ?? 'SHOW_CAUTION';
    onSafetyEvent?.(report, instruction);
    if (instruction === 'SHOW_CAUTION') {
      closeSheets();
    } else {
      onSafetyStopRequest?.();
    }
  };

  const selectVisiblePage = (index: number) => {
    setVisiblePageIndex(index);
    carouselRef.current?.scrollTo({
      x: index * responsiveLayout.stride,
      animated: true,
    });
  };

  const handleCarouselLayout = (event: LayoutChangeEvent) => {
    setCarouselWidth(event.nativeEvent.layout.width);
  };

  const handleMomentumEnd = (
    event: NativeSyntheticEvent<NativeScrollEvent>,
  ) => {
    setVisiblePageIndex(
      clampWorkoutPageIndex(
        event.nativeEvent.contentOffset.x,
        blocks.length,
        responsiveLayout.stride,
      ),
    );
  };

  if (previewResult !== 'none') {
    return (
      <ResultScreen
        blocks={blocks}
        elapsedSeconds={elapsedSeconds}
        onBackHome={onBackHome}
        reportNote={fixture.reportNote}
        result={previewResult}
        useJua={useJua}
      />
    );
  }

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="light" />
      <View
        style={[
          styles.timerHeader,
          { paddingTop: responsiveLayout.headerTopPadding },
        ]}
      >
        <View
          style={[
            styles.timerHeaderContent,
            { maxWidth: responsiveLayout.contentMaxWidth },
          ]}
        >
          <View testID="workout-header-top-row" style={styles.headerTopRow}>
            <View style={styles.timerCopy}>
              <Text style={styles.timerCaption}>{timerCaption}</Text>
              <Text
                accessibilityLabel={`운동 시간 ${formatWorkoutTime(elapsedSeconds)}`}
                style={[
                  styles.timer,
                  useJua && styles.jua,
                  paused && styles.timerPaused,
                ]}
              >
                {formatWorkoutTime(elapsedSeconds)}
              </Text>
            </View>
            <View style={styles.timerActions}>
              <Pressable
                accessibilityLabel={paused ? '재개' : '일시정지'}
                accessibilityRole="button"
                onPress={togglePaused}
                style={({ pressed }) => [
                  styles.roundAction,
                  pressed && styles.pressed,
                ]}
                testID="workout-pause-action"
              >
                <PlaybackMark paused={paused} />
              </Pressable>
              <Pressable
                accessibilityLabel="안전 중단 및 이상 반응 보고"
                accessibilityRole="button"
                onPress={openSafety}
                style={({ pressed }) => [
                  styles.stopAction,
                  pressed && styles.pressed,
                ]}
                testID="workout-stop-action"
              >
                <Text style={styles.stopActionLabel}>중단</Text>
              </Pressable>
            </View>
          </View>
          <View
            accessibilityLabel="운동 블록 진행률"
            style={styles.progressRow}
          >
            {blocks.map((block, index) => (
              <View
                key={block.id}
                style={[
                  styles.progressSegment,
                  block.status === 'COMPLETED'
                    ? styles.progressSegmentDone
                    : index === currentIndex
                      ? styles.progressSegmentCurrent
                      : null,
                ]}
              />
            ))}
          </View>
          <View style={styles.routineHeader}>
            <Text
              accessibilityRole="header"
              numberOfLines={1}
              style={styles.routineTitle}
            >
              {apiConfig === undefined
                ? '전신 기본 루틴'
                : `${trainingTypeLabel(apiConfig.plan.training_type_code)} 루틴`}
            </Text>
            <Text style={styles.routineStep}>
              {Math.min(currentIndex + 1, blocks.length)} / {blocks.length} 블록
            </Text>
          </View>
        </View>
      </View>

      {fixture.offline ? <OfflineBanner /> : null}
      {apiConfig !== undefined && !sessionReady && apiError === null ? (
        <ApiBanner message="운동 세션을 준비하고 있어요…" tone="neutral" />
      ) : null}
      {apiError ? <ApiBanner message={apiError} tone="error" /> : null}
      {additionalSaved ? (
        <ApiBanner message="계획 외 활동 기록을 저장했어요." tone="success" />
      ) : null}

      <MascotStage
        blockName={currentBlock.name}
        burstKey={burstKey}
        burstOpacity={burstOpacity}
        burstScale={burstScale}
        height={responsiveLayout.mascotHeight}
        maxWidth={responsiveLayout.contentMaxWidth}
        serious={isSafetyState}
        useJua={useJua}
      />

      <View
        style={[
          styles.carouselRegion,
          { maxWidth: responsiveLayout.contentMaxWidth },
        ]}
      >
        <View style={styles.carouselGuide}>
          <Text style={styles.carouselHint}>
            {visiblePageIndex === currentIndex
              ? '좌우로 밀어 다른 블록 보기'
              : '다른 블록 보는 중'}
          </Text>
          <Text style={styles.carouselCount}>
            완료 {completedCount} / {blocks.length}
          </Text>
        </View>

        <Animated.ScrollView
          ref={carouselRef}
          contentContainerStyle={[
            styles.blockCarousel,
            { gap: responsiveLayout.gap, paddingHorizontal: carouselPadding },
          ]}
          decelerationRate="fast"
          horizontal
          onLayout={handleCarouselLayout}
          onMomentumScrollEnd={handleMomentumEnd}
          onScroll={Animated.event(
            [{ nativeEvent: { contentOffset: { x: scrollX } } }],
            { useNativeDriver: true },
          )}
          scrollEventThrottle={16}
          showsHorizontalScrollIndicator={false}
          snapToAlignment="start"
          snapToInterval={responsiveLayout.stride}
          testID="workout-carousel"
        >
          {blocks.map((block, index) => (
            <ArcBlockCard
              key={block.id}
              block={block}
              current={index === currentIndex && !allBlocksCompleted}
              index={index}
              expanded={detailBlockId === block.id}
              hasDetails={
                block.tips.length > 0 ||
                (apiConfig !== undefined &&
                  block.exerciseId !== undefined &&
                  Boolean(block.instructionAvailable))
              }
              layout={responsiveLayout}
              onToggleExpanded={() =>
                setDetailBlockId((current) =>
                  current === block.id ? null : block.id,
                )
              }
              onUndo={
                block.status === 'COMPLETED'
                  ? () => void reopenBlock(block)
                  : undefined
              }
              scrollX={scrollX}
            />
          ))}
        </Animated.ScrollView>

        <View style={styles.dotRow}>
          {blocks.map((block, index) => {
            const active = index === visiblePageIndex;
            const done = block.status === 'COMPLETED';
            return (
              <Pressable
                key={block.id}
                accessibilityLabel={`${index + 1}번째 블록 보기`}
                accessibilityRole="button"
                onPress={() => selectVisiblePage(index)}
                style={[
                  styles.dot,
                  active && styles.dotActive,
                  done
                    ? styles.dotDone
                    : active
                      ? styles.dotVisiblePending
                      : null,
                ]}
                testID={`workout-dot-${index}`}
              />
            );
          })}
        </View>
      </View>

      <View
        style={[
          styles.bottomBar,
          { maxWidth: responsiveLayout.contentMaxWidth },
        ]}
      >
        <Pressable
          accessibilityLabel={
            canFinish ? '운동 마치기' : `${currentBlock.name} 블록 격파`
          }
          accessibilityRole="button"
          accessibilityState={{ disabled: !(canSmash || canFinish) }}
          disabled={!(canSmash || canFinish)}
          onPress={() => {
            if (allBlocksCompleted && apiConfig !== undefined) {
              void finishWorkout();
            } else {
              void smashCurrentBlock();
            }
          }}
          style={({ pressed }) => [
            styles.smashAction,
            !(canSmash || canFinish) && styles.smashActionDisabled,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.smashActionText, useJua && styles.jua]}>
            {actionPending
              ? '저장 중…'
              : allBlocksCompleted && apiConfig !== undefined
                ? '운동 마치기'
                : '블록 격파'}
          </Text>
        </Pressable>
        <Pressable
          accessibilityLabel="선택 휴식 타이머"
          accessibilityRole="button"
          onPress={openRest}
          style={({ pressed }) => [
            styles.restAction,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.restActionText}>휴식</Text>
        </Pressable>
        {apiConfig !== undefined ? (
          <Pressable
            accessibilityLabel="계획 외 활동 기록"
            accessibilityRole="button"
            disabled={!sessionReady || actionPending}
            onPress={() => {
              setApiError(null);
              setAdditionalSaved(false);
              setOverlay('additional');
              setPaused(true);
              recordTimerChange('PAUSE');
            }}
            style={({ pressed }) => [
              styles.additionalAction,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.restActionText}>추가 기록</Text>
          </Pressable>
        ) : null}
      </View>

      {detailBlock && overlay === 'none' ? (
        <ExerciseDetailOverlay
          block={detailBlock}
          detail={
            apiConfig !== undefined && detailBlock.exerciseId !== undefined ? (
              <ExerciseDetailSheet
                api={apiConfig.api}
                exerciseId={detailBlock.exerciseId}
              />
            ) : (
              <View style={styles.tipList}>
                {detailBlock.tips.map((tip) => (
                  <Text key={tip} style={styles.tipText}>
                    {tip}
                  </Text>
                ))}
              </View>
            )
          }
          onClose={() => setDetailBlockId(null)}
        />
      ) : null}

      {overlay === 'rest' ? (
        <RestSheet
          onAddSeconds={() => setRestSeconds((current) => current + 30)}
          onClose={closeRest}
          restSeconds={restSeconds}
          useJua={useJua}
        />
      ) : null}
      {overlay === 'not-completed' ? (
        <NotCompletedSheet
          error={apiConfig === undefined ? null : apiError}
          onClose={closeSheets}
          onSelect={(reasonCode) => void submitNotCompleted(reasonCode)}
          pending={actionPending}
        />
      ) : null}
      {overlay === 'safety' ? (
        <SafetyConfirmSheet
          completedCount={completedCount}
          elapsedSeconds={elapsedSeconds}
          onClose={closeSheets}
          onOpenReport={() =>
            setOverlay(apiConfig === undefined ? 'symptom' : 'api-safety')
          }
          onStop={() => void finishWorkout()}
          totalCount={blocks.length}
        />
      ) : null}
      {overlay === 'symptom' ? (
        <SymptomSheet
          instruction={fixture.instruction ?? 'SHOW_CAUTION'}
          onClose={closeSheets}
          onSelectSeverity={setSelectedSeverity}
          onSelectSymptom={setSelectedSymptom}
          onSubmit={submitSafetyEvent}
          selectedSeverity={selectedSeverity}
          selectedSymptom={selectedSymptom}
        />
      ) : null}
      {overlay === 'api-safety' ? (
        <ApiSafetySheet
          error={apiError}
          onClose={closeSheets}
          onToggleBodyArea={toggleBodyArea}
          onToggleReaction={toggleReaction}
          onSelectBodySeverity={selectBodySeverity}
          onSubmit={() => void submitApiSafetyEvent()}
          pending={actionPending}
          selectedBodySeverities={selectedBodySeverities}
          selectedReactions={selectedReactions}
        />
      ) : null}
      {overlay === 'api-guidance' && apiGuidance ? (
        <ApiGuidanceSheet
          guidance={apiGuidance}
          onConfirm={() => {
            setApiGuidance(null);
            closeSheets();
          }}
        />
      ) : null}
      {overlay === 'additional' ? (
        <AdditionalActivitySheet
          activityType={additionalActivityType}
          durationMinutes={additionalDurationMinutes}
          error={apiError}
          intensity={additionalIntensity}
          note={additionalNote}
          onClose={() => {
            closeSheets();
          }}
          onSelectDuration={setAdditionalDurationMinutes}
          onSelectIntensity={setAdditionalIntensity}
          onSelectType={setAdditionalActivityType}
          onChangeNote={setAdditionalNote}
          onSubmit={() => void submitAdditionalActivity()}
          pending={actionPending}
        />
      ) : null}
    </SafeAreaView>
  );
}

function firstPendingIndex(
  blocks: readonly Pick<WorkoutBlock, 'id'>[],
  completedBlockIds: readonly string[],
) {
  const index = blocks.findIndex(
    (block) => !completedBlockIds.includes(block.id),
  );
  return index === -1 ? Math.max(0, blocks.length - 1) : index;
}

function PlaybackMark({ paused }: { paused: boolean }) {
  if (paused) {
    return <View style={styles.playMark} />;
  }
  return (
    <View accessibilityElementsHidden style={styles.pauseMark}>
      <View style={styles.pauseBar} />
      <View style={styles.pauseBar} />
    </View>
  );
}

function MascotStage({
  blockName,
  burstKey,
  burstOpacity,
  burstScale,
  height,
  maxWidth,
  serious,
  useJua,
}: {
  blockName: string;
  burstKey: number;
  burstOpacity: Animated.Value;
  burstScale: Animated.Value;
  height: number;
  maxWidth: number;
  serious: boolean;
  useJua: boolean;
}) {
  return (
    <View
      accessibilityLabel={serious ? '안전 안내 화면' : `${blockName} 운동 안내`}
      style={[
        styles.mascotStage,
        { height, maxWidth },
        serious && styles.mascotStageSerious,
      ]}
    >
      {serious ? (
        <View style={[styles.mascot, styles.mascotSerious]}>
          <Text style={styles.mascotMark}>!</Text>
        </View>
      ) : (
        <Image
          accessible={false}
          resizeMode="contain"
          source={imageAssets.mascotWarmupWalk}
          style={styles.mascotAnimation}
          testID="workout-warmup-mascot"
        />
      )}
      <View style={styles.mascotCopy}>
        <Text style={styles.mascotEyebrow}>
          {serious ? '안전을 먼저 확인해주세요' : '지금 할 운동'}
        </Text>
        <Text style={styles.mascotTitle}>
          {serious ? '운동을 멈춘 상태예요' : blockName}
        </Text>
        <Text style={styles.mascotCaption}>
          {serious
            ? '안내를 확인하기 전에는 운동을 재개하지 않아요.'
            : '내 속도에 맞춰 정확하게 진행해요.'}
        </Text>
      </View>
      {burstKey > 0 ? (
        <Animated.Text
          key={burstKey}
          pointerEvents="none"
          style={[
            styles.burstText,
            useJua && styles.jua,
            { opacity: burstOpacity, transform: [{ scale: burstScale }] },
          ]}
          testID="workout-smash-burst"
        >
          격파!
        </Animated.Text>
      ) : null}
    </View>
  );
}

function ArcBlockCard({
  block,
  current,
  expanded,
  hasDetails,
  index,
  layout,
  onToggleExpanded,
  onUndo,
  scrollX,
}: {
  block: WorkoutViewBlock;
  current: boolean;
  expanded: boolean;
  hasDetails: boolean;
  index: number;
  layout: WorkoutResponsiveLayout;
  onToggleExpanded: () => void;
  onUndo?: () => void;
  scrollX: Animated.Value;
}) {
  const inputRange = WORKOUT_ARC.INPUT_OFFSETS.map(
    (offset) => (index + offset) * layout.stride,
  );
  const rotate = scrollX.interpolate({
    extrapolate: 'clamp',
    inputRange,
    outputRange: [...WORKOUT_ARC.ROTATE],
  });
  const scale = scrollX.interpolate({
    extrapolate: 'clamp',
    inputRange,
    outputRange: [...WORKOUT_ARC.SCALE],
  });
  const lift = scrollX.interpolate({
    extrapolate: 'clamp',
    inputRange,
    outputRange: [...WORKOUT_ARC.LIFT],
  });
  const opacity = scrollX.interpolate({
    extrapolate: 'clamp',
    inputRange,
    outputRange: [...WORKOUT_ARC.OPACITY],
  });
  const done = block.status === 'COMPLETED';
  const badgeLabel = done ? '완료' : current ? '진행 중' : 'PENDING';

  return (
    <Animated.View
      style={[
        styles.blockCard,
        { height: layout.cardHeight, width: layout.cardWidth },
        current
          ? styles.blockCardCurrent
          : done
            ? styles.blockCardDone
            : styles.blockCardPending,
        {
          opacity,
          transform: [
            { translateY: layout.cardHeight / 2 },
            { rotate },
            { translateY: -layout.cardHeight / 2 },
            { translateY: lift },
            { scale },
          ],
        },
      ]}
      testID={`workout-card-${index}`}
    >
      <View style={styles.blockCardHeader}>
        <View
          style={[
            styles.blockBadge,
            current
              ? styles.blockBadgeCurrent
              : done
                ? styles.blockBadgeDone
                : null,
          ]}
        >
          <Text
            style={[
              styles.blockBadgeText,
              (current || done) && styles.blockBadgeTextEmphasis,
              current && styles.blockBadgeTextCurrent,
            ]}
          >
            {badgeLabel}
          </Text>
        </View>
        <Text style={styles.blockOrder}>{index + 1}번째 블록</Text>
      </View>
      <Text style={[styles.blockName, done && styles.blockNameDone]}>
        {block.name}
      </Text>
      <Text style={[styles.blockMeta, current && styles.blockMetaCurrent]}>
        {block.meta}
      </Text>
      {done && onUndo ? (
        <Pressable
          accessibilityLabel={`${block.name} 완료 취소`}
          accessibilityRole="button"
          onPress={onUndo}
          style={styles.undoButton}
        >
          <Text style={styles.undoButtonText}>완료 취소</Text>
        </Pressable>
      ) : null}
      {hasDetails ? (
        <Pressable
          accessibilityLabel={expanded ? '설명 접기' : '자세 · 설명 보기'}
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={onToggleExpanded}
          style={styles.infoButton}
        >
          <Text style={styles.infoButtonText}>
            {expanded ? '설명 보는 중' : '자세 · 설명 보기'}
          </Text>
        </Pressable>
      ) : null}
    </Animated.View>
  );
}

function ExerciseDetailOverlay({
  block,
  detail,
  onClose,
}: {
  block: WorkoutViewBlock;
  detail: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <View
      accessibilityLabel={`${block.name} 자세와 설명`}
      accessibilityViewIsModal
      style={styles.sheetOverlay}
      testID="workout-detail-overlay"
    >
      <View
        style={[styles.sheet, styles.detailSheet]}
        testID="workout-detail-sheet"
      >
        <View style={styles.sheetHandle} />
        <View style={styles.detailSheetHeader}>
          <View style={styles.detailSheetHeading}>
            <Text style={styles.detailSheetEyebrow}>운동 자세와 설명</Text>
            <Text
              accessibilityRole="header"
              style={[styles.sheetTitle, styles.detailSheetTitle]}
            >
              {block.name}
            </Text>
          </View>
          <Pressable
            accessibilityLabel="설명 접기"
            accessibilityRole="button"
            accessibilityState={{ expanded: true }}
            onPress={onClose}
            style={styles.detailCloseButton}
          >
            <Text style={styles.detailCloseButtonText}>닫기</Text>
          </Pressable>
        </View>
        <ScrollView
          contentContainerStyle={styles.detailSheetContent}
          nestedScrollEnabled
          showsVerticalScrollIndicator
          style={styles.detailSheetScroll}
          testID="workout-detail-scroll"
        >
          {detail}
        </ScrollView>
      </View>
    </View>
  );
}

function OfflineBanner() {
  return (
    <View accessibilityRole="alert" style={styles.offlineBanner}>
      <View style={styles.offlineDot} />
      <Text style={styles.offlineText}>
        연결이 끊겼어요. 진행 상태는 기기에 임시 저장되고, 연결되면 자동으로
        올려드려요.
      </Text>
    </View>
  );
}

function ApiBanner({
  message,
  tone,
}: {
  message: string;
  tone: 'neutral' | 'error' | 'success';
}) {
  return (
    <View
      accessibilityRole={tone === 'error' ? 'alert' : undefined}
      style={[
        styles.apiBanner,
        tone === 'error' && styles.apiBannerError,
        tone === 'success' && styles.apiBannerSuccess,
      ]}
    >
      <Text
        style={[
          styles.apiBannerText,
          tone === 'error' && styles.apiBannerTextError,
        ]}
      >
        {message}
      </Text>
    </View>
  );
}

function RestSheet({
  onAddSeconds,
  onClose,
  restSeconds,
  useJua,
}: {
  onAddSeconds: () => void;
  onClose: () => void;
  restSeconds: number;
  useJua: boolean;
}) {
  return (
    <View accessibilityViewIsModal style={styles.restSheet}>
      <View style={styles.restSheetRow}>
        <View>
          <Text style={styles.restLabel}>선택 휴식</Text>
          <Text
            accessibilityLabel={`남은 휴식 ${formatWorkoutTime(restSeconds)}`}
            style={[styles.restTimer, useJua && styles.jua]}
          >
            {formatWorkoutTime(restSeconds)}
          </Text>
        </View>
        <View style={styles.restActions}>
          <Pressable
            accessibilityRole="button"
            onPress={onAddSeconds}
            style={styles.restAddButton}
          >
            <Text style={styles.restAddButtonText}>+30초</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={onClose}
            style={styles.restEndButton}
          >
            <Text style={[styles.restEndButtonText, useJua && styles.jua]}>
              휴식 끝
            </Text>
          </Pressable>
        </View>
      </View>
      <Text style={styles.restDescription}>
        휴식 타이머는 선택 사항이에요. 완료 상태는 직접 체크할 때만 바뀝니다.
      </Text>
    </View>
  );
}

function SheetFrame({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <View accessibilityViewIsModal style={styles.sheetOverlay}>
      <View style={styles.sheet}>
        <View style={styles.sheetHandle} />
        <Text accessibilityRole="header" style={styles.sheetTitle}>
          {title}
        </Text>
        {children}
      </View>
    </View>
  );
}

function SafetyConfirmSheet({
  completedCount,
  elapsedSeconds,
  onClose,
  onOpenReport,
  onStop,
  totalCount,
}: {
  completedCount: number;
  elapsedSeconds: number;
  onClose: () => void;
  onOpenReport: () => void;
  onStop?: () => void;
  totalCount: number;
}) {
  return (
    <SheetFrame title="지금 운동을 중단할까요?">
      <Text style={styles.sheetDescription}>
        경과 {formatWorkoutTime(elapsedSeconds)} · {completedCount}/{totalCount}
        블록 완료. 여기까지 완료한 블록은 그대로 기록돼요.
      </Text>
      <Pressable
        accessibilityRole="button"
        onPress={onStop}
        style={styles.dangerButton}
      >
        <Text style={styles.dangerButtonText}>중단하기</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={onOpenReport}
        style={styles.outlineButtonWide}
      >
        <Text style={styles.outlineButtonText}>
          불편·이상 반응 먼저 보고하기
        </Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={onClose}
        style={styles.textButton}
      >
        <Text style={styles.textButtonLabel}>계속 운동하기</Text>
      </Pressable>
    </SheetFrame>
  );
}

function SymptomSheet({
  instruction,
  onClose,
  onSelectSeverity,
  onSelectSymptom,
  onSubmit,
  selectedSeverity,
  selectedSymptom,
}: {
  instruction: WorkoutSafetyInstruction;
  onClose: () => void;
  onSelectSeverity: (severity: WorkoutSafetyReport['severityCode']) => void;
  onSelectSymptom: (symptom: WorkoutSafetyReport['symptomCode']) => void;
  onSubmit: () => void;
  selectedSeverity: WorkoutSafetyReport['severityCode'];
  selectedSymptom: WorkoutSafetyReport['symptomCode'];
}) {
  const severe = instruction !== 'SHOW_CAUTION';
  const guidance =
    instruction === 'STOP_AND_SEEK_HELP'
      ? SAFETY_GUIDANCE.emergency
      : instruction === 'STOP_SESSION'
        ? SAFETY_GUIDANCE.severePain
        : SAFETY_GUIDANCE.mild;

  return (
    <SheetFrame title="불편·이상 반응 보고">
      <ScrollView showsVerticalScrollIndicator={false}>
        <Text style={styles.choiceTitle}>어떤 일이 있었나요?</Text>
        <View style={styles.choiceWrap}>
          {WORKOUT_SYMPTOMS.map((symptom) => (
            <ChoiceButton
              key={symptom.code}
              label={symptom.label}
              onPress={() => onSelectSymptom(symptom.code)}
              selected={selectedSymptom === symptom.code}
            />
          ))}
        </View>
        <Text style={styles.choiceTitle}>정도는 어떤가요?</Text>
        <View style={styles.choiceWrap}>
          {WORKOUT_SEVERITIES.map((severity) => (
            <ChoiceButton
              key={severity.code}
              label={severity.label}
              onPress={() => onSelectSeverity(severity.code)}
              selected={selectedSeverity === severity.code}
            />
          ))}
        </View>
        <View style={[styles.guidance, severe && styles.guidanceSevere]}>
          <Text
            style={[styles.guidanceText, severe && styles.guidanceTextSevere]}
          >
            {guidance}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={onSubmit}
          style={styles.dangerButton}
        >
          <Text style={styles.dangerButtonText}>
            {severe ? '보고하고 안전 중단' : '보고만 하고 계속하기'}
          </Text>
        </Pressable>
        {!severe ? (
          <Pressable
            accessibilityRole="button"
            onPress={onClose}
            style={styles.textButton}
          >
            <Text style={styles.textButtonLabel}>취소</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SheetFrame>
  );
}

function ApiSafetySheet({
  error,
  onClose,
  onSelectBodySeverity,
  onToggleBodyArea,
  onToggleReaction,
  onSubmit,
  pending,
  selectedBodySeverities,
  selectedReactions,
}: {
  error: string | null;
  onClose: () => void;
  onSelectBodySeverity: (
    code: string,
    severity: WorkoutSafetyReport['severityCode'],
  ) => void;
  onToggleBodyArea: (code: string) => void;
  onToggleReaction: (code: string) => void;
  onSubmit: () => void;
  pending: boolean;
  selectedBodySeverities: Readonly<
    Record<string, WorkoutSafetyReport['severityCode']>
  >;
  selectedReactions: readonly string[];
}) {
  const selectedBodyAreas = Object.keys(selectedBodySeverities);
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    selectedBodyAreas.some((code) =>
      EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );
  const canSubmit =
    selectedBodyAreas.length > 0 || selectedReactions.length > 0;
  return (
    <SheetFrame title="불편·이상 반응 보고">
      <ScrollView showsVerticalScrollIndicator={false}>
        <Text style={styles.sheetDescription}>
          선택한 내용을 서버의 안전 기준으로 확인한 뒤 계속 여부를 안내해요.
        </Text>
        <Text style={styles.choiceTitle}>불편한 부위</Text>
        <View style={styles.choiceWrap}>
          {DEFAULT_BODY_AREA_OPTIONS.map((option) => (
            <ChoiceButton
              key={option.code}
              label={option.label}
              multiple
              onPress={() => onToggleBodyArea(option.code)}
              selected={selectedBodyAreas.includes(option.code)}
            />
          ))}
          <ChoiceButton
            label={showExtendedAreas ? '다른 부위 접기' : '다른 부위 더 보기'}
            multiple
            onPress={() => setShowExtendedAreas((visible) => !visible)}
            selected={showExtendedAreas}
          />
          {showExtendedAreas
            ? EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                <ChoiceButton
                  key={option.code}
                  label={option.label}
                  multiple
                  onPress={() => onToggleBodyArea(option.code)}
                  selected={selectedBodyAreas.includes(option.code)}
                />
              ))
            : null}
        </View>
        {selectedBodyAreas.map((bodyAreaCode) => {
          const bodyArea = bodyAreaLabel(bodyAreaCode);
          return (
            <View key={bodyAreaCode}>
              <Text style={styles.choiceTitle}>{bodyArea} 불편함 정도</Text>
              <View style={styles.choiceWrap}>
                {WORKOUT_SEVERITIES.map((severity) => (
                  <ChoiceButton
                    key={severity.code}
                    accessibilityLabel={`${bodyArea} ${severity.label}`}
                    label={severity.label}
                    onPress={() =>
                      onSelectBodySeverity(bodyAreaCode, severity.code)
                    }
                    selected={
                      selectedBodySeverities[bodyAreaCode] === severity.code
                    }
                  />
                ))}
              </View>
            </View>
          );
        })}
        <Text style={styles.choiceTitle}>이상 반응</Text>
        <View style={styles.choiceWrap}>
          {ADVERSE_REACTION_OPTIONS.map((option) => (
            <ChoiceButton
              key={option.code}
              label={option.label}
              multiple
              onPress={() => onToggleReaction(option.code)}
              selected={selectedReactions.includes(option.code)}
            />
          ))}
        </View>
        {error ? <Text style={styles.inlineError}>{error}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: pending || !canSubmit }}
          disabled={pending || !canSubmit}
          onPress={onSubmit}
          style={[
            styles.dangerButton,
            (pending || !canSubmit) && styles.actionDisabled,
          ]}
        >
          <Text style={styles.dangerButtonText}>
            {pending ? '확인 중…' : '보고하고 안전 안내 확인'}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={onClose}
          style={styles.textButton}
        >
          <Text style={styles.textButtonLabel}>취소</Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

function ApiGuidanceSheet({
  guidance,
  onConfirm,
}: {
  guidance: string;
  onConfirm: () => void;
}) {
  return (
    <SheetFrame title="안전 안내">
      <View style={[styles.guidance, styles.guidanceSevere]}>
        <Text style={[styles.guidanceText, styles.guidanceTextSevere]}>
          {guidance}
        </Text>
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={onConfirm}
        style={styles.outlineButtonWide}
      >
        <Text style={styles.outlineButtonText}>확인했어요</Text>
      </Pressable>
    </SheetFrame>
  );
}

function AdditionalActivitySheet({
  activityType,
  durationMinutes,
  error,
  intensity,
  note,
  onChangeNote,
  onClose,
  onSelectDuration,
  onSelectIntensity,
  onSelectType,
  onSubmit,
  pending,
}: {
  activityType: string;
  durationMinutes: number;
  error: string | null;
  intensity: string;
  note: string;
  onChangeNote: (note: string) => void;
  onClose: () => void;
  onSelectDuration: (minutes: number) => void;
  onSelectIntensity: (code: string) => void;
  onSelectType: (code: string) => void;
  onSubmit: () => void;
  pending: boolean;
}) {
  return (
    <SheetFrame title="계획 외 활동 기록">
      <ScrollView showsVerticalScrollIndicator={false}>
        <Text style={styles.sheetDescription}>
          계획한 블록과 별개로 추가 활동을 남겨요. 이 기록은 운동 완료 상태를
          바꾸지 않아요.
        </Text>
        <Text style={styles.choiceTitle}>활동 종류</Text>
        <View style={styles.choiceWrap}>
          {ADDITIONAL_ACTIVITY_TYPES.map((option) => (
            <ChoiceButton
              key={option.code}
              label={option.label}
              onPress={() => onSelectType(option.code)}
              selected={activityType === option.code}
            />
          ))}
        </View>
        <Text style={styles.choiceTitle}>활동 시간</Text>
        <View style={styles.choiceWrap}>
          {[10, 20, 30].map((minutes) => (
            <ChoiceButton
              key={minutes}
              label={`${minutes}분`}
              onPress={() => onSelectDuration(minutes)}
              selected={durationMinutes === minutes}
            />
          ))}
        </View>
        <Text style={styles.choiceTitle}>강도</Text>
        <View style={styles.choiceWrap}>
          {ACTIVITY_INTENSITIES.map((option) => (
            <ChoiceButton
              key={option.code}
              label={option.label}
              onPress={() => onSelectIntensity(option.code)}
              selected={intensity === option.code}
            />
          ))}
        </View>
        <Text style={styles.choiceTitle}>메모 (선택)</Text>
        <TextInput
          accessibilityLabel="추가 활동 메모"
          maxLength={500}
          multiline
          onChangeText={onChangeNote}
          placeholder="활동 내용을 간단히 남겨주세요"
          style={styles.noteInput}
          value={note}
        />
        {error ? <Text style={styles.inlineError}>{error}</Text> : null}
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={onSubmit}
          style={[styles.outlineButtonWide, pending && styles.actionDisabled]}
        >
          <Text style={styles.outlineButtonText}>
            {pending ? '저장 중…' : '추가 활동 저장'}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={onClose}
          style={styles.textButton}
        >
          <Text style={styles.textButtonLabel}>돌아가기</Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

function ChoiceButton({
  accessibilityLabel,
  label,
  multiple = false,
  onPress,
  selected,
}: {
  accessibilityLabel?: string;
  label: string;
  multiple?: boolean;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={multiple ? 'checkbox' : 'radio'}
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.choiceButton, selected && styles.choiceButtonSelected]}
    >
      <Text
        style={[
          styles.choiceButtonText,
          selected && styles.choiceButtonTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function NotCompletedSheet({
  error,
  onClose,
  onSelect,
  pending,
}: {
  error: string | null;
  onClose: () => void;
  onSelect: (reasonCode: string) => void;
  pending: boolean;
}) {
  return (
    <SheetFrame title="오늘 운동을 마치지 못한 이유">
      <Text style={styles.sheetDescription}>
        남긴 이유는 다음 추천을 위한 참고 정보로만 사용해요.
      </Text>
      <View style={styles.reasonList}>
        {NOT_COMPLETED_REASONS.map((reason) => (
          <Pressable
            key={reason.code}
            accessibilityRole="button"
            disabled={pending}
            onPress={() => onSelect(reason.code)}
            style={[styles.reasonButton, pending && styles.actionDisabled]}
          >
            <Text style={styles.reasonButtonText}>{reason.label}</Text>
          </Pressable>
        ))}
      </View>
      {error ? <Text style={styles.inlineError}>{error}</Text> : null}
      <Pressable
        accessibilityRole="button"
        disabled={pending}
        onPress={onClose}
        style={styles.textButton}
      >
        <Text style={styles.textButtonLabel}>돌아가기</Text>
      </Pressable>
    </SheetFrame>
  );
}

function ResultScreen({
  blocks,
  elapsedSeconds,
  onBackHome,
  reportNote,
  result,
  useJua,
}: {
  blocks: readonly WorkoutViewBlock[];
  elapsedSeconds: number;
  onBackHome?: () => void;
  reportNote?: string;
  result: Exclude<WorkoutResult, 'none'>;
  useJua: boolean;
}) {
  const stopped = result === 'stopped';
  const completedCount = blocks.filter(
    (block) => block.status === 'COMPLETED',
  ).length;

  return (
    <SafeAreaView
      edges={['left', 'right']}
      style={[styles.resultScreen, stopped && styles.stoppedScreen]}
    >
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.resultScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text
          accessibilityRole="header"
          style={[
            styles.resultTitle,
            useJua && !stopped && styles.jua,
            stopped && styles.resultTitleStopped,
          ]}
        >
          {stopped ? '중단했어요' : '오늘 운동 완료!'}
        </Text>
        <Text
          style={[
            styles.resultDescription,
            stopped && styles.resultDescriptionStopped,
          ]}
        >
          {stopped
            ? '여기까지의 기록은 저장돼요. 회복이 우선입니다.'
            : '완료한 블록이 이번 주 루틴에 반영됐어요.'}
        </Text>
        <View style={styles.resultCard}>
          <View style={styles.resultStats}>
            {[
              ['운동 시간', formatWorkoutTime(elapsedSeconds)],
              ['완료 블록', `${completedCount}/${blocks.length}`],
              ['상태', stopped ? '중단' : '완료'],
            ].map(([label, value]) => (
              <View key={label} style={styles.resultStat}>
                <Text style={styles.resultStatLabel}>{label}</Text>
                <Text style={[styles.resultStatValue, useJua && styles.jua]}>
                  {value}
                </Text>
              </View>
            ))}
          </View>
          <View style={styles.resultItems}>
            {blocks.map((block) => {
              const done = block.status === 'COMPLETED';
              return (
                <View key={block.id} style={styles.resultItem}>
                  <View style={styles.resultItemNameWrap}>
                    <View
                      style={[
                        styles.resultItemDot,
                        done && styles.resultItemDotDone,
                      ]}
                    />
                    <Text style={styles.resultItemName}>{block.name}</Text>
                  </View>
                  <Text
                    style={[
                      styles.resultItemValue,
                      done && styles.resultItemValueDone,
                    ]}
                  >
                    {done ? '완료' : '미완료'}
                  </Text>
                </View>
              );
            })}
          </View>
          {reportNote ? (
            <View style={styles.reportNote}>
              <Text style={styles.reportNoteText}>{reportNote}</Text>
            </View>
          ) : null}
        </View>
      </ScrollView>
      <View style={styles.resultFooter}>
        <Pressable
          accessibilityRole="button"
          onPress={onBackHome}
          style={styles.resultButton}
        >
          <Text style={[styles.resultButtonText, useJua && styles.jua]}>
            기록 저장하고 홈으로
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function getWorkoutFixture(state: WorkoutPreviewState): WorkoutFixture {
  const first = WORKOUT_BLOCKS[0]!.id;
  const firstTwo = WORKOUT_BLOCKS.slice(0, 2).map((block) => block.id);
  const all = WORKOUT_BLOCKS.map((block) => block.id);
  const base = { offline: false } as const;

  switch (state) {
    case 'offline':
      return {
        ...base,
        completedBlockIds: [],
        elapsedSeconds: 11,
        offline: true,
        overlay: 'none',
        result: 'none',
      };
    case 'partial':
      return {
        ...base,
        completedBlockIds: firstTwo,
        elapsedSeconds: 742,
        overlay: 'none',
        result: 'none',
      };
    case 'all-blocks':
      return {
        ...base,
        completedBlockIds: all,
        elapsedSeconds: 2160,
        overlay: 'none',
        result: 'none',
      };
    case 'rest':
      return {
        ...base,
        completedBlockIds: [first],
        elapsedSeconds: 356,
        overlay: 'rest',
        result: 'none',
      };
    case 'not-completed':
      return {
        ...base,
        completedBlockIds: [],
        elapsedSeconds: 802,
        overlay: 'not-completed',
        result: 'none',
      };
    case 'safety':
      return {
        ...base,
        completedBlockIds: [first],
        elapsedSeconds: 418,
        overlay: 'safety',
        result: 'none',
      };
    case 'symptom-mild':
      return {
        ...base,
        completedBlockIds: [first],
        elapsedSeconds: 418,
        instruction: 'SHOW_CAUTION',
        overlay: 'symptom',
        result: 'none',
        safetyReport: { symptomCode: 'PAIN', severityCode: 'MILD' },
      };
    case 'symptom-severe':
      return {
        ...base,
        completedBlockIds: [first],
        elapsedSeconds: 418,
        instruction: 'STOP_AND_SEEK_HELP',
        overlay: 'symptom',
        result: 'none',
        safetyReport: {
          symptomCode: 'BREATHING_DIFFICULTY',
          severityCode: 'SEVERE',
        },
      };
    case 'completed':
      return {
        ...base,
        completedBlockIds: all,
        elapsedSeconds: 2160,
        overlay: 'none',
        result: 'completed',
      };
    case 'stopped':
      return {
        ...base,
        completedBlockIds: firstTwo,
        elapsedSeconds: 802,
        overlay: 'none',
        reportNote: '보고된 이상 반응 — 호흡 곤란 · 심함',
        result: 'stopped',
      };
    default:
      return {
        ...base,
        completedBlockIds: [],
        elapsedSeconds: 0,
        overlay: 'none',
        result: 'none',
      };
  }
}

const styles = StyleSheet.create({
  screen: { flex: 1, overflow: 'hidden', backgroundColor: colors.canvas },
  timerHeader: {
    flexShrink: 0,
    backgroundColor: colors.green,
    paddingTop: WORKOUT_LAYOUT.headerTopPadding,
  },
  timerHeaderContent: {
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: WORKOUT_LAYOUT.headerHorizontalPadding,
    paddingBottom: 14,
  },
  headerTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  timerCopy: { minWidth: 0 },
  timerCaption: {
    color: colors.text,
    fontSize: 11.5,
    fontWeight: '700',
    letterSpacing: 0.6,
    opacity: 0.85,
  },
  timer: {
    marginTop: 2,
    color: colors.text,
    fontSize: 38,
    fontWeight: '900',
    letterSpacing: 1,
    lineHeight: 40,
  },
  timerPaused: { opacity: 0.55 },
  jua: { fontFamily: fontFamilies.slogan, fontWeight: '400' },
  timerActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  roundAction: {
    width: 52,
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,.18)',
  },
  pauseMark: { flexDirection: 'row', gap: 3.8 },
  pauseBar: {
    width: 3.6,
    height: 14,
    borderRadius: 1.4,
    backgroundColor: colors.text,
  },
  playMark: {
    width: 0,
    height: 0,
    marginLeft: 3,
    borderTopWidth: 7,
    borderBottomWidth: 7,
    borderLeftWidth: 11,
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
    borderLeftColor: colors.text,
  },
  stopAction: {
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,.55)',
    borderRadius: 18,
    backgroundColor: 'transparent',
    paddingHorizontal: 14,
  },
  stopActionLabel: { color: colors.text, fontSize: 13.5, fontWeight: '800' },
  progressRow: { flexDirection: 'row', gap: 5, marginTop: 14 },
  progressSegment: {
    height: 6,
    flex: 1,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,.28)',
  },
  progressSegmentCurrent: { backgroundColor: 'rgba(255,255,255,.75)' },
  progressSegmentDone: { backgroundColor: colors.text },
  routineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    marginTop: 8,
  },
  routineTitle: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '700',
  },
  routineStep: { color: colors.text, fontSize: 12.5, fontWeight: '700' },
  offlineBanner: {
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    borderBottomWidth: 1,
    borderBottomColor: '#F0E2B8',
    backgroundColor: '#FBF1D6',
    paddingVertical: 10,
    paddingHorizontal: 18,
  },
  offlineDot: {
    width: 8,
    height: 8,
    flexShrink: 0,
    borderRadius: 4,
    backgroundColor: '#EE875B',
  },
  offlineText: {
    flex: 1,
    color: '#6B551A',
    fontSize: 12.5,
    fontWeight: '700',
    lineHeight: 17.5,
  },
  apiBanner: {
    flexShrink: 0,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    paddingVertical: 9,
    paddingHorizontal: 18,
  },
  apiBannerError: {
    borderBottomColor: colors.dangerBorder,
    backgroundColor: colors.dangerBg,
  },
  apiBannerSuccess: {
    borderBottomColor: colors.greenBorder,
    backgroundColor: colors.greenTint,
  },
  apiBannerText: {
    color: colors.textSub,
    fontSize: 12.5,
    fontWeight: '700',
    lineHeight: 18,
  },
  apiBannerTextError: { color: colors.dangerText },
  mascotStage: {
    width: '100%',
    alignSelf: 'center',
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    position: 'relative',
    paddingTop: 8,
    paddingHorizontal: 18,
  },
  mascotStageSerious: { backgroundColor: colors.dangerBg },
  mascot: {
    width: 82,
    height: 82,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 5,
    borderColor: colors.surface,
    borderRadius: 41,
    backgroundColor: colors.yellow,
  },
  mascotSerious: {
    borderColor: colors.dangerBorder,
    backgroundColor: colors.surface,
  },
  mascotAnimation: { width: 104, height: 96 },
  mascotMark: { color: colors.primary, fontSize: 25, fontWeight: '900' },
  mascotCopy: { maxWidth: 190 },
  mascotEyebrow: { color: colors.greenText, fontSize: 11.5, fontWeight: '800' },
  mascotTitle: {
    marginTop: 4,
    color: colors.text,
    fontSize: 19,
    fontWeight: '900',
  },
  mascotCaption: {
    marginTop: 5,
    color: colors.textSub,
    fontSize: 11.5,
    lineHeight: 17,
  },
  burstText: {
    position: 'absolute',
    top: 26,
    left: 0,
    right: 0,
    color: colors.green,
    fontSize: 34,
    fontWeight: '900',
    textAlign: 'center',
  },
  carouselRegion: {
    width: '100%',
    minHeight: 0,
    flex: 1,
    alignSelf: 'center',
    overflow: 'hidden',
  },
  carouselGuide: {
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    paddingTop: 2,
    paddingRight: 20,
    paddingBottom: 8,
    paddingLeft: 20,
  },
  carouselHint: { color: colors.textMuted, fontSize: 13, fontWeight: '800' },
  carouselCount: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
  blockCarousel: {
    paddingTop: 14,
  },
  blockCard: {
    ...shadows.card,
    borderWidth: 1.5,
    borderRadius: 22,
    padding: 16,
  },
  blockCardCurrent: {
    borderColor: colors.greenBorder,
    backgroundColor: colors.surface,
  },
  blockCardDone: { borderColor: '#EAE7E0', backgroundColor: '#FFF8E5' },
  blockCardPending: { borderColor: '#EAE7E0', backgroundColor: '#F7F5F0' },
  blockCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 7,
  },
  blockBadge: {
    borderRadius: 999,
    backgroundColor: colors.border,
    paddingVertical: 4,
    paddingHorizontal: 9,
  },
  blockBadgeCurrent: { backgroundColor: colors.yellow },
  blockBadgeDone: { backgroundColor: colors.green },
  blockBadgeText: {
    color: colors.textSub,
    fontSize: 10.5,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  blockBadgeTextEmphasis: { color: colors.text },
  blockBadgeTextCurrent: { color: '#342E17' },
  blockOrder: { color: '#B0ACA4', fontSize: 11.5, fontWeight: '700' },
  blockName: {
    marginTop: 10,
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: -0.4,
  },
  blockNameDone: {
    color: colors.textMuted,
    textDecorationLine: 'line-through',
  },
  blockMeta: {
    marginTop: 6,
    color: colors.textMuted,
    fontSize: 13.5,
    fontWeight: '700',
    lineHeight: 20.25,
  },
  blockMetaCurrent: { color: colors.greenText },
  infoButton: {
    minHeight: 36,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: 10,
    paddingVertical: 8,
  },
  infoButtonText: { color: colors.green, fontSize: 12.5, fontWeight: '700' },
  undoButton: {
    minHeight: 34,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: 8,
    borderWidth: 1,
    borderColor: colors.greenBorder,
    borderRadius: 10,
    backgroundColor: colors.surface,
    paddingHorizontal: 11,
  },
  undoButtonText: {
    color: colors.greenText,
    fontSize: 11.5,
    fontWeight: '800',
  },
  tipList: {
    gap: 6,
    marginTop: 2,
    borderRadius: 12,
    backgroundColor: '#F3F1EB',
    paddingVertical: 11,
    paddingHorizontal: 12,
  },
  tipText: {
    color: '#5C5850',
    fontSize: 12.5,
    fontWeight: '600',
    lineHeight: 18.75,
  },
  dotRow: {
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingTop: 10,
    paddingBottom: 2,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: '#D8D4CB',
  },
  dotActive: { width: 22 },
  dotDone: { backgroundColor: colors.green },
  dotVisiblePending: { backgroundColor: colors.textMuted },
  bottomBar: {
    width: '100%',
    alignSelf: 'center',
    flexShrink: 0,
    flexDirection: 'row',
    gap: 8,
    paddingTop: 6,
    paddingRight: 18,
    paddingBottom: 24,
    paddingLeft: 18,
  },
  smashAction: {
    minHeight: 58,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 5,
    borderBottomColor: colors.primary,
    borderRadius: 18,
    backgroundColor: colors.green,
    padding: 17,
  },
  smashActionDisabled: {
    borderBottomColor: '#B7B3AC',
    backgroundColor: '#CFCCC5',
  },
  smashActionText: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  restAction: {
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    paddingHorizontal: 18,
  },
  additionalAction: {
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.greenBorder,
    borderRadius: 18,
    backgroundColor: colors.greenTint,
    paddingHorizontal: 12,
  },
  restActionText: { color: colors.textSub, fontSize: 13.5, fontWeight: '700' },
  pressed: { opacity: 0.82 },
  restSheet: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 30,
    borderTopLeftRadius: 26,
    borderTopRightRadius: 26,
    backgroundColor: colors.primary,
    paddingTop: 20,
    paddingRight: 18,
    paddingBottom: 28,
    paddingLeft: 18,
  },
  restSheetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  restLabel: {
    color: colors.text,
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.6,
    opacity: 0.85,
  },
  restTimer: {
    marginTop: 2,
    color: colors.text,
    fontSize: 44,
    fontWeight: '900',
    lineHeight: 44,
  },
  restActions: { flexDirection: 'row', gap: 8 },
  restAddButton: {
    minHeight: 46,
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,.5)',
    borderRadius: 16,
    backgroundColor: 'transparent',
    paddingVertical: 13,
    paddingHorizontal: 15,
  },
  restAddButtonText: {
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
  },
  restEndButton: {
    minHeight: 46,
    justifyContent: 'center',
    borderRadius: 16,
    backgroundColor: colors.yellow,
    paddingVertical: 13,
    paddingHorizontal: 17,
  },
  restEndButtonText: { color: '#342E17', fontSize: 16, fontWeight: '900' },
  restDescription: {
    marginTop: 10,
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '600',
    lineHeight: 18,
    opacity: 0.85,
  },
  sheetOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 50,
    alignItems: 'center',
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20,32,16,.62)',
  },
  sheet: {
    width: '100%',
    maxWidth: 640,
    maxHeight: '92%',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.surface,
    paddingTop: 10,
    paddingHorizontal: WORKOUT_LAYOUT.sheetHorizontalPadding,
    paddingBottom: WORKOUT_LAYOUT.sheetBottomPadding,
  },
  sheetHandle: {
    width: 42,
    height: 5,
    alignSelf: 'center',
    borderRadius: 3,
    backgroundColor: colors.borderSoft,
  },
  sheetTitle: {
    marginTop: 16,
    color: colors.text,
    fontSize: 19,
    fontWeight: '800',
  },
  detailSheet: {
    maxHeight: '82%',
  },
  detailSheetHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16,
    marginTop: 14,
  },
  detailSheetHeading: {
    minWidth: 0,
    flex: 1,
  },
  detailSheetEyebrow: {
    color: colors.greenText,
    fontSize: 11.5,
    fontWeight: '800',
  },
  detailSheetTitle: {
    marginTop: 4,
  },
  detailCloseButton: {
    minWidth: 52,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 13,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
  },
  detailCloseButtonText: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '800',
  },
  detailSheetScroll: {
    flexShrink: 1,
    marginTop: 14,
  },
  detailSheetContent: {
    paddingBottom: 8,
  },
  sheetDescription: {
    marginTop: 6,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19.5,
  },
  outlineButtonWide: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 9,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
  },
  outlineButtonText: {
    color: '#4A4740',
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  dangerButton: {
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 18,
    borderBottomWidth: 5,
    borderBottomColor: '#8E3226',
    borderRadius: 18,
    backgroundColor: '#C2503C',
    paddingHorizontal: 12,
  },
  dangerButtonText: {
    color: colors.surface,
    fontSize: 15,
    fontWeight: '900',
    textAlign: 'center',
  },
  textButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 6,
  },
  textButtonLabel: {
    color: colors.textMuted,
    fontSize: 13.5,
    fontWeight: '700',
  },
  choiceTitle: {
    marginTop: 16,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '800',
  },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 9 },
  choiceButton: {
    minHeight: 44,
    minWidth: 88,
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    paddingHorizontal: 10,
  },
  choiceButtonSelected: {
    borderColor: colors.green,
    backgroundColor: colors.green,
  },
  choiceButtonText: { color: colors.text, fontSize: 13, fontWeight: '700' },
  choiceButtonTextSelected: { color: colors.text },
  noteInput: {
    minHeight: 76,
    marginTop: 9,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    color: colors.text,
    fontSize: 13,
    lineHeight: 19,
    paddingVertical: 11,
    paddingHorizontal: 12,
    textAlignVertical: 'top',
  },
  guidance: {
    marginTop: 14,
    borderWidth: 1,
    borderColor: colors.greenBorder,
    borderRadius: 14,
    backgroundColor: colors.greenTint,
    paddingVertical: 12,
    paddingHorizontal: 13,
  },
  guidanceSevere: {
    borderColor: '#F2CFC9',
    backgroundColor: '#FBEAE7',
  },
  guidanceText: {
    color: colors.greenText,
    fontSize: 12.5,
    lineHeight: 18.75,
    fontWeight: '700',
  },
  guidanceTextSevere: { color: '#8E3226' },
  inlineError: {
    marginTop: 12,
    color: colors.dangerText,
    fontSize: 12.5,
    fontWeight: '700',
    lineHeight: 18,
  },
  actionDisabled: { opacity: 0.5 },
  reasonList: { gap: 7, marginTop: 14 },
  reasonButton: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: 13,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
  },
  reasonButtonText: { color: colors.text, fontSize: 13, fontWeight: '700' },
  resultScreen: { flex: 1, backgroundColor: colors.greenTint },
  stoppedScreen: { backgroundColor: '#F5F2EC' },
  resultScrollContent: {
    paddingTop: 64,
    paddingHorizontal: 18,
    paddingBottom: 12,
  },
  resultTitle: {
    color: colors.primary,
    fontSize: 28,
    fontWeight: '900',
    textAlign: 'center',
  },
  resultTitleStopped: { color: colors.text, fontSize: 24, fontWeight: '800' },
  resultDescription: {
    marginTop: 8,
    color: colors.greenText,
    fontSize: 13.5,
    fontWeight: '700',
    lineHeight: 20.25,
    textAlign: 'center',
  },
  resultDescriptionStopped: { color: colors.textSub },
  resultCard: {
    ...shadows.card,
    marginTop: 20,
    borderRadius: 24,
    backgroundColor: colors.surface,
    padding: 18,
  },
  resultStats: { flexDirection: 'row', gap: 10 },
  resultStat: { flex: 1, alignItems: 'center' },
  resultStatLabel: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '700',
  },
  resultStatValue: {
    marginTop: 5,
    color: colors.primary,
    fontSize: 23,
    fontWeight: '900',
  },
  resultItems: {
    gap: 9,
    marginTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
    paddingTop: 14,
  },
  resultItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  resultItemNameWrap: {
    minWidth: 0,
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  resultItemDot: {
    width: 8,
    height: 8,
    flexShrink: 0,
    borderRadius: 4,
    backgroundColor: '#D8D4CB',
  },
  resultItemDotDone: { backgroundColor: colors.green },
  resultItemName: { color: colors.text, fontSize: 13.5, fontWeight: '700' },
  resultItemValue: {
    color: '#B0ACA4',
    fontSize: 12.5,
    fontWeight: '800',
  },
  resultItemValueDone: { color: colors.greenText },
  reportNote: {
    marginTop: 14,
    borderRadius: 12,
    backgroundColor: '#FBEAE7',
    paddingVertical: 11,
    paddingHorizontal: 12,
  },
  reportNoteText: {
    color: '#8E3226',
    fontSize: 12.5,
    fontWeight: '700',
    lineHeight: 18.75,
  },
  resultFooter: {
    flexShrink: 0,
    paddingTop: 8,
    paddingRight: 18,
    paddingBottom: 26,
    paddingLeft: 18,
  },
  resultButton: {
    width: '100%',
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 5,
    borderBottomColor: colors.primary,
    borderRadius: 20,
    backgroundColor: colors.green,
    padding: 18,
  },
  resultButtonText: { color: colors.text, fontSize: 19, fontWeight: '900' },
});
