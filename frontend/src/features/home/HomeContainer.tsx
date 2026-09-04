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
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
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
  planEditRequest,
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
  /** Server-owned check-in defaults, used only until today's check-in exists. */
  checkinDefaults: DailyContextDefaultsResponse | null;
  week: WeekResponse | null;
  sessions: WorkoutSessionLogSummary[];
};

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

const FALLBACK_LOCATION_CODE = 'HOME';
const EMPTY_SESSIONS: WorkoutSessionLogSummary[] = [];
const DEFAULT_FINAL_VALIDATION_HOLD_MS = 1_500;
/** Long enough for a drag to settle, short enough to save before a hand-off. */
const PLAN_EDIT_SAVE_DELAY_MS = 500;

function wait(milliseconds: number): Promise<void> {
  if (milliseconds <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
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
  decision,
  onDecisionChange,
  planRevision,
  onSessionStarted,
  onRestChosen,
  onCheckinDecisionSuccess,
  alternativeUsedCount = 0,
  onAlternativeSuccess,
  onRecoverDecision,
  todaySession = null,
  localSessionState = 'ACTIVE',
  onResumeWorkout,
  onTab,
  onOpenCalendar,
  hasUnreadNotification = false,
  notificationToastVisible = false,
  onNotifications,
  finalValidationHoldMs = DEFAULT_FINAL_VALIDATION_HOLD_MS,
}: {
  api: Api;
  me: MeResponse;
  /** Owned by the flow above, so the choice survives leaving this screen. */
  restToday: boolean;
  /** Today's decision, held above so a tab switch does not discard it. */
  decision: DecisionResponse | null;
  onDecisionChange: Dispatch<SetStateAction<DecisionResponse | null>>;
  planRevision: WeeklyPlanRevisionResponse | null;
  /** Retained for callers until the retired location-revision UI is removed. */
  onPlanRevisionChange?: (revision: WeeklyPlanRevisionResponse | null) => void;
  onSessionStarted: (sessionId: string, plan: WorkoutPlan) => void;
  onRestChosen: (pressureNotificationsAllowed: boolean) => void;
  /** Clear flow-owned REST state only after a replacement decision succeeds. */
  onCheckinDecisionSuccess?: () => void;
  /** UI-only until the backend owns the combined alternative quota. */
  alternativeUsedCount?: number;
  onAlternativeSuccess?: () => void;
  /** Re-read the flow-owned decision when Home data is manually refreshed. */
  onRecoverDecision?: () => void;
  todaySession?: WorkoutSessionDetailResponse | null;
  localSessionState?: LocalWorkoutPresentationState;
  onResumeWorkout?: () => void;
  onTab: (tab: TabId) => void;
  onOpenCalendar: () => void;
  hasUnreadNotification?: boolean;
  notificationToastVisible?: boolean;
  onNotifications?: () => void;
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
      const [routine, context, checkinDefaults, week, sessionList] =
        await Promise.all([
          routinePromise,
          optional(api.getDailyContext(localDate, signal), ['notFound']),
          // The check-in must still open when this is unavailable, so every
          // absence falls back to the profile defaults the screen already has.
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
  const inFlight = useRef(false);

  const data = state.status === 'ready' ? state.data : null;
  const routine = data?.routine ?? null;
  const context = data?.context ?? null;
  const checkinDefaults = data?.checkinDefaults ?? null;
  const week = data?.week ?? null;
  const sessions = data?.sessions ?? EMPTY_SESSIONS;

  // Memoised because it feeds the mutation callbacks' dependency lists; a new
  // array each render would rebuild them on every render.
  const locationCodes = useMemo(
    () =>
      profile === null || profile === undefined
        ? []
        : profile.available_location_codes.length > 0
          ? profile.available_location_codes
          : [profile.preferred_location_code],
    [profile],
  );

  const run = useCallback((kind: HomeBusyKind, action: () => Promise<void>) => {
    // Overlapping actions can represent different user intents. Serialize
    // them even though a retry of one saved decision reuses its original key.
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setBusy(kind);
    setRoutineLoadingPhaseCode(null);
    setActionError(null);
    setStaleContext(false);

    void action()
      .catch((error: unknown) => {
        setActionError(actionMessage(error));
        setStaleContext(isApiError(error) && error.kind === 'stale');
      })
      .finally(() => {
        inFlight.current = false;
        setBusy(null);
        setRoutineLoadingPhaseCode(null);
      });
  }, []);

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
            location_code:
              draft.locationCode ??
              latestContext?.location_code ??
              profile?.preferred_location_code ??
              locationCodes[0] ??
              FALLBACK_LOCATION_CODE,
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
        setData({ routine, context: saved, checkinDefaults, week, sessions });
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
      profile,
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
      onSessionStarted(selection.workout_session.session_id, plan);
    });
  }, [api, decision, onSessionStarted, run]);

  const chooseRest = useCallback(() => {
    if (decision === null) {
      return;
    }
    const option = decision.options.find(
      (entry) => entry.option_code === 'REST' && entry.selectable,
    );
    if (option === undefined) {
      return;
    }

    run('starting', async () => {
      const selection = await api.selectOption(
        decision.decision_id,
        option.option_id,
      );
      onRestChosen(selection.pressure_notifications_allowed ?? false);
    });
  }, [api, decision, onRestChosen, run]);

  /**
   * A user edit of today's plan — set and repetition changes (ADR-0018 D4) or a
   * reorder inside one phase (D5) — is applied to the decision first so the
   * routine card and the workout screen read the same plan, then sent to the
   * server. `updateDecisionPlan` is optional: until the route exists the edit
   * lives only as long as the running app, and implementing it turns on
   * persistence without another change here.
   *
   * Dragging emits one move per step, so the request is deferred until the user
   * settles rather than sending an intermediate order.
   */
  const planSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A drag emits several moves before React re-renders, so the edit chain reads
  // its own last result rather than the decision prop of the current render.
  const editedPlan = useRef<{ decisionId: string; plan: WorkoutPlan } | null>(
    null,
  );

  useEffect(
    () => () => {
      if (planSaveTimer.current !== null) {
        clearTimeout(planSaveTimer.current);
      }
    },
    [],
  );

  const applyPlanEdit = useCallback(
    (edit: (plan: WorkoutPlan) => WorkoutPlan) => {
      const decisionId = decision?.decision_id ?? null;
      const current =
        editedPlan.current?.decisionId === decisionId
          ? editedPlan.current.plan
          : (decision?.final_plan ?? null);
      if (decisionId === null || current === null) {
        return;
      }
      const plan = edit(current);
      if (plan === current) {
        return;
      }
      editedPlan.current = { decisionId, plan };
      onDecisionChange((latest) =>
        latest?.decision_id === decisionId
          ? { ...latest, final_plan: plan }
          : latest,
      );

      const save = api.updateDecisionPlan;
      if (save === undefined) {
        return;
      }
      if (planSaveTimer.current !== null) {
        clearTimeout(planSaveTimer.current);
      }
      planSaveTimer.current = setTimeout(() => {
        planSaveTimer.current = null;
        void save(decisionId, planEditRequest(plan))
          .then((next) => {
            setActionError(null);
            editedPlan.current = null;
            onDecisionChange((latest) =>
              latest?.decision_id === next.decision_id ? next : latest,
            );
          })
          .catch((error: unknown) => {
            setActionError(actionMessage(error));
            editedPlan.current = null;
            // The server did not accept the edit, so stop showing it and read
            // back the plan it actually stored.
            onRecoverDecision?.();
          });
      }, PLAN_EDIT_SAVE_DELAY_MS);
    },
    [api, decision, onDecisionChange, onRecoverDecision],
  );

  const reorderPlan = useCallback(
    (from: number, to: number) => {
      applyPlanEdit((plan) => moveWorkoutPlanItem(plan, from, to));
    },
    [applyPlanEdit],
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
      }));
      if (prescriptions.length === 0) {
        return;
      }
      applyPlanEdit((plan) => applyPlanItemPrescriptions(plan, prescriptions));
    },
    [applyPlanEdit],
  );

  const permissionDenied =
    state.status === 'error' &&
    isApiError(state.error) &&
    state.error.kind === 'permission';

  return (
    <HomeScreen
      nickname={profile?.nickname ?? '회원'}
      profileImageUrl={profile?.profile_image_url ?? null}
      localDate={localDate}
      status={
        state.status === 'ready'
          ? 'ready'
          : state.status === 'error'
            ? 'error'
            : 'loading'
      }
      errorMessage={state.status === 'error' ? state.message : undefined}
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
      persistentPains={checkinDefaults?.pains ?? profile?.persistent_pains}
      locationCodes={locationCodes}
      busy={busy}
      routineLoadingPhaseCode={routineLoadingPhaseCode ?? undefined}
      actionError={actionError}
      staleContext={staleContext}
      onRetryCheckin={
        lastDraft === null ? undefined : () => submitCheckin(lastDraft, true)
      }
      onRetryDecision={pendingDecision === null ? undefined : retryDecision}
      onSubmitCheckin={(draft) => submitCheckin(draft)}
      onRequestAlternativeCheckin={(draft, changed) =>
        changed ? submitCheckin(draft, false, true) : regenerateDecision()
      }
      onStartWorkout={startWorkout}
      onResumeWorkout={onResumeWorkout}
      onChooseRest={chooseRest}
      onRegenerateDecision={regenerateDecision}
      onReorderPlan={reorderPlan}
      onSubmitUserEdits={submitUserEdits}
      onNavigateTab={onTab}
      hasUnreadNotification={hasUnreadNotification}
      notificationToastVisible={notificationToastVisible}
      onNotifications={onNotifications}
      onProfile={() => onTab('my')}
      onOpenCalendar={onOpenCalendar}
    />
  );
}
