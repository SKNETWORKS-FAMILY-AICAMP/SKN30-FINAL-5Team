/**
 * The API side of the home screen.
 *
 * Home is the entry point, so the whole daily loop is driven from here:
 * today's stored state is read, the check-in is written, the server's decision
 * is requested, and the selected option hands off to the workout session. The
 * screen itself stays presentational — every server rule stays on the server.
 *
 * Two reads the design would use do not exist in the contract yet:
 *
 * - there is no way to re-read today's decision by date, so a decision is held
 *   for this session only; the flow above owns it, so switching tabs does not
 *   discard today's routine, and after a restart the user re-runs the check-in,
 *   which is what produces a decision
 * - there is no way to read the current weekly plan revision, so the revision
 *   sequence is likewise only known from a response this session created
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import type { Api } from '../../api/endpoints';
import {
  isApiError,
  messageForError,
  type ApiErrorKind,
} from '../../api/errors';
import type {
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  RoutineResponse,
  WeeklyPlanRevisionResponse,
  WeekResponse,
  WorkoutPlan,
} from '../../api/types';
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
import { sleepMinutesFromHours, type HomeCheckinDraft } from './homeModel';

type HomeData = {
  routine: RoutineResponse | null;
  context: DailyContextResponse | null;
  week: WeekResponse | null;
};

const FALLBACK_GOAL_CODE = 'GENERAL_FITNESS';
const FALLBACK_LOCATION_CODE = 'HOME';

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

export function HomeContainer({
  api,
  me,
  restToday,
  decision,
  onDecisionChange,
  planRevision,
  onPlanRevisionChange,
  onSessionStarted,
  onRestChosen,
  onTab,
  onOpenCalendar,
}: {
  api: Api;
  me: MeResponse;
  /** Owned by the flow above, so the choice survives leaving this screen. */
  restToday: boolean;
  /** Today's decision, held above so a tab switch does not discard it. */
  decision: DecisionResponse | null;
  onDecisionChange: (decision: DecisionResponse | null) => void;
  planRevision: WeeklyPlanRevisionResponse | null;
  onPlanRevisionChange: (revision: WeeklyPlanRevisionResponse | null) => void;
  onSessionStarted: (sessionId: string, plan: WorkoutPlan) => void;
  onRestChosen: () => void;
  onTab: (tab: TabId) => void;
  onOpenCalendar: () => void;
}) {
  const localDate = localDateString();
  const weekStart = weekStartString();

  const { state, reload, setData } = useAsyncData<HomeData>(
    async (signal) => {
      const routine = await optional(api.getCurrentRoutine(localDate, signal), [
        'notFound',
      ]);
      const context = await optional(api.getDailyContext(localDate, signal), [
        'notFound',
      ]);
      // The week card is secondary: a week the server cannot summarise must
      // not blank out today's routine, but an auth failure still surfaces.
      const week = await optional(api.getWeek(weekStart, signal), [
        'notFound',
        'validation',
        'conflict',
        'unavailable',
        'server',
      ]);
      return { routine, context, week };
    },
    [api, localDate, weekStart],
  );

  const [busy, setBusy] = useState<HomeBusyKind | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [staleContext, setStaleContext] = useState(false);
  const [lastDraft, setLastDraft] = useState<HomeCheckinDraft | null>(null);
  const inFlight = useRef(false);

  const data = state.status === 'ready' ? state.data : null;
  const routine = data?.routine ?? null;
  const context = data?.context ?? null;
  const week = data?.week ?? null;

  const profile = me.profile;
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
    // Mutations carry a fresh idempotency key per call, so overlapping runs
    // would create separate intents rather than retrying one.
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setBusy(kind);
    setActionError(null);
    setStaleContext(false);

    void action()
      .catch((error: unknown) => {
        setActionError(messageForError(error));
        setStaleContext(isApiError(error) && error.kind === 'stale');
      })
      .finally(() => {
        inFlight.current = false;
        setBusy(null);
      });
  }, []);

  const submitCheckin = useCallback(
    (draft: HomeCheckinDraft, refreshVersion = false) => {
      if (routine === null) {
        return;
      }
      setLastDraft(draft);

      run('checkin', async () => {
        const sleepMinutes = sleepMinutesFromHours(draft.sleepHours);
        if (sleepMinutes === undefined) {
          throw new Error('sleep hours out of range');
        }

        // A previous attempt lost the optimistic-lock race, so the retry has to
        // carry the version that is stored now rather than the stale one.
        let expectedVersion = context?.context_version;
        if (refreshVersion) {
          const current = await optional(api.getDailyContext(localDate), [
            'notFound',
          ]);
          expectedVersion = current?.context_version;
        }

        const profileDuration =
          profile?.default_requested_duration_minutes ??
          routine.days[0]?.requested_duration_minutes;

        const saved = await api.replaceDailyContext(
          localDate,
          {
            fatigue_level_code: draft.fatigueLevelCode,
            requested_duration_minutes: draft.requestedDurationMinutes,
            duration_adjustment_source_code:
              draft.requestedDurationMinutes === profileDuration
                ? 'PROFILE'
                : 'USER_OVERRIDE',
            location_code:
              context?.location_code ??
              profile?.preferred_location_code ??
              locationCodes[0] ??
              FALLBACK_LOCATION_CODE,
            sleep_minutes: sleepMinutes,
            discomforts: Object.entries(draft.discomforts).map(
              ([body_area_code, severity_code]) => ({
                body_area_code,
                severity_code,
              }),
            ),
            adverse_reaction_codes: draft.adverseReactionCodes,
          },
          expectedVersion,
        );

        const next = await api.createDecision({
          local_date: localDate,
          daily_context_id: saved.id,
          expected_context_version: saved.context_version,
        });

        setData({ routine, context: saved, week });
        onDecisionChange(next);
      });
    },
    [
      api,
      context,
      localDate,
      locationCodes,
      onDecisionChange,
      profile,
      routine,
      run,
      setData,
      week,
    ],
  );

  const createRoutine = useCallback(() => {
    run('checkin', async () => {
      await api.createRoutine({
        effective_from: localDate,
        goal_code: profile?.primary_goal_code ?? FALLBACK_GOAL_CODE,
      });
      reload();
    });
  }, [api, localDate, profile, reload, run]);

  const startWorkout = useCallback(() => {
    if (decision === null || decision.final_plan === null) {
      return;
    }
    const option = decision.options.find(
      (entry) => entry.option_code === 'FINAL_ROUTINE',
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
      (entry) => entry.option_code === 'REST',
    );
    if (option === undefined) {
      return;
    }

    run('starting', async () => {
      await api.selectOption(decision.decision_id, option.option_id);
      onRestChosen();
    });
  }, [api, decision, onRestChosen, run]);

  /**
   * The revision sequence is only knowable from a response this client
   * received, so the first revision of a session creates the week's initial
   * plan. If the plan already exists, the sequence cannot be recovered.
   */
  const revisionSequence = useCallback(async () => {
    if (planRevision !== null) {
      return planRevision.revision_sequence;
    }
    try {
      const initial = await api.createInitialWeeklyPlan(weekStart);
      onPlanRevisionChange(initial);
      return initial.revision_sequence;
    } catch (error: unknown) {
      if (isApiError(error) && error.code === 'INITIAL_PLAN_ALREADY_EXISTS') {
        throw new Error(
          '이번 주 계획 수정 요청은 이 기기에서 이번 주 계획을 만든 뒤에 사용할 수 있어요.',
        );
      }
      throw error;
    }
  }, [api, onPlanRevisionChange, planRevision, weekStart]);

  /**
   * A revised routine changes what today's plan should be built from, so the
   * server is asked for a fresh decision from the stored check-in.
   */
  const applyRevision = useCallback(
    async (revision: WeeklyPlanRevisionResponse) => {
      onPlanRevisionChange(revision);
      reload();

      if (revision.routine === null) {
        onDecisionChange(null);
        setActionError(
          '요청한 계획 수정을 적용하지 못했어요. 오늘 체크인을 다시 하면 현재 계획으로 추천을 받을 수 있어요.',
        );
        return;
      }
      if (context === null) {
        onDecisionChange(null);
        return;
      }

      const next = await api.createDecision({
        local_date: localDate,
        daily_context_id: context.id,
        expected_context_version: context.context_version,
      });
      onDecisionChange(next);
    },
    [api, context, localDate, onDecisionChange, onPlanRevisionChange, reload],
  );

  const requestAiRevision = useCallback(() => {
    run('revision', async () => {
      const sequence = await revisionSequence();
      const revision = await api.createPlanRevision(weekStart, {
        source_code: 'AI',
        expected_revision_sequence: sequence,
        user_edits: null,
      });
      await applyRevision(revision);
    });
  }, [api, applyRevision, revisionSequence, run, weekStart]);

  const submitUserEdits = useCallback(
    (edits: HomeUserEdits) => {
      run('revision', async () => {
        const sequence = await revisionSequence();
        const revision = await api.createPlanRevision(weekStart, {
          source_code: 'USER',
          expected_revision_sequence: sequence,
          user_edits: {
            routine_id: edits.routineId,
            location_code: edits.locationCode,
          },
        });
        await applyRevision(revision);
      });
    },
    [api, applyRevision, revisionSequence, run, weekStart],
  );

  const permissionDenied =
    state.status === 'error' &&
    isApiError(state.error) &&
    state.error.kind === 'permission';

  return (
    <HomeScreen
      nickname={profile?.nickname ?? '회원'}
      localDate={localDate}
      status={
        state.status === 'ready'
          ? 'ready'
          : state.status === 'error'
            ? 'error'
            : 'loading'
      }
      errorMessage={state.status === 'error' ? state.message : undefined}
      permissionDenied={permissionDenied}
      onRetry={permissionDenied ? undefined : reload}
      routine={routine}
      context={context}
      decision={decision}
      week={week}
      planRevision={planRevision}
      restToday={restToday}
      defaultDurationMinutes={profile?.default_requested_duration_minutes}
      locationCodes={locationCodes}
      busy={busy}
      actionError={actionError}
      staleContext={staleContext}
      onRetryCheckin={
        lastDraft === null ? undefined : () => submitCheckin(lastDraft, true)
      }
      onCreateRoutine={createRoutine}
      onSubmitCheckin={(draft) => submitCheckin(draft)}
      onStartWorkout={startWorkout}
      onChooseRest={chooseRest}
      onRequestAiRevision={requestAiRevision}
      onSubmitUserEdits={submitUserEdits}
      onNavigateTab={onTab}
      onOpenCalendar={onOpenCalendar}
    />
  );
}
