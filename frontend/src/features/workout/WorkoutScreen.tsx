import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Image,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type PanResponderGestureState,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { Api } from '../../api/endpoints';
import { ApiError, messageForError } from '../../api/errors';
import {
  formatExercisePrescription,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  ExerciseVariantsResponse,
  NotCompletedReasonCode,
  SessionItem,
  WorkoutPlan,
} from '../../api/types';
import { orderedWorkoutPlanItems } from '../../api/workoutPlan';
import { imageAssets } from '../../assets';
import { colors, shadows } from '../../components/theme';
import { useScale } from '../../components/scale';
import { ExerciseDetailSheet } from './ExerciseDetailSheet';
import {
  ExerciseVariantsAction,
  ExerciseVariantsContent,
} from './ExerciseVariants';
import type { SessionOutcome } from './SessionScreen';
import {
  NOT_COMPLETED_REASONS,
  SAFETY_GUIDANCE,
  getWorkoutResponsiveLayout,
  WORKOUT_SAFETY_HELP,
  WORKOUT_STOP_REASONS,
  WORKOUT_ARC,
  WORKOUT_BLOCKS,
  WORKOUT_CAROUSEL,
  WORKOUT_SEVERITIES,
  WORKOUT_SYMPTOMS,
  type WorkoutBlock,
  type WorkoutBlockStatus,
  type WorkoutPreviewState,
  type WorkoutResponsiveLayout,
  type WorkoutExecutionState,
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
  'none' | 'rest' | 'not-completed' | 'stop-reasons' | 'symptom' | 'additional';
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

const PAIN_REPORT_INTRO =
  '어떤 통증이 있는지 알려주면, 운동을 계속할지 중단할지 결정할게요.';

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
  initialEquipmentGuideExerciseId?: string;
  sessionId: string;
  plan: WorkoutPlan;
  onOutcome: (outcome: SessionOutcome) => void;
  /** Keeps an IN_PROGRESS session resumable while the backend stop state evolves. */
  onReturnHomeResumable?: () => void;
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

export function workoutPageAfterHorizontalDrag(
  currentIndex: number,
  blockCount: number,
  dragX: number,
  velocityX: number,
) {
  if (blockCount <= 0) {
    return 0;
  }
  const swipeX =
    Math.abs(dragX) >= 36 ? dragX : Math.abs(velocityX) >= 0.25 ? velocityX : 0;
  const nextIndex =
    swipeX === 0 ? currentIndex : currentIndex + (swipeX < 0 ? 1 : -1);
  return Math.max(0, Math.min(blockCount - 1, nextIndex));
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
  const layoutScale = responsiveLayout.scale;
  const carouselRef = useRef<ScrollView | null>(null);
  const carouselDragStartOffset = useRef(0);
  const [scrollX] = useState(() => new Animated.Value(0));
  const [burstOpacity] = useState(() => new Animated.Value(0));
  const [burstScale] = useState(() => new Animated.Value(0.7));
  const [elapsedSeconds, setElapsedSeconds] = useState(fixture.elapsedSeconds);
  const [previewResult, setPreviewResult] = useState<WorkoutResult>(
    fixture.result,
  );
  const [executionState, setExecutionState] = useState<WorkoutExecutionState>(
    fixture.overlay === 'rest' ? 'RESTING' : 'RUNNING',
  );
  const stateBeforePause = useRef<Exclude<WorkoutExecutionState, 'PAUSED'>>(
    fixture.overlay === 'rest' ? 'RESTING' : 'RUNNING',
  );
  const [overlay, setOverlay] = useState<WorkoutOverlay>(fixture.overlay);
  const [completedBlockIds, setCompletedBlockIds] = useState<readonly string[]>(
    fixture.completedBlockIds,
  );
  const [detailBlockId, setDetailBlockId] = useState<string | null>(null);
  const [variantGuide, setVariantGuide] = useState<{
    block: WorkoutViewBlock;
    response: ExerciseVariantsResponse;
  } | null>(null);
  const [restSeconds, setRestSeconds] = useState(0);
  const [selectedStopReason, setSelectedStopReason] = useState<
    NotCompletedReasonCode | 'SAFETY' | null
  >(null);
  const [safetyStopAcknowledged, setSafetyStopAcknowledged] = useState(false);
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
  const [sessionReady, setSessionReady] = useState(apiConfig === undefined);
  const [actionPending, setActionPending] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [additionalDurationMinutes, setAdditionalDurationMinutes] =
    useState(10);
  const [additionalActivityType, setAdditionalActivityType] =
    useState<string>('WALKING');
  const [additionalIntensity, setAdditionalIntensity] =
    useState<string>('MODERATE');
  const [additionalNote, setAdditionalNote] = useState('');
  const [additionalSaved, setAdditionalSaved] = useState(false);
  const useJua = brandFonts.loaded && !brandFonts.failed;
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
  const paused = executionState === 'PAUSED';
  const targetDurationMinutes =
    apiConfig?.plan.requested_duration_minutes ?? 30;
  const isSafetyState = overlay === 'stop-reasons' || overlay === 'symptom';
  const carouselPadding = Math.max(
    0,
    (carouselWidth - responsiveLayout.cardWidth) / 2,
  );
  const timerCaption =
    executionState === 'RESTING'
      ? '휴식 중'
      : executionState === 'PAUSED'
        ? '일시 정지'
        : '운동 진행 중';
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
      executionState === 'PAUSED' ||
      previewResult !== 'none' ||
      !sessionReady
    ) {
      return undefined;
    }
    const timer = setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [executionState, previewResult, sessionReady]);

  useEffect(() => {
    if (executionState !== 'RESTING') {
      return undefined;
    }
    const timer = setInterval(() => {
      setRestSeconds((current) => current + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [executionState]);

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
    if (executionState === 'PAUSED') {
      setExecutionState(stateBeforePause.current);
      recordTimerChange('RESUME');
      onPauseChange?.(false);
      return;
    }
    stateBeforePause.current = executionState;
    setExecutionState('PAUSED');
    recordTimerChange('PAUSE');
    onPauseChange?.(true);
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
    setExecutionState('PAUSED');
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
    }
    onBlockStatusChange?.(block.id, 'PENDING');
  };

  const applyServerBlockProgress = (items: readonly SessionItem[]) => {
    const serverCompletedBlockIds = items
      .filter((item) => item.status_code === 'COMPLETED')
      .map((item) => item.plan_item_id);
    setCompletedBlockIds(serverCompletedBlockIds);
    setVisiblePageIndex(
      firstPendingIndex(sourceBlocks, serverCompletedBlockIds),
    );
    return serverCompletedBlockIds;
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
        setExecutionState('PAUSED');
        setPreviewResult('completed');
      }
      return;
    }

    const previousCompletedBlockIds = completedBlockIds;
    const previousVisiblePageIndex = visiblePageIndex;

    // The server remains the official source of completion, but the visual
    // response does not need to wait for a network round trip. The next block
    // stays disabled through actionPending until this mutation is confirmed.
    applyCompletedBlock(block);
    setActionPending(true);
    setApiError(null);
    try {
      let shouldFinalize = false;
      try {
        const response = await apiConfig.api.updateSessionItem(
          apiConfig.sessionId,
          block.id,
          'COMPLETED',
          new Date().toISOString(),
        );
        if (response.item.status_code !== 'COMPLETED') {
          throw new Error('server did not confirm block completion');
        }
        const serverNextIndex =
          response.next_pending_plan_item_id === null
            ? -1
            : blocks.findIndex(
                (item) => item.id === response.next_pending_plan_item_id,
              );
        if (serverNextIndex >= 0) {
          setVisiblePageIndex(serverNextIndex);
        }
        shouldFinalize =
          response.completed_item_count === response.total_item_count;
      } catch (error) {
        // A failed fetch is ambiguous: the server may have committed the block
        // and only lost the response. Re-read before rolling the optimistic UI
        // back so a completed block does not appear to come back unexpectedly.
        try {
          const detail = await apiConfig.api.getWorkoutSession(
            apiConfig.sessionId,
          );
          const serverCompletedBlockIds = applyServerBlockProgress(
            detail.items,
          );
          const serverConfirmedCompletion = serverCompletedBlockIds.includes(
            block.id,
          );

          if (!serverConfirmedCompletion) {
            setApiError(messageForError(error));
          } else if (detail.status_code === 'IN_PROGRESS') {
            shouldFinalize =
              detail.completed_item_count === detail.total_item_count;
          } else {
            setApiError(messageForError(error));
          }
        } catch {
          setCompletedBlockIds(previousCompletedBlockIds);
          setVisiblePageIndex(previousVisiblePageIndex);
          setApiError(messageForError(error));
        }
      }

      if (shouldFinalize) {
        try {
          await finalizeServerSession();
        } catch (finishError) {
          setApiError(messageForError(finishError));
        }
      }
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
    if (executionState === 'PAUSED') {
      return;
    }
    setRestSeconds(0);
    setExecutionState('RESTING');
    setOverlay('rest');
    onRestChange?.(true);
  };

  const closeRest = () => {
    setOverlay('none');
    if (executionState === 'PAUSED') {
      stateBeforePause.current = 'RUNNING';
    } else {
      setExecutionState('RUNNING');
    }
    onRestChange?.(false);
  };

  const pauseForOverlay = () => {
    if (executionState === 'PAUSED') {
      return;
    }
    const leavingRest = executionState === 'RESTING';
    stateBeforePause.current = leavingRest ? 'RUNNING' : executionState;
    setExecutionState('PAUSED');
    recordTimerChange('PAUSE');
    onPauseChange?.(true);
    if (leavingRest) {
      onRestChange?.(false);
    }
  };

  const openStopReasons = () => {
    setApiError(null);
    setSelectedStopReason(null);
    setSafetyStopAcknowledged(false);
    pauseForOverlay();
    setOverlay('stop-reasons');
  };

  const openPainReport = () => {
    setApiError(null);
    pauseForOverlay();
    setOverlay('symptom');
  };

  const closeSheets = () => {
    setOverlay('none');
    if (executionState === 'PAUSED') {
      setExecutionState(stateBeforePause.current);
      recordTimerChange('RESUME');
      onPauseChange?.(false);
    }
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
      setExecutionState('PAUSED');
      apiConfig.onOutcome({ kind: 'notCompleted', result });
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
  };

  const submitApiSafetyEvent = async () => {
    if (apiConfig === undefined || actionPending || !sessionReady) {
      return;
    }
    setActionPending(true);
    setApiError(null);
    try {
      const event = await apiConfig.api.reportSafetyEvent(apiConfig.sessionId, {
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
          message:
            '안전 중단 응답을 확인할 수 없습니다. 운동을 계속하지 마세요.',
        });
      }
      setExecutionState('PAUSED');
      apiConfig.onOutcome({ kind: 'safetyStop', event });
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
      setExecutionState('RUNNING');
      recordTimerChange('RESUME');
    } catch (error) {
      setApiError(messageForError(error));
    } finally {
      setActionPending(false);
    }
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

  const selectVisiblePage = useCallback(
    (index: number) => {
      setVisiblePageIndex(index);
      carouselRef.current?.scrollTo({
        x: index * responsiveLayout.stride,
        animated: true,
      });
    },
    [responsiveLayout.stride],
  );

  const beginCarouselDrag = useCallback(() => {
    carouselDragStartOffset.current =
      visiblePageIndex * responsiveLayout.stride;
  }, [responsiveLayout.stride, visiblePageIndex]);

  const moveCarouselDrag = useCallback(
    (gesture: PanResponderGestureState) => {
      const maxOffset = Math.max(
        0,
        (blocks.length - 1) * responsiveLayout.stride,
      );
      const nextOffset = Math.max(
        0,
        Math.min(maxOffset, carouselDragStartOffset.current - gesture.dx),
      );
      scrollX.setValue(nextOffset);
      carouselRef.current?.scrollTo({ x: nextOffset, animated: false });
    },
    [blocks.length, responsiveLayout.stride, scrollX],
  );

  const finishCarouselDrag = useCallback(
    (gesture: PanResponderGestureState) => {
      selectVisiblePage(
        workoutPageAfterHorizontalDrag(
          visiblePageIndex,
          blocks.length,
          gesture.dx,
          gesture.vx,
        ),
      );
    },
    [blocks.length, selectVisiblePage, visiblePageIndex],
  );

  const cancelCarouselDrag = useCallback(
    () => selectVisiblePage(visiblePageIndex),
    [selectVisiblePage, visiblePageIndex],
  );

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
            {
              maxWidth: responsiveLayout.contentMaxWidth,
              paddingHorizontal:
                WORKOUT_LAYOUT.headerHorizontalPadding * layoutScale,
              paddingBottom: 14 * layoutScale,
            },
          ]}
        >
          <View testID="workout-header-top-row" style={styles.headerTopRow}>
            <View testID="workout-timer-card" style={styles.timerCopy}>
              <View style={styles.timerMetaRow}>
                <View style={styles.timerStatusBadge}>
                  <View
                    style={[
                      styles.timerStatusDot,
                      paused && styles.timerStatusDotPaused,
                    ]}
                  />
                  <Text
                    style={[
                      styles.timerCaption,
                      {
                        fontSize: 11.5 * layoutScale,
                        letterSpacing: 0.45 * layoutScale,
                      },
                    ]}
                  >
                    {timerCaption}
                  </Text>
                </View>
                <Text style={styles.targetTime}>
                  목표 {targetDurationMinutes}분
                </Text>
              </View>
              <Text
                accessibilityLabel={`진행 시간 ${formatWorkoutTime(elapsedSeconds)} / 목표 시간 ${targetDurationMinutes}분`}
                style={[
                  styles.timer,
                  {
                    fontSize: 46 * layoutScale,
                    letterSpacing: 1.6 * layoutScale,
                    lineHeight: 48 * layoutScale,
                  },
                  useJua && styles.timerBrand,
                  paused && styles.timerPaused,
                ]}
              >
                {formatWorkoutTime(elapsedSeconds)}
              </Text>
              <Text style={styles.elapsedLabel}>ELAPSED TIME</Text>
            </View>
            <View style={styles.timerActions}>
              <Pressable
                accessibilityLabel={paused ? '재개' : '일시정지'}
                accessibilityRole="button"
                onPress={togglePaused}
                style={({ pressed }) => [
                  styles.roundAction,
                  {
                    width: 52 * layoutScale,
                    height: 52 * layoutScale,
                    borderRadius: 18 * layoutScale,
                  },
                  pressed && styles.pressed,
                ]}
                testID="workout-pause-action"
              >
                <PlaybackMark paused={paused} />
              </Pressable>
              <Pressable
                accessibilityLabel="운동 중단"
                accessibilityRole="button"
                onPress={openStopReasons}
                style={({ pressed }) => [
                  styles.stopAction,
                  {
                    height: 52 * layoutScale,
                    borderRadius: 18 * layoutScale,
                    paddingHorizontal: 14 * layoutScale,
                  },
                  pressed && styles.pressed,
                ]}
                testID="workout-stop-action"
              >
                <Text
                  style={[
                    styles.stopActionLabel,
                    { fontSize: 13.5 * layoutScale },
                  ]}
                >
                  중단
                </Text>
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
        scale={layoutScale}
        serious={isSafetyState}
        useJua={useJua}
      />

      <View
        style={[
          styles.carouselRegion,
          { maxWidth: responsiveLayout.contentMaxWidth },
        ]}
      >
        <WorkoutCarouselDragSurface
          onCancel={cancelCarouselDrag}
          onEnd={finishCarouselDrag}
          onMove={moveCarouselDrag}
          onStart={beginCarouselDrag}
        >
          <View
            style={[
              styles.carouselGuide,
              {
                gap: 10 * layoutScale,
                paddingTop: 2 * layoutScale,
                paddingRight: 20 * layoutScale,
                paddingBottom: 8 * layoutScale,
                paddingLeft: 20 * layoutScale,
              },
            ]}
          >
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
              {
                gap: responsiveLayout.gap,
                paddingHorizontal: carouselPadding,
                paddingTop: 14 * layoutScale,
              },
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
            style={[
              styles.carouselViewport,
              {
                height: responsiveLayout.cardHeight + 14 * layoutScale,
              },
            ]}
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
                onToggleExpanded={() => {
                  setVariantGuide(null);
                  setDetailBlockId((current) =>
                    current === block.id ? null : block.id,
                  );
                }}
                onUndo={
                  block.status === 'COMPLETED'
                    ? () => void reopenBlock(block)
                    : undefined
                }
                scrollX={scrollX}
                variantAction={
                  apiConfig !== undefined && block.exerciseId !== undefined ? (
                    <ExerciseVariantsAction
                      actionStyle={styles.cardVariantAction}
                      actionTextStyle={styles.cardVariantActionText}
                      api={apiConfig.api}
                      autoOpen={
                        apiConfig.initialEquipmentGuideExerciseId ===
                        block.exerciseId
                      }
                      exerciseId={block.exerciseId}
                      exerciseName={block.name}
                      label="장비가 없을 때"
                      onOpen={(response) => {
                        setDetailBlockId(null);
                        setVariantGuide({ block, response });
                      }}
                      presentation="text"
                    />
                  ) : null
                }
              />
            ))}
          </Animated.ScrollView>
        </WorkoutCarouselDragSurface>
      </View>

      <View
        style={[
          styles.bottomBar,
          {
            maxWidth: responsiveLayout.contentMaxWidth,
            gap: 8 * layoutScale,
            paddingTop: 6 * layoutScale,
            paddingRight: 18 * layoutScale,
            paddingBottom: 4 * layoutScale,
            paddingLeft: 18 * layoutScale,
          },
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
            {
              width: 154 * layoutScale,
              height: 58 * layoutScale,
              borderRadius: 18 * layoutScale,
              paddingHorizontal: 8 * layoutScale,
            },
            !(canSmash || canFinish) && styles.smashActionDisabled,
            pressed && styles.pressed,
          ]}
          testID="workout-smash-action"
        >
          <LinearGradient
            colors={
              canSmash || canFinish
                ? ['#FFFDF8', '#FFF2D1', '#FFE2A3']
                : ['#F3ECE4', '#F3ECE4']
            }
            end={{ x: 0.5, y: 1 }}
            locations={canSmash || canFinish ? [0, 0.55, 1] : [0, 1]}
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.smashActionGradient}
            testID="workout-smash-gradient"
          />
          <Text style={styles.smashActionText}>
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
          accessibilityState={{ disabled: paused }}
          disabled={paused}
          onPress={openRest}
          style={({ pressed }) => [
            styles.smashAction,
            styles.restAction,
            {
              width: 154 * layoutScale,
              height: 58 * layoutScale,
              borderRadius: 18 * layoutScale,
              paddingHorizontal: 8 * layoutScale,
            },
            paused && styles.actionDisabled,
            pressed && styles.pressed,
          ]}
          testID="workout-rest-action"
        >
          <LinearGradient
            colors={['#FAFAF8', '#EEEDE9', '#DDDCD7']}
            end={{ x: 0.5, y: 1 }}
            locations={[0, 0.55, 1]}
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.smashActionGradient}
            testID="workout-rest-gradient"
          />
          <View style={styles.restActionContent}>
            <TimerMark />
            <Text style={styles.restActionText}>휴식</Text>
          </View>
        </Pressable>
      </View>

      <View
        style={[
          styles.dotRow,
          {
            gap: 6 * layoutScale,
            paddingTop: 6 * layoutScale,
            paddingBottom: 18 * layoutScale,
          },
        ]}
        testID="workout-bottom-pagination"
      >
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

      {detailBlock && variantGuide === null && overlay === 'none' ? (
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

      {variantGuide && overlay === 'none' ? (
        <ExerciseDetailOverlay
          accessibilityLabel={`${variantGuide.block.name} 장비 안내`}
          block={variantGuide.block}
          detail={<ExerciseVariantsContent response={variantGuide.response} />}
          eyebrow="필요 장비와 변형 방법"
          onClose={() => setVariantGuide(null)}
          title={`${variantGuide.block.name} 장비 안내`}
        />
      ) : null}

      {overlay === 'rest' ? (
        <RestSheet
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
      {overlay === 'stop-reasons' ? (
        <StopReasonSheet
          acknowledged={safetyStopAcknowledged}
          error={apiConfig === undefined ? null : apiError}
          onClose={closeSheets}
          onConfirm={() => {
            if (selectedStopReason === 'SAFETY') {
              if (apiConfig === undefined) {
                openPainReport();
              } else {
                void submitApiSafetyEvent();
              }
              return;
            }
            if (selectedStopReason === null) {
              return;
            }
            if (apiConfig === undefined) {
              onNotCompleted?.(selectedStopReason);
              setPreviewResult('stopped');
              return;
            }
            if (apiConfig.onReturnHomeResumable) {
              apiConfig.onReturnHomeResumable();
              return;
            }
            if (completedCount === 0) {
              void submitNotCompleted(selectedStopReason);
            } else {
              void finishWorkout();
            }
          }}
          onSelect={setSelectedStopReason}
          onToggleAcknowledgement={() =>
            setSafetyStopAcknowledged((current) => !current)
          }
          pending={apiConfig !== undefined && actionPending}
          selectedReason={selectedStopReason}
          submitsSafetyStop={apiConfig !== undefined}
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

function TimerMark() {
  return (
    <View accessibilityElementsHidden style={styles.timerMark}>
      <View style={styles.timerMarkHand} />
      <View style={styles.timerMarkDot} />
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
  scale,
  serious,
  useJua,
}: {
  blockName: string;
  burstKey: number;
  burstOpacity: Animated.Value;
  burstScale: Animated.Value;
  height: number;
  maxWidth: number;
  scale: number;
  serious: boolean;
  useJua: boolean;
}) {
  return (
    <View
      accessibilityLabel={serious ? '안전 안내 화면' : `${blockName} 운동 안내`}
      style={[
        styles.mascotStage,
        {
          height,
          maxWidth,
          gap: 16 * scale,
          paddingTop: 8 * scale,
          paddingHorizontal: 18 * scale,
        },
        serious && styles.mascotStageSerious,
      ]}
    >
      {serious ? (
        <View
          style={[
            styles.mascot,
            {
              width: 82 * scale,
              height: 82 * scale,
              borderRadius: 41 * scale,
            },
            styles.mascotSerious,
          ]}
        >
          <Text style={styles.mascotMark}>!</Text>
        </View>
      ) : (
        <View
          style={[
            styles.mascotFrame,
            {
              width: 104 * scale,
              height: 104 * scale,
              borderRadius: 52 * scale,
            },
          ]}
          testID="workout-mascot-frame"
        >
          <Image
            accessible={false}
            resizeMode="contain"
            source={imageAssets.mascotWarmupWalk}
            style={[
              styles.mascotAnimation,
              { width: 94 * scale, height: 94 * scale },
            ]}
            testID="workout-warmup-mascot"
          />
        </View>
      )}
      <View style={[styles.mascotCopy, { maxWidth: 190 * scale }]}>
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
            {
              top: height * 0.99,
              opacity: burstOpacity,
              transform: [{ scale: burstScale }],
            },
          ]}
          testID="workout-smash-burst"
        >
          격파!
        </Animated.Text>
      ) : null}
    </View>
  );
}

function WorkoutCarouselDragSurface({
  children,
  onCancel,
  onEnd,
  onMove,
  onStart,
}: {
  children: React.ReactNode;
  onCancel: () => void;
  onEnd: (gesture: PanResponderGestureState) => void;
  onMove: (gesture: PanResponderGestureState) => void;
  onStart: () => void;
}) {
  const responder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (
          _event,
          gesture: PanResponderGestureState,
        ) =>
          Math.abs(gesture.dx) > 6 &&
          Math.abs(gesture.dx) > Math.abs(gesture.dy),
        onMoveShouldSetPanResponderCapture: (
          _event,
          gesture: PanResponderGestureState,
        ) =>
          Math.abs(gesture.dx) > 6 &&
          Math.abs(gesture.dx) > Math.abs(gesture.dy),
        onPanResponderGrant: onStart,
        onPanResponderMove: (_event, gesture: PanResponderGestureState) =>
          onMove(gesture),
        onPanResponderRelease: (_event, gesture: PanResponderGestureState) =>
          onEnd(gesture),
        onPanResponderTerminate: onCancel,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [onCancel, onEnd, onMove, onStart],
  );

  return (
    <View
      {...(Platform.OS === 'web' ? responder.panHandlers : undefined)}
      style={[
        styles.carouselDragSurface,
        Platform.OS === 'web'
          ? ({ cursor: 'grab', touchAction: 'pan-y' } as unknown as ViewStyle)
          : undefined,
      ]}
      testID="workout-carousel-drag-surface"
    >
      {children}
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
  variantAction,
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
  variantAction?: React.ReactNode;
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
      {hasDetails || variantAction ? (
        <View style={styles.cardActionRow} testID={`workout-actions-${index}`}>
          {hasDetails ? (
            <Pressable
              accessibilityLabel={expanded ? '설명 접기' : '자세 설명 보기'}
              accessibilityRole="button"
              accessibilityState={{ expanded }}
              onPress={onToggleExpanded}
              style={({ pressed }) => [
                styles.infoButton,
                pressed && styles.cardActionPressed,
              ]}
              testID={`workout-info-action-${index}`}
            >
              <Text style={styles.infoButtonText}>
                {expanded ? '설명 보는 중' : '자세 설명 보기'}
              </Text>
            </Pressable>
          ) : null}
          {variantAction}
        </View>
      ) : null}
    </Animated.View>
  );
}

function ExerciseDetailOverlay({
  accessibilityLabel,
  block,
  detail,
  eyebrow = '운동 자세와 설명',
  onClose,
  title,
}: {
  accessibilityLabel?: string;
  block: WorkoutViewBlock;
  detail: React.ReactNode;
  eyebrow?: string;
  onClose: () => void;
  title?: string;
}) {
  return (
    <View
      accessibilityLabel={accessibilityLabel ?? `${block.name} 자세와 설명`}
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
            <Text style={styles.detailSheetEyebrow}>{eyebrow}</Text>
            <Text
              accessibilityRole="header"
              style={[styles.sheetTitle, styles.detailSheetTitle]}
            >
              {title ?? block.name}
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
  onClose,
  restSeconds,
  useJua,
}: {
  onClose: () => void;
  restSeconds: number;
  useJua: boolean;
}) {
  return (
    <View
      pointerEvents="box-none"
      style={styles.restOverlay}
      testID="workout-rest-overlay"
    >
      <View style={styles.restTimerCard} testID="workout-rest-timer-card">
        <Text style={styles.restMessage}>휴식도 운동의 일부에요</Text>
        <Text
          accessibilityLabel={`현재 휴식 시간 ${formatWorkoutTime(restSeconds)}`}
          style={[styles.restTimer, useJua && styles.jua]}
        >
          {formatWorkoutTime(restSeconds)}
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={onClose}
          style={styles.restEndButton}
        >
          <Text style={[styles.restEndButtonText, useJua && styles.jua]}>
            돌아가기
          </Text>
        </Pressable>
      </View>
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

function StopReasonSheet({
  acknowledged,
  error,
  onClose,
  onConfirm,
  onSelect,
  onToggleAcknowledgement,
  pending,
  selectedReason,
  submitsSafetyStop,
}: {
  acknowledged: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
  onSelect: (reason: NotCompletedReasonCode | 'SAFETY') => void;
  onToggleAcknowledgement: () => void;
  pending: boolean;
  selectedReason: NotCompletedReasonCode | 'SAFETY' | null;
  submitsSafetyStop: boolean;
}) {
  const [helpOpen, setHelpOpen] = useState(false);
  const safetySelected = selectedReason === 'SAFETY';
  const canContinue =
    selectedReason !== null && (!safetySelected || acknowledged);
  return (
    <SheetFrame title="운동을 중단하는 이유를 알려주세요">
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.stopReasonList}>
          {WORKOUT_STOP_REASONS.map((reason) => (
            <ChoiceButton
              key={reason.code}
              label={reason.label}
              listStyle
              onPress={() => onSelect(reason.code)}
              selected={selectedReason === reason.code}
            />
          ))}
        </View>
        <View style={styles.safetyReasonSection}>
          <Text style={styles.safetyReasonEyebrow}>
            해당 이유로 운동을 중단하면, 오늘은 더 이상 운동을 진행할 수 없어요
          </Text>
          <View style={styles.safetyReasonChoiceRow}>
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ checked: safetySelected }}
              onPress={() => onSelect('SAFETY')}
              style={[
                styles.choiceButton,
                styles.stopReasonChoiceButton,
                styles.safetyReasonChoice,
                safetySelected && styles.choiceButtonSelected,
                safetySelected && styles.stopReasonChoiceSelected,
              ]}
            >
              <Text
                style={[
                  styles.choiceButtonText,
                  styles.stopReasonChoiceText,
                  safetySelected && styles.choiceButtonTextSelected,
                ]}
              >
                통증 또는 이상 반응이 있어요.
              </Text>
            </Pressable>
            <Pressable
              accessibilityLabel="통증 또는 이상 반응 도움말"
              accessibilityRole="button"
              accessibilityState={{ expanded: helpOpen }}
              onPress={() => setHelpOpen((current) => !current)}
              style={({ pressed }) => [
                styles.inlineHelpAction,
                pressed && styles.pressed,
              ]}
              testID="workout-stop-safety-help"
            >
              <Text style={styles.inlineHelpActionText}>?</Text>
            </Pressable>
          </View>
          {helpOpen ? (
            <View style={styles.inlineHelpPopup}>
              <Text style={styles.helpSectionTitle}>통증</Text>
              <Text style={styles.helpSectionBody}>
                {WORKOUT_SAFETY_HELP.pain}
              </Text>
              <Text style={styles.helpSectionTitle}>이상 반응</Text>
              <Text style={styles.helpSectionBody}>
                {WORKOUT_SAFETY_HELP.reaction}
              </Text>
              <Text style={styles.helpNote}>{WORKOUT_SAFETY_HELP.note}</Text>
            </View>
          ) : null}
          {safetySelected ? (
            <>
              <Text style={styles.safetyReasonWarning}>
                안전 관련 입력으로 운동 중단이 확정되면 현재 운동을 다시 이어 할
                수 없습니다.
              </Text>
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: acknowledged }}
                onPress={onToggleAcknowledgement}
                style={styles.acknowledgementRow}
              >
                <View
                  style={[
                    styles.acknowledgementBox,
                    acknowledged && styles.acknowledgementBoxChecked,
                  ]}
                >
                  <Text style={styles.acknowledgementMark}>
                    {acknowledged ? '✓' : ''}
                  </Text>
                </View>
                <Text style={styles.acknowledgementText}>
                  이어하기 제한 안내를 확인했어요.
                </Text>
              </Pressable>
            </>
          ) : null}
        </View>
      </ScrollView>
      {error ? <Text style={styles.inlineError}>{error}</Text> : null}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: !canContinue || pending }}
        disabled={!canContinue || pending}
        onPress={onConfirm}
        style={[
          styles.stopConfirmButton,
          (!canContinue || pending) && styles.actionDisabled,
        ]}
        testID="workout-stop-confirm"
      >
        <LinearGradient
          colors={['#D97260', '#CC5A47', '#C2503C']}
          end={{ x: 0.5, y: 1 }}
          locations={[0, 0.55, 1]}
          pointerEvents="none"
          start={{ x: 0.5, y: 0 }}
          style={styles.stopConfirmGradient}
          testID="workout-stop-confirm-gradient"
        />
        <Text style={styles.stopConfirmButtonText}>
          {pending
            ? '중단 처리 중…'
            : safetySelected && submitsSafetyStop
              ? '안전하게 운동 중단하기'
              : safetySelected
                ? '안전 관련 내용 입력하기'
                : '이 사유로 중단하기'}
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
        <Text style={styles.sheetDescription}>{PAIN_REPORT_INTRO}</Text>
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
          style={severe ? styles.dangerButton : styles.stopConfirmButton}
          testID={!severe ? 'workout-report-continue' : undefined}
        >
          {!severe ? (
            <LinearGradient
              colors={['#D97260', '#CC5A47', '#C2503C']}
              end={{ x: 0.5, y: 1 }}
              locations={[0, 0.55, 1]}
              pointerEvents="none"
              start={{ x: 0.5, y: 0 }}
              style={styles.stopConfirmGradient}
              testID="workout-report-continue-gradient"
            />
          ) : null}
          <Text
            style={
              severe ? styles.dangerButtonText : styles.stopConfirmButtonText
            }
          >
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
  listStyle = false,
  multiple = false,
  onPress,
  selected,
}: {
  accessibilityLabel?: string;
  label: string;
  listStyle?: boolean;
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
      style={[
        styles.choiceButton,
        listStyle && styles.stopReasonChoiceButton,
        selected && styles.choiceButtonSelected,
        listStyle && selected && styles.stopReasonChoiceSelected,
      ]}
    >
      <Text
        style={[
          styles.choiceButtonText,
          listStyle && styles.stopReasonChoiceText,
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
        overlay: 'stop-reasons',
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
  timerCopy: {
    minWidth: 0,
    flex: 1,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,.72)',
    borderRadius: 20,
    backgroundColor: 'rgba(255,248,229,.94)',
    paddingTop: 10,
    paddingRight: 14,
    paddingBottom: 10,
    paddingLeft: 14,
    shadowColor: '#9A650D',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.12,
    shadowRadius: 9,
    elevation: 3,
  },
  timerMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  timerStatusBadge: {
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    backgroundColor: '#FFE7B0',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  timerStatusDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#C26F00',
  },
  timerStatusDotPaused: { backgroundColor: '#8A8179' },
  timerCaption: {
    color: colors.text,
    fontSize: 11.5,
    fontWeight: '800',
    letterSpacing: 0.45,
  },
  timer: {
    marginTop: 5,
    color: colors.text,
    fontSize: 46,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    letterSpacing: 1.6,
    lineHeight: 48,
  },
  targetTime: {
    flexShrink: 0,
    borderWidth: 1,
    borderColor: '#E7CAA0',
    borderRadius: 999,
    backgroundColor: '#FFFDF8',
    color: colors.textSub,
    fontSize: 11.5,
    fontWeight: '800',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  elapsedLabel: {
    marginTop: -1,
    color: colors.textSub,
    fontSize: 8.5,
    fontWeight: '800',
    letterSpacing: 1.3,
    opacity: 0.72,
  },
  timerPaused: { opacity: 0.55 },
  timerBrand: { fontFamily: fontFamilies.brand },
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
  timerMark: {
    width: 19,
    height: 19,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.8,
    borderColor: colors.textSub,
    borderRadius: 999,
  },
  timerMarkHand: {
    position: 'absolute',
    width: 1.8,
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.textSub,
    transform: [{ translateY: -2 }, { rotate: '-18deg' }],
  },
  timerMarkDot: {
    width: 3.5,
    height: 3.5,
    borderRadius: 999,
    backgroundColor: colors.textSub,
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
    borderColor: colors.dangerBorder,
    borderRadius: 18,
    backgroundColor: colors.dangerBg,
    paddingHorizontal: 14,
  },
  stopActionLabel: {
    color: colors.dangerText,
    fontFamily: Platform.select({
      ios: 'System',
      android: 'sans-serif-medium',
      default: 'system-ui',
    }),
    fontSize: 13.5,
    fontWeight: '700',
    letterSpacing: -0.15,
  },
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
  mascotFrame: {
    width: 104,
    height: 104,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    borderRadius: 52,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  mascotAnimation: { width: 94, height: 94 },
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
  carouselDragSurface: {
    width: '100%',
    minHeight: 0,
    flex: 1,
    justifyContent: 'center',
  },
  carouselViewport: { flexGrow: 0, flexShrink: 0 },
  carouselHint: { color: colors.textMuted, fontSize: 13, fontWeight: '800' },
  carouselCount: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
  blockCarousel: {
    minHeight: '100%',
    alignItems: 'center',
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
  cardActionRow: {
    width: '100%',
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 8,
    marginTop: 12,
  },
  infoButton: {
    minHeight: 44,
    minWidth: 0,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#E2AC48',
    borderRadius: 12,
    backgroundColor: '#FFF2D1',
    paddingVertical: 10,
    paddingHorizontal: 8,
    shadowColor: '#C28B28',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  infoButtonText: {
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '800',
    textAlign: 'center',
  },
  cardVariantAction: {
    minHeight: 44,
    minWidth: 0,
    width: '100%',
    alignSelf: 'stretch',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.greenBorder,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingVertical: 10,
    paddingHorizontal: 8,
  },
  cardVariantActionText: {
    color: colors.greenText,
    fontSize: 12.5,
    fontWeight: '800',
    textAlign: 'center',
  },
  cardActionPressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
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
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingTop: 6,
    paddingRight: 18,
    paddingBottom: 24,
    paddingLeft: 18,
  },
  smashAction: {
    height: 58,
    flexGrow: 0,
    flexShrink: 0,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    borderWidth: 1.5,
    borderColor: '#E2AC48',
    borderRadius: 18,
    overflow: 'hidden',
    paddingHorizontal: 8,
    shadowColor: '#C28B28',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.13,
    shadowRadius: 8,
    elevation: 3,
  },
  smashActionDisabled: {
    borderColor: '#DDD4CA',
    shadowOpacity: 0,
    elevation: 0,
  },
  smashActionGradient: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  smashActionText: {
    color: '#5A4636',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  restAction: {
    borderColor: '#AAA8A1',
    shadowColor: '#74716B',
    shadowOpacity: 0.14,
  },
  restActionContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  restActionText: {
    color: '#55534E',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  pressed: { opacity: 0.82 },
  restOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 40,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(20,32,16,.62)',
    padding: 24,
  },
  restTimerCard: {
    width: '100%',
    maxWidth: 360,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,.82)',
    borderRadius: 26,
    backgroundColor: 'rgba(255,253,248,.96)',
    paddingTop: 28,
    paddingRight: 24,
    paddingBottom: 24,
    paddingLeft: 24,
    shadowColor: '#8D5C09',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.16,
    shadowRadius: 10,
    elevation: 4,
  },
  restMessage: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: -0.2,
    textAlign: 'center',
  },
  restTimer: {
    marginTop: 12,
    color: colors.text,
    fontSize: 56,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    letterSpacing: 2,
    lineHeight: 58,
  },
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
    width: '100%',
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 22,
    borderRadius: 16,
    backgroundColor: colors.yellow,
    paddingVertical: 13,
    paddingHorizontal: 17,
  },
  restEndButtonText: { color: '#342E17', fontSize: 16, fontWeight: '900' },
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
  stopConfirmButton: {
    position: 'relative',
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    borderWidth: 1,
    borderColor: 'rgba(142, 50, 38, 0.8)',
    borderRadius: 18,
    padding: 17,
    shadowColor: '#8E3226',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.11,
    shadowRadius: 6,
    elevation: 3,
  },
  stopConfirmGradient: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    borderRadius: 18,
  },
  stopConfirmButtonText: {
    color: colors.surface,
    fontFamily: Platform.select({
      ios: 'System',
      android: 'sans-serif-medium',
      default: 'system-ui',
    }),
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: -0.15,
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
  stopReasonList: { gap: 8, marginTop: 6 },
  stopReasonChoiceButton: {
    width: '100%',
    alignItems: 'flex-start',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
  },
  stopReasonChoiceSelected: {
    backgroundColor: '#FFFFFF',
  },
  stopReasonChoiceText: {
    textAlign: 'left',
  },
  safetyReasonSection: {
    gap: 10,
    marginTop: 16,
    borderWidth: 1.5,
    borderColor: colors.dangerBorder,
    borderRadius: 18,
    backgroundColor: colors.dangerBg,
    padding: 14,
  },
  safetyReasonEyebrow: {
    color: colors.dangerText,
    fontSize: 12.5,
    fontWeight: '700',
    lineHeight: 18,
  },
  safetyReasonChoiceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  safetyReasonChoice: {
    flex: 1,
    width: 'auto',
  },
  inlineHelpAction: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.dangerBorder,
    borderRadius: 999,
    backgroundColor: colors.surface,
  },
  inlineHelpActionText: {
    color: colors.dangerText,
    fontSize: 14,
    fontWeight: '900',
  },
  inlineHelpPopup: {
    gap: 6,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: 14,
    backgroundColor: colors.surface,
    padding: 12,
  },
  safetyReasonWarning: {
    color: colors.dangerText,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 19,
  },
  acknowledgementRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  acknowledgementBox: {
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.dangerBorder,
    borderRadius: 7,
    backgroundColor: colors.surface,
  },
  acknowledgementBoxChecked: {
    borderColor: colors.dangerText,
    backgroundColor: colors.dangerText,
  },
  acknowledgementMark: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '900',
  },
  acknowledgementText: {
    flex: 1,
    color: colors.dangerText,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  helpSection: {
    gap: 6,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 16,
    backgroundColor: colors.surface,
    padding: 14,
  },
  helpSectionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  helpSectionBody: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 19,
  },
  helpNote: {
    color: colors.textSub,
    fontSize: 12.5,
    fontWeight: '600',
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
