/**
 * The API side of the home screen.
 *
 * Home is the entry point, so the whole daily loop is driven from here:
 * today's stored state is read, the check-in is written, the server's decision
 * is requested, and the selected option hands off to the workout session. The
 * screen itself stays presentational — every server rule stays on the server.
 *
 * The flow above owns today's decision so switching tabs does not discard it.
 * It also re-reads the server's latest completed decision on Home entry. This
 * container performs the same read after an ambiguous creation failure so a
 * committed routine is not reported as failed merely because its response was
 * lost.
 */

import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';

import type { Api } from '../../api/endpoints';
import { createIdempotencyKey } from '../../api/client';
import {
  isApiError,
  messageForError,
  type ApiErrorKind,
} from '../../api/errors';
import { planRevisionReasonLabel } from '../../api/labels';
import type {
  DailyContextDefaultsResponse,
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  PlanRevisionResponse,
  RoutineResponse,
  WeeklyPlanRevisionResponse,
  WeekResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import {
  applyPlanItemPrescriptions,
  moveWorkoutPlanItem,
  planItemOrderRequest,
  planItemWorkSecondsPerSet,
  workoutPlanRevision,
} from '../../api/workoutPlan';
import {
  localDateString,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import {
  HomeScreen,
  type HomeBusyKind,
  type HomeUserEdits,
} from './HomeScreen';
import {
  sleepMinutesFromHours,
  type HomeCheckinDraft,
  type LocalWorkoutPresentationState,
} from './homeModel';
import type { RoutineGenerationPhaseCode } from './RoutineGenerationLoading';

type HomeData = {
  routine: RoutineResponse;
  context: DailyContextResponse | null;
  previousContext: DailyContextResponse | null;
  /** Server-owned check-in defaults, used only until today's check-in exists. */
  checkinDefaults: DailyContextDefaultsResponse | null;
  week: WeekResponse | null;
  sessions: WorkoutSessionLogSummary[];
};

export type HomeRecoveryState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'error'; message: string; permissionDenied: boolean };

type PendingRoutineAttempt = {
  scope: string;
  idempotencyKey: string;
};

type DecisionBaseline =
  | { status: 'known-none' }
  | { status: 'known'; decisionId: string }
  | { status: 'unknown' };

type PendingDecisionAttempt = {
  context: DailyContextResponse;
  idempotencyKey: string;
  baseline: DecisionBaseline;
  countsAsAlternative: boolean;
};

type PlanEditAttempt = {
  decisionId: string;
  optimisticPlan: WorkoutPlan;
  execute: () => Promise<PlanRevisionResponse>;
};

const EMPTY_SESSIONS: WorkoutSessionLogSummary[] = [];
const DEFAULT_FINAL_VALIDATION_HOLD_MS = 1_500;

function planFromRevision(response: PlanRevisionResponse): WorkoutPlan {
  return {
    ...response.final_plan,
    plan_revision: response.plan_revision,
  };
}

function canRetryPlanEdit(error: unknown): boolean {
  return (
    !isApiError(error) ||
    error.kind === 'network' ||
    error.kind === 'server' ||
    error.kind === 'unavailable'
  );
}

function wait(milliseconds: number): Promise<void> {
  if (milliseconds <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function previousLocalDate(localDate: string): string {
  const date = new Date(`${localDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function canShowFinalValidation(decision: DecisionResponse): boolean {
  return (
    decision.final_plan !== null &&
    decision.action_code !== 'STOP_AND_SEEK_HELP' &&
    decision.safety_status_code !== 'BLOCKED'
  );
}

/** Absent resources are a normal state here, not a failure to report. */
function optional<T>(
  promise: Promise<T>,
  kinds: readonly ApiErrorKind[],
): Promise<T | null> {
  return promise.catch((error: unknown) => {
    if (isApiError(error) && kinds.includes(error.kind)) {
      return null;
    }
    throw error;
  });
}

function actionMessage(error: unknown): string {
  if (isApiError(error) && error.code === 'PLAN_REVISION_REJECTED') {
    const messages = Array.from(
      new Set(
        error.details
          .map((detail) =>
            detail.reason_code
              ? planRevisionReasonLabel(detail.reason_code)
              : null,
          )
          .filter((message): message is string => message !== null),
      ),
    );
    if (messages.length > 0) {
      return messages.join(' ');
    }
  }
  return messageForError(error);
}

function isAmbiguousMutationError(error: unknown): boolean {
  return (
    !isApiError(error) ||
    error.kind === 'network' ||
    error.kind === 'conflict' ||
    error.kind === 'server' ||
    error.kind === 'unavailable'
  );
}

function isExactApiError(error: unknown, code: string): boolean {
  return isApiError(error) && error.code === code;
}

function isNewDecision(
  stored: DecisionResponse,
  baseline: DecisionBaseline,
): boolean {
  if (baseline.status === 'known-none') {
    return true;
  }
  return (
    baseline.status === 'known' && stored.decision_id !== baseline.decisionId
  );
}

function decisionStageError(error: unknown): unknown {
  if (!isApiError(error) || error.kind === 'network') {
    return Object.assign(new Error('decision result could not be confirmed'), {
      userMessage:
        '체크인은 저장됐지만 오늘 루틴 생성 결과를 확인하지 못했어요. 저장된 체크인으로 루틴 생성만 다시 시도할 수 있어요.',
    });
  }
  if (
    error.kind === 'conflict' ||
    error.kind === 'server' ||
    error.kind === 'unavailable'
  ) {
    return Object.assign(
      new Error('decision generation failed after check-in'),
      {
        userMessage: `체크인은 저장됐지만 ${error.message}`,
      },
    );
  }
  return error;
}

export function HomeContainer({
  api,
  me,
  restToday,
  safetyGuidance,
  decision,
  onDecisionChange,
  planRevision,
  onSessionStarted,
  onCheckinDecisionSuccess,
  alternativeUsedCount = 0,
  onAlternativeSuccess,
  decisionGenerationPending = false,
  onDecisionGenerationPendingChange,
  onRecoverDecision,
  todaySession = null,
  localSessionState = 'ACTIVE',
  onResumeWorkout,
  onTab,
  onOpenCalendar,
  onOpenExerciseCatalog,
  hasUnreadNotification = false,
  notificationPanel,
  onDismissNotificationPanel,
  notificationToastVisible = false,
  onNotifications,
  recoveryState,
  finalValidationHoldMs = DEFAULT_FINAL_VALIDATION_HOLD_MS,
}: {
  api: Api;
  me: MeResponse;
  /** Owned by the flow above, so the choice survives leaving this screen. */
  restToday: boolean;
  safetyGuidance?: string;
  /** Today's decision, held above so a tab switch does not discard it. */
  decision: DecisionResponse | null;
  onDecisionChange: Dispatch<SetStateAction<DecisionResponse | null>>;
  planRevision: WeeklyPlanRevisionResponse | null;
  /** Retained for callers until the retired location-revision UI is removed. */
  onPlanRevisionChange?: (revision: WeeklyPlanRevisionResponse | null) => void;
  onSessionStarted: (
    sessionId: string,
    plan: WorkoutPlan,
    locationCode?: string,
  ) => void;
  /** Clear flow-owned REST state only after a replacement decision succeeds. */
  onCheckinDecisionSuccess?: () => void;
  /** UI-only until the backend owns the combined alternative quota. */
  alternativeUsedCount?: number;
  onAlternativeSuccess?: () => void;
  /** Flow-owned generation state, preserved while Home is temporarily unmounted. */
  decisionGenerationPending?: boolean;
  onDecisionGenerationPendingChange?: (pending: boolean) => void;
  /** Re-read the flow-owned decision when Home data is manually refreshed. */
  onRecoverDecision?: () => void;
  todaySession?: WorkoutSessionDetailResponse | null;
  localSessionState?: LocalWorkoutPresentationState;
  onResumeWorkout?: (locationCode?: string) => void;
  onTab: (tab: TabId) => void;
  onOpenCalendar: () => void;
  onOpenExerciseCatalog?: () => void;
  hasUnreadNotification?: boolean;
  notificationPanel?: ReactNode;
  onDismissNotificationPanel?: () => void;
  notificationToastVisible?: boolean;
  onNotifications?: () => void;
  /** The flow-owned aggregate snapshot read used on Home entry and retry. */
  recoveryState?: HomeRecoveryState;
  /** Testable presentation delay after a decision response is ready. */
  finalValidationHoldMs?: number;
}) {
  const profile = me.profile;
  const now = new Date();
  const localDate = localDateString(now, profile?.timezone);
  const weekStart = weekStartString(now, profile?.timezone);
  const pendingRoutineAttempt = useRef<PendingRoutineAttempt | null>(null);
  const routineRecoveryScope =
    profile === null
      ? null
      : `${me.user_id}:${profile.profile_version}:${localDate}`;

  const { state, reload, setData } = useAsyncData<HomeData>(
    async (signal) => {
      const routinePromise = api
        .getCurrentRoutine(localDate, signal)
        .then((routine) => {
          if (pendingRoutineAttempt.current?.scope === routineRecoveryScope) {
            pendingRoutineAttempt.current = null;
          }
          return routine;
        })
        .catch(async (error: unknown) => {
          if (
            !isExactApiError(error, 'ROUTINE_NOT_FOUND') ||
            profile === null ||
            routineRecoveryScope === null
          ) {
            throw error;
          }

          const attempt =
            pendingRoutineAttempt.current?.scope === routineRecoveryScope
              ? pendingRoutineAttempt.current
              : {
                  scope: routineRecoveryScope,
                  idempotencyKey: createIdempotencyKey(),
                };
          pendingRoutineAttempt.current = attempt;

          try {
            const created = await api.createRoutine(
              {
                effective_from: localDate,
                goal_code: profile.primary_goal_code,
              },
              attempt.idempotencyKey,
            );
            if (pendingRoutineAttempt.current === attempt) {
              pendingRoutineAttempt.current = null;
            }
            return created;
          } catch (creationError: unknown) {
            if (isAmbiguousMutationError(creationError)) {
              try {
                const recovered = await api.getCurrentRoutine(localDate);
                if (pendingRoutineAttempt.current === attempt) {
                  pendingRoutineAttempt.current = null;
                }
                return recovered;
              } catch {
                // Preserve the creation error. The same idempotency key remains
                // available for a manual retry of this exact recovery intent.
              }
            }
            throw creationError;
          }
        });
      const [
        routine,
        context,
        previousContext,
        checkinDefaults,
        week,
        sessionList,
      ] = await Promise.all([
        routinePromise,
        optional(api.getDailyContext(localDate, signal), ['notFound']),
        optional(api.getDailyContext(previousLocalDate(localDate), signal), [
          'notFound',
        ]),
        // The check-in must still open when this is unavailable. Persistent
        // pains can fall back to the profile, but location choices cannot:
        // the defaults response is their only authority.
        optional(api.getDailyContextDefaults(localDate, signal), [
          'notFound',
          'validation',
          'conflict',
          'unavailable',
          'server',
        ]),
        // Weekly summaries are secondary. They may be absent while the daily
        // flow remains usable, but authentication and permission errors still
        // surface through the Home state.
        optional(api.getWeek(weekStart, signal), [
          'notFound',
          'validation',
          'conflict',
          'unavailable',
          'server',
        ]),
        optional(
          api.listWorkoutSessions(
            {
              fromLocalDate: weekStart,
              toLocalDate: localDate,
              limit: 100,
            },
            signal,
          ),
          ['notFound', 'validation', 'unavailable', 'server'],
        ),
      ]);
      return {
        routine,
        context,
        previousContext,
        checkinDefaults,
        week,
        sessions: sessionList?.items ?? [],
      };
    },
    [
      api,
      localDate,
      me.user_id,
      profile?.primary_goal_code,
      profile?.profile_version,
      weekStart,
    ],
  );

  const [busy, setBusy] = useState<HomeBusyKind | null>(null);
  const [routineLoadingPhaseCode, setRoutineLoadingPhaseCode] =
    useState<RoutineGenerationPhaseCode | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [staleContext, setStaleContext] = useState(false);
  const [lastDraft, setLastDraft] = useState<HomeCheckinDraft | null>(null);
  const [pendingDecision, setPendingDecision] =
    useState<PendingDecisionAttempt | null>(null);
  const [pendingPlanEdit, setPendingPlanEdit] =
    useState<PlanEditAttempt | null>(null);
  const inFlight = useRef(false);

  const data = state.status === 'ready' ? state.data : null;
  const routine = data?.routine ?? null;
  const context = data?.context ?? null;
  const previousContext = data?.previousContext ?? null;
  const checkinDefaults = data?.checkinDefaults ?? null;
  const week = data?.week ?? null;
  const sessions = data?.sessions ?? EMPTY_SESSIONS;

  const locationCodes = useMemo(() => {
    const choices = (checkinDefaults?.selectable_location_codes ?? []).filter(
      (code, index, codes) =>
        (code === 'HOME' || code === 'GYM') && codes.indexOf(code) === index,
    );
    const preferred = [
      context?.location_code,
      previousContext?.location_code,
    ].find((code) => code !== undefined && choices.includes(code));
    return preferred === undefined
      ? choices
      : [preferred, ...choices.filter((code) => code !== preferred)];
  }, [
    checkinDefaults?.selectable_location_codes,
    context?.location_code,
    previousContext?.location_code,
  ]);

  const run = useCallback(
    (kind: HomeBusyKind, action: () => Promise<void>) => {
      // Overlapping actions can represent different user intents. Serialize
      // them even though a retry of one saved decision reuses its original key.
      if (inFlight.current) {
        return;
      }
      const generatesDecision =
        kind === 'decision-generation' || kind === 'regeneration';
      inFlight.current = true;
      setBusy(kind);
      if (generatesDecision) {
        onDecisionGenerationPendingChange?.(true);
      }
      setRoutineLoadingPhaseCode(null);
      setActionError(null);
      setPendingPlanEdit(null);
      setStaleContext(false);

      void action()
        .catch((error: unknown) => {
          setActionError(actionMessage(error));
          setStaleContext(isApiError(error) && error.kind === 'stale');
        })
        .finally(() => {
          inFlight.current = false;
          setBusy(null);
          if (generatesDecision) {
            onDecisionGenerationPendingChange?.(false);
          }
          setRoutineLoadingPhaseCode(null);
        });
    },
    [onDecisionGenerationPendingChange],
  );

  const holdFinalValidation = useCallback(async () => {
    setRoutineLoadingPhaseCode('FINAL_VALIDATION');
    await wait(finalValidationHoldMs);
  }, [finalValidationHoldMs]);

  const requestDecision = useCallback(
    async (attempt: PendingDecisionAttempt) => {
      try {
        const next = await api.createDecision(
          {
            local_date: localDate,
            daily_context_id: attempt.context.id,
            expected_context_version: attempt.context.context_version,
          },
          attempt.idempotencyKey,
        );
        if (canShowFinalValidation(next)) {
          await holdFinalValidation();
        }
        setPendingDecision(null);
        onDecisionChange(next);
        onCheckinDecisionSuccess?.();
        if (attempt.countsAsAlternative && next.final_plan !== null) {
          onAlternativeSuccess?.();
        }
      } catch (error: unknown) {
        if (
          isAmbiguousMutationError(error) &&
          attempt.baseline.status !== 'unknown'
        ) {
          try {
            const stored = await api.getDecisionForDate(localDate);
            if (isNewDecision(stored, attempt.baseline)) {
              if (canShowFinalValidation(stored)) {
                await holdFinalValidation();
              }
              setPendingDecision(null);
              onDecisionChange(stored);
              onCheckinDecisionSuccess?.();
              if (attempt.countsAsAlternative && stored.final_plan !== null) {
                onAlternativeSuccess?.();
              }
              return;
            }
          } catch {
            // The original creation error remains the most useful result. A
            // missing or unavailable recovery read must not replace it.
          }
        }
        if (isApiError(error)) {
          if (error.kind !== 'stale' && !isAmbiguousMutationError(error)) {
            // Validation/input errors require a changed check-in rather than
            // replaying a request whose outcome the server already knows.
            setPendingDecision(null);
          }
        }
        throw decisionStageError(error);
      }
    },
    [
      api,
      holdFinalValidation,
      localDate,
      onCheckinDecisionSuccess,
      onAlternativeSuccess,
      onDecisionChange,
    ],
  );

  const submitCheckin = useCallback(
    (
      draft: HomeCheckinDraft,
      refreshVersion = false,
      countsAsAlternative = false,
    ) => {
      if (routine === null) {
        return;
      }
      setLastDraft(draft);
      // A fresh check-in supersedes the recommendation currently on screen.
      // Remove it before loading so an error cannot leave the old routine
      // looking like the result of the new request.
      onDecisionChange(null);

      run('decision-generation', async () => {
        const sleepMinutes = sleepMinutesFromHours(draft.sleepHours);
        if (sleepMinutes === undefined) {
          throw new Error('sleep hours out of range');
        }
        if (
          draft.locationCode === null ||
          !locationCodes.includes(draft.locationCode)
        ) {
          throw Object.assign(new Error('daily location is required'), {
            userMessage:
              '운동 장소 선택지를 다시 불러온 뒤 집 또는 헬스장을 선택해주세요.',
          });
        }

        // A previous attempt lost the optimistic-lock race, so the retry has to
        // carry the version that is stored now rather than the stale one.
        let latestContext = context;
        let expectedVersion = latestContext?.context_version;
        if (refreshVersion) {
          const current = await optional(api.getDailyContext(localDate), [
            'notFound',
          ]);
          latestContext = current;
          expectedVersion = current?.context_version;
        }

        const saved = await api.replaceDailyContext(
          localDate,
          {
            fatigue_level_code: draft.fatigueLevelCode,
            available_time_minutes: draft.availableTimeMinutes,
            location_code: draft.locationCode,
            sleep_minutes: sleepMinutes,
            sleep_source_code: sleepMinutes === null ? null : 'MANUAL',
            pain_present: Object.keys(draft.pains).length > 0,
            red_flag_present: draft.redFlagPresent,
            pains: Object.entries(draft.pains).map(
              ([body_area_code, intensity_score]) => ({
                body_area_code,
                intensity_score,
              }),
            ),
          },
          expectedVersion,
        );
        // Check-in persistence is already complete even if decision creation
        // later loses its response. Reflect it now so a retry never rewrites
        // the same check-in merely to regenerate today's routine.
        setData({
          routine,
          context: saved,
          previousContext,
          checkinDefaults,
          week,
          sessions,
        });
        let baseline: DecisionBaseline =
          decision === null
            ? { status: 'unknown' }
            : { status: 'known', decisionId: decision.decision_id };
        if (decision === null) {
          try {
            const stored = await api.getDecisionForDate(localDate);
            baseline = {
              status: 'known',
              decisionId: stored.decision_id,
            };
          } catch (error: unknown) {
            baseline = isExactApiError(error, 'DECISION_NOT_FOUND')
              ? { status: 'known-none' }
              : { status: 'unknown' };
          }
        }
        const attempt: PendingDecisionAttempt = {
          context: saved,
          idempotencyKey: createIdempotencyKey(),
          baseline,
          countsAsAlternative,
        };
        setPendingDecision(attempt);
        // A previous routine belongs to the previous check-in. Hide it while
        // the server decides from the newly saved context so an error and a
        // stale routine are never presented as one result.
        onDecisionChange(null);
        await requestDecision(attempt);
      });
    },
    [
      api,
      checkinDefaults,
      context,
      decision,
      localDate,
      locationCodes,
      onDecisionChange,
      previousContext,
      requestDecision,
      routine,
      run,
      setData,
      sessions,
      week,
    ],
  );

  const retryDecision = useCallback(() => {
    if (pendingDecision === null) {
      return;
    }
    run('decision-generation', () => requestDecision(pendingDecision));
  }, [pendingDecision, requestDecision, run]);

  const startWorkout = useCallback(() => {
    if (decision === null || decision.final_plan === null) {
      return;
    }
    const option = decision.options.find(
      (entry) => entry.option_code === 'FINAL_ROUTINE' && entry.selectable,
    );
    if (option === undefined) {
      return;
    }
    const plan = decision.final_plan;

    run('starting', async () => {
      const selection = await api.selectOption(
        decision.decision_id,
        option.option_id,
      );
      if (selection.workout_session === null) {
        return;
      }
      onSessionStarted(
        selection.workout_session.session_id,
        plan,
        context?.location_code,
      );
    });
  }, [api, context?.location_code, decision, onSessionStarted, run]);

  const persistPlanEdit = useCallback(
    (attempt: PlanEditAttempt) => {
      if (inFlight.current) {
        return;
      }
      inFlight.current = true;
      setBusy('plan-edit');
      setActionError(null);
      setPendingPlanEdit(null);
      onDecisionChange((latest) =>
        latest?.decision_id === attempt.decisionId
          ? { ...latest, final_plan: attempt.optimisticPlan }
          : latest,
      );

      void attempt
        .execute()
        .then((response) => {
          setActionError(null);
          onDecisionChange((latest) =>
            latest?.decision_id === response.decision_id
              ? { ...latest, final_plan: planFromRevision(response) }
              : latest,
          );
        })
        .catch((error: unknown) => {
          setActionError(actionMessage(error));
          setPendingPlanEdit(canRetryPlanEdit(error) ? attempt : null);
          // A stale or ambiguous result cannot remain an authoritative local
          // plan. Read back the decision the server actually stored.
          onRecoverDecision?.();
        })
        .finally(() => {
          inFlight.current = false;
          setBusy(null);
        });
    },
    [onDecisionChange, onRecoverDecision],
  );

  const reorderPlan = useCallback(
    (from: number, to: number) => {
      const current = decision?.final_plan;
      if (!decision || !current) {
        return;
      }
      const plan = moveWorkoutPlanItem(current, from, to);
      if (plan === current) {
        return;
      }
      const completedPlanItemIds =
        todaySession?.items
          .filter((item) => item.status_code === 'COMPLETED')
          .map((item) => item.plan_item_id) ?? [];
      const body = planItemOrderRequest(plan, completedPlanItemIds);
      const idempotencyKey = createIdempotencyKey();
      persistPlanEdit({
        decisionId: decision.decision_id,
        optimisticPlan: plan,
        execute: () =>
          api.updateDecisionPlanOrder(
            decision.decision_id,
            body,
            idempotencyKey,
          ),
      });
    },
    [api, decision, persistPlanEdit, todaySession],
  );

  const regenerateDecision = useCallback(() => {
    const plan = decision?.final_plan;
    const sequence = decision?.regeneration_sequence;
    if (!decision || !plan || (sequence !== 0 && sequence !== 1)) {
      return;
    }
    const decisionId = decision.decision_id;

    run('regeneration', async () => {
      const next = await api.regenerateDecision(decisionId, {
        expected_plan_id: plan.plan_id,
        expected_regeneration_sequence: sequence,
      });
      if (canShowFinalValidation(next)) {
        await holdFinalValidation();
      }
      onDecisionChange(next);
      if (next.final_plan !== null) {
        onAlternativeSuccess?.();
      }
    });
  }, [
    api,
    decision,
    holdFinalValidation,
    onAlternativeSuccess,
    onDecisionChange,
    run,
  ]);

  const submitUserEdits = useCallback(
    (edits: HomeUserEdits) => {
      const prescriptions = edits.itemOverrides.map((override) => ({
        plan_item_id: override.planItemId,
        sets: override.sets,
        reps: override.reps,
        workSecondsPerSet: override.workSecondsPerSet,
      }));
      if (prescriptions.length === 0) {
        return;
      }
      const current = decision?.final_plan;
      if (!decision || !current) {
        return;
      }
      const changed = prescriptions.flatMap((edit) => {
        const item = current.items.find(
          (candidate) => candidate.plan_item_id === edit.plan_item_id,
        );
        if (item === undefined) {
          return [];
        }
        // Only when the user actually retyped it. A sets-only edit leaves the
        // duration to the server, which resolves it from the reviewed catalog
        // rather than trusting a figure this screen derived.
        const editedWorkSeconds =
          edit.workSecondsPerSet !== null &&
          edit.workSecondsPerSet !== planItemWorkSecondsPerSet(item)
            ? edit.workSecondsPerSet
            : null;
        if (
          item.sets === edit.sets &&
          item.reps === edit.reps &&
          editedWorkSeconds === null
        ) {
          return [];
        }
        return [{ ...edit, workSecondsPerSet: editedWorkSeconds }];
      });
      const plan = applyPlanItemPrescriptions(current, changed);
      if (changed.length === 0 || plan === current) {
        return;
      }
      const idempotencyKeys = changed.map(() => createIdempotencyKey());
      persistPlanEdit({
        decisionId: decision.decision_id,
        optimisticPlan: plan,
        execute: async () => {
          let serverPlan = current;
          let response: PlanRevisionResponse | null = null;
          for (const [index, edit] of changed.entries()) {
            response = await api.updateDecisionPlanItem(
              decision.decision_id,
              edit.plan_item_id,
              {
                expected_plan_id: serverPlan.plan_id,
                expected_plan_revision: workoutPlanRevision(serverPlan),
                sets: edit.sets,
                reps: edit.reps,
                // Sent only for an item measured in time; the server refuses it
                // on a repetition-based one, whose per-set work it derives.
                ...(edit.workSecondsPerSet === null
                  ? {}
                  : { work_seconds_per_set: edit.workSecondsPerSet }),
              },
              idempotencyKeys[index],
            );
            serverPlan = planFromRevision(response);
          }
          return response!;
        },
      });
    },
    [api, decision, persistPlanEdit],
  );

  const retryPlanEdit = useCallback(() => {
    if (pendingPlanEdit !== null) {
      persistPlanEdit(pendingPlanEdit);
    }
  }, [pendingPlanEdit, persistPlanEdit]);

  const recoveryError =
    recoveryState?.status === 'error' ? recoveryState : null;
  const permissionDenied =
    recoveryError?.permissionDenied === true ||
    (state.status === 'error' &&
      isApiError(state.error) &&
      state.error.kind === 'permission');
  const homeStatus =
    permissionDenied || state.status === 'error' || recoveryError !== null
      ? 'error'
      : state.status === 'loading' || recoveryState?.status === 'loading'
        ? 'loading'
        : 'ready';
  const homeErrorMessage =
    recoveryError?.message ??
    (state.status === 'error' ? state.message : undefined);

  return (
    <HomeScreen
      nickname={profile?.nickname ?? '회원'}
      profileImageUrl={profile?.profile_image_url ?? null}
      localDate={localDate}
      status={homeStatus}
      errorMessage={homeErrorMessage}
      exerciseApi={api}
      permissionDenied={permissionDenied}
      onRetry={
        permissionDenied
          ? undefined
          : () => {
              reload();
              onRecoverDecision?.();
            }
      }
      routine={routine}
      context={context}
      decision={decision}
      alternativeUsedCount={alternativeUsedCount}
      todaySession={todaySession}
      localSessionState={localSessionState}
      week={week}
      sessions={sessions}
      weeklyGoalCount={profile?.desired_weekly_workout_count ?? 1}
      planRevision={planRevision}
      restToday={restToday}
      safetyGuidance={safetyGuidance}
      persistentPains={checkinDefaults?.pains ?? profile?.persistent_pains}
      locationCodes={locationCodes}
      busy={busy ?? (decisionGenerationPending ? 'decision-generation' : null)}
      routineLoadingPhaseCode={routineLoadingPhaseCode ?? undefined}
      actionError={actionError}
      staleContext={staleContext}
      onRetryCheckin={
        lastDraft === null ? undefined : () => submitCheckin(lastDraft, true)
      }
      onRetryDecision={pendingDecision === null ? undefined : retryDecision}
      onRetryPlanEdit={pendingPlanEdit === null ? undefined : retryPlanEdit}
      onSubmitCheckin={(draft) => submitCheckin(draft)}
      onRequestAlternativeCheckin={(draft, changed) =>
        changed ? submitCheckin(draft, false, true) : regenerateDecision()
      }
      onStartWorkout={startWorkout}
      onResumeWorkout={
        onResumeWorkout
          ? () => onResumeWorkout(context?.location_code)
          : undefined
      }
      onRegenerateDecision={regenerateDecision}
      onReorderPlan={reorderPlan}
      onSubmitUserEdits={submitUserEdits}
      onNavigateTab={onTab}
      hasUnreadNotification={hasUnreadNotification}
      notificationPanel={notificationPanel}
      onDismissNotificationPanel={onDismissNotificationPanel}
      notificationToastVisible={notificationToastVisible}
      onNotifications={onNotifications}
      onProfile={() => onTab('my')}
      onOpenCalendar={onOpenCalendar}
      onOpenExerciseCatalog={onOpenExerciseCatalog}
    />
  );
}
