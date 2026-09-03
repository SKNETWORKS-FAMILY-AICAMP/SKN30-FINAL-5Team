/**
 * The signed-in vertical slice, as an explicit screen state machine.
 *
 * Home is the entry point and the hub: today's state, the check-in, and the
 * server's final routine all happen there, so the only steps left here are the
 * ones that genuinely replace the screen — the workout itself, its result, and
 * the secondary tabs.
 *
 * `restToday`, today's decision and the week's plan revision are held here
 * rather than inside the home screen so that leaving home and coming back does
 * not discard them, and so that once the user chooses rest, every screen for
 * the rest of that day stops prompting them to work out.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { Api } from '../api/endpoints';
import type {
  DecisionResponse,
  MeResponse,
  WeeklyPlanRevisionResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
} from '../api/types';
import { localDateString, weekStartString } from '../api/useAsync';
import type { TabId } from '../components/brand/BrandChrome';
import { ExerciseCatalogScreen } from '../features/catalog/ExerciseCatalogScreen';
import { CalendarReportContainer } from '../features/home/CalendarReportContainer';
import { HomeContainer } from '../features/home/HomeContainer';
import { MyPageContainer } from '../features/home/MyPageContainer';
import { MascotHouseScreen } from '../features/house/MascotHouseScreen';
import type { SessionOutcome } from '../features/workout/SessionScreen';
import { SessionResultScreen } from '../features/workout/SessionResultScreen';
import { WorkoutScreen } from '../features/workout/WorkoutScreen';
import { WeeklyReportScreen } from '../features/weekly/WeeklyReportScreen';

type Step =
  | { name: 'home' }
  | { name: 'session'; sessionId: string; plan: WorkoutPlan }
  | { name: 'result'; sessionId: string; outcome: SessionOutcome }
  | { name: 'weekly'; weekStart: string }
  | { name: 'calendar-report' }
  | { name: 'account' }
  | { name: 'exercises' }
  | { name: 'house' };

export function MainFlow({
  api,
  me,
  onRefreshMe,
  onSignOut,
}: {
  api: Api;
  me: MeResponse;
  onRefreshMe: () => Promise<void>;
  onSignOut: () => void;
}) {
  const localDate = localDateString(new Date(), me.profile?.timezone);
  const [step, setStep] = useState<Step>({ name: 'home' });
  const [restChoice, setRestChoice] = useState<{
    localDate: string;
    pressureNotificationsAllowed: boolean;
  } | null>(null);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [planRevision, setPlanRevision] =
    useState<WeeklyPlanRevisionResponse | null>(null);
  const [recoveryNonce, setRecoveryNonce] = useState(0);
  const [todaySession, setTodaySession] =
    useState<WorkoutSessionDetailResponse | null>(null);
  const [resumableSessionId, setResumableSessionId] = useState<string | null>(
    null,
  );
  const [alternativeUsage, setAlternativeUsage] = useState({
    localDate,
    count: 0,
  });
  const decisionRef = useRef(decision);

  useEffect(() => {
    decisionRef.current = decision;
  }, [decision]);

  // A restart loses this flow's in-memory state, so recover today's stored
  // decision — and an unfinished session — from the server on entry and
  // explicit refresh.
  // Nothing here re-runs agents; both calls only read what a decision run
  // already persisted.
  useEffect(() => {
    if (step.name !== 'home') {
      return;
    }
    const controller = new AbortController();
    const decisionIdAtStart = decisionRef.current?.decision_id ?? null;
    const weekStart = weekStartString(new Date(), me.profile?.timezone);
    const latestPlanRevisionRequest = api.getLatestWeeklyPlanRevision
      ? api
          .getLatestWeeklyPlanRevision(weekStart, controller.signal)
          .catch(() => null)
      : Promise.resolve(null);

    void (async () => {
      const [stored, sessions, latestPlanRevision] = await Promise.all([
        api.getDecisionForDate(localDate, controller.signal).catch(() => null),
        api
          .listWorkoutSessions(
            { fromLocalDate: localDate, toLocalDate: localDate },
            controller.signal,
          )
          .catch(() => null),
        latestPlanRevisionRequest,
      ]);
      if (controller.signal.aborted) {
        return;
      }
      if (latestPlanRevision !== null) {
        setPlanRevision(latestPlanRevision);
      }
      const todaySessions = sessions?.items ?? [];
      const active = todaySessions.find(
        (item) =>
          item.status_code === 'PLANNED' || item.status_code === 'IN_PROGRESS',
      );
      const visibleSession =
        active ??
        todaySessions.find(
          (item) => item.status_code === 'STOPPED_FOR_SAFETY',
        ) ??
        todaySessions[0] ??
        null;
      const detail =
        visibleSession === null
          ? null
          : await api
              .getWorkoutSession(visibleSession.session_id, controller.signal)
              .catch(() => null);
      if (controller.signal.aborted) {
        return;
      }
      setTodaySession(detail);
      if (stored) {
        setDecision((current) =>
          (current?.decision_id ?? null) === decisionIdAtStart
            ? stored
            : current,
        );
      }
    })();

    return () => controller.abort();
  }, [api, localDate, me.profile?.timezone, recoveryNonce, step.name]);

  const goHome = useCallback(() => setStep({ name: 'home' }), []);
  const recoverHomeDecision = useCallback(
    () => setRecoveryNonce((value) => value + 1),
    [],
  );

  // One tab handler for every screen that shows the bar, so the destinations
  // stay identical wherever it appears.
  const onTab = useCallback(
    (tab: TabId) => {
      if (tab === 'house') {
        setStep({ name: 'house' });
        return;
      }
      if (tab === 'report') {
        setStep({ name: 'calendar-report' });
        return;
      }
      if (tab === 'my') {
        setStep({ name: 'account' });
        return;
      }
      recoverHomeDecision();
      setStep({ name: 'home' });
    },
    [recoverHomeDecision],
  );
  const routineStartLocalDate = me.profile
    ? localDateString(new Date(me.profile.created_at), me.profile.timezone)
    : undefined;
  const restToday = restChoice?.localDate === localDate;

  switch (step.name) {
    case 'session':
      return (
        <WorkoutScreen
          api={api}
          sessionId={step.sessionId}
          plan={step.plan}
          onOutcome={(outcome) => {
            setResumableSessionId(null);
            setStep({ name: 'result', sessionId: step.sessionId, outcome });
          }}
          onReturnHomeResumable={() => {
            setResumableSessionId(step.sessionId);
            setRecoveryNonce((value) => value + 1);
            goHome();
          }}
        />
      );

    case 'result':
      return (
        <SessionResultScreen
          api={api}
          sessionId={step.sessionId}
          outcome={step.outcome}
          onDone={() => {
            setRecoveryNonce((value) => value + 1);
            goHome();
          }}
        />
      );

    case 'house':
      return (
        <MascotHouseScreen
          api={api}
          nickname={me.profile?.nickname ?? '회원'}
          onNavigate={onTab}
          timeZone={me.profile?.timezone}
        />
      );

    case 'weekly':
      return (
        <WeeklyReportScreen
          api={api}
          onBack={() => setStep({ name: 'calendar-report' })}
          onNavigateTab={onTab}
          onPlanRevisionChange={setPlanRevision}
          planRevision={planRevision}
          timeZone={me.profile?.timezone}
          weekStart={step.weekStart}
        />
      );

    case 'calendar-report':
      return (
        <CalendarReportContainer
          api={api}
          timeZone={me.profile?.timezone}
          routineStartLocalDate={routineStartLocalDate}
          restLocalDate={restChoice?.localDate}
          onNavigateTab={onTab}
          onOpenWeeklyReport={(weekStart) =>
            setStep({ name: 'weekly', weekStart })
          }
        />
      );

    case 'account':
      return (
        <MyPageContainer
          api={api}
          me={me}
          onNavigateTab={onTab}
          onRefreshMe={onRefreshMe}
          onSignOut={onSignOut}
          onOpenExerciseCatalog={() => setStep({ name: 'exercises' })}
        />
      );

    case 'exercises':
      return (
        <ExerciseCatalogScreen
          api={api}
          onBack={() => setStep({ name: 'account' })}
        />
      );

    case 'home':
    default:
      return (
        <HomeContainer
          api={api}
          me={me}
          restToday={restToday}
          decision={decision}
          todaySession={todaySession}
          localSessionState={
            todaySession?.session_id === resumableSessionId
              ? 'STOPPED_RESUMABLE'
              : 'ACTIVE'
          }
          alternativeUsedCount={
            alternativeUsage.localDate === localDate
              ? alternativeUsage.count
              : 0
          }
          onAlternativeSuccess={() =>
            setAlternativeUsage((current) => ({
              localDate,
              count:
                current.localDate === localDate
                  ? Math.min(2, current.count + 1)
                  : 1,
            }))
          }
          onDecisionChange={setDecision}
          planRevision={planRevision}
          onSessionStarted={(sessionId, plan) => {
            setResumableSessionId(null);
            setStep({ name: 'session', sessionId, plan });
          }}
          onResumeWorkout={() => {
            if (todaySession !== null && decision?.final_plan) {
              setResumableSessionId(null);
              setStep({
                name: 'session',
                sessionId: todaySession.session_id,
                plan: decision.final_plan,
              });
            }
          }}
          onRestChosen={(pressureNotificationsAllowed) =>
            setRestChoice({ localDate, pressureNotificationsAllowed })
          }
          onCheckinDecisionSuccess={() => setRestChoice(null)}
          onRecoverDecision={recoverHomeDecision}
          onTab={onTab}
          onOpenCalendar={() => setStep({ name: 'calendar-report' })}
        />
      );
  }
}
