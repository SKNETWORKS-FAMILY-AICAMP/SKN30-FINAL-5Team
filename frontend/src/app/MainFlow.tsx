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
import { isApiError, messageForError } from '../api/errors';
import type {
  DecisionResponse,
  MeResponse,
  NotificationListResponse,
  NotificationResponse,
  WeeklyPlanRevisionResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
} from '../api/types';
import { localDateString, weekStartString } from '../api/useAsync';
import type { TabId } from '../components/brand/BrandChrome';
import { ExerciseCatalogScreen } from '../features/catalog/ExerciseCatalogScreen';
import { CalendarReportContainer } from '../features/home/CalendarReportContainer';
import {
  HomeContainer,
  type HomeRecoveryState,
} from '../features/home/HomeContainer';
import { MyPageContainer } from '../features/home/MyPageContainer';
import {
  NotificationSheet,
  type NotificationLoadStatus,
} from '../features/home/NotificationSheet';
import { MascotHouseScreen } from '../features/house/MascotHouseScreen';
import { RewardsScreen } from '../features/rewards/RewardsScreen';
import type { SessionOutcome } from '../features/workout/SessionScreen';
import {
  isRestOutcome,
  SessionResultScreen,
} from '../features/workout/SessionResultScreen';
import { WorkoutScreen } from '../features/workout/WorkoutScreen';
import { WeeklyReportScreen } from '../features/weekly/WeeklyReportScreen';

type Step =
  | { name: 'home' }
  | {
      name: 'session';
      sessionId: string;
      plan: WorkoutPlan;
      locationCode?: string;
    }
  | { name: 'result'; sessionId: string; outcome: SessionOutcome }
  | { name: 'weekly'; weekStart: string }
  | { name: 'calendar-report' }
  | { name: 'account' }
  | { name: 'exercises' }
  | { name: 'rewards' }
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
  const [restLocalDate, setRestLocalDate] = useState<string | null>(null);
  const [homeSafetyGuidance, setHomeSafetyGuidance] = useState<{
    localDate: string;
    message: string;
  } | null>(null);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [planRevision, setPlanRevision] =
    useState<WeeklyPlanRevisionResponse | null>(null);
  const [recoveryNonce, setRecoveryNonce] = useState(0);
  const [todaySession, setTodaySession] =
    useState<WorkoutSessionDetailResponse | null>(null);
  const [homeRecoveryState, setHomeRecoveryState] = useState<HomeRecoveryState>(
    { status: 'loading' },
  );
  const [alternativeUsage, setAlternativeUsage] = useState({
    localDate,
    count: 0,
  });
  const [notificationResponse, setNotificationResponse] =
    useState<NotificationListResponse | null>(null);
  const [notificationStatus, setNotificationStatus] =
    useState<NotificationLoadStatus>('idle');
  const [notificationError, setNotificationError] = useState<string | null>(
    null,
  );
  const [notificationSheetOpen, setNotificationSheetOpen] = useState(false);
  const [pendingNotificationId, setPendingNotificationId] = useState<
    string | null
  >(null);
  const [notificationToastVisible, setNotificationToastVisible] =
    useState(false);
  const knownNotificationIds = useRef<Set<string> | null>(null);
  const notificationRequestSequence = useRef(0);
  const decisionRef = useRef(decision);

  useEffect(() => {
    decisionRef.current = decision;
  }, [decision]);

  const refreshNotifications = useCallback(
    async (signal?: AbortSignal): Promise<boolean> => {
      if (signal?.aborted) {
        return false;
      }
      const requestSequence = notificationRequestSequence.current + 1;
      notificationRequestSequence.current = requestSequence;
      setNotificationStatus('loading');
      setNotificationError(null);
      try {
        const next = await api.listNotifications(signal);
        if (
          signal?.aborted ||
          requestSequence !== notificationRequestSequence.current
        ) {
          return false;
        }

        const previousIds = knownNotificationIds.current;
        const hasNewUnread =
          previousIds !== null &&
          next.items.some(
            (item) => !item.is_read && !previousIds.has(item.notification_id),
          );
        knownNotificationIds.current = new Set(
          next.items.map((item) => item.notification_id),
        );
        setNotificationResponse(next);
        setNotificationStatus('ready');
        if (hasNewUnread) {
          setNotificationToastVisible(true);
        }
        return true;
      } catch (error: unknown) {
        if (
          signal?.aborted ||
          (error instanceof Error && error.name === 'AbortError') ||
          requestSequence !== notificationRequestSequence.current
        ) {
          return false;
        }
        setNotificationStatus('error');
        setNotificationError(messageForError(error));
        return false;
      }
    },
    [api],
  );

  useEffect(() => {
    if (step.name !== 'home') {
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(
      () => void refreshNotifications(controller.signal),
      0,
    );
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [refreshNotifications, step.name]);

  useEffect(() => {
    if (!notificationToastVisible) {
      return;
    }
    const timeout = setTimeout(() => setNotificationToastVisible(false), 2_500);
    return () => clearTimeout(timeout);
  }, [notificationToastVisible]);

  // A restart loses this flow's in-memory state, so recover today's decision
  // and its plan-scoped session from one consistent server snapshot. This
  // read never re-runs agents or starts a workout session.
  useEffect(() => {
    if (step.name !== 'home') {
      return;
    }
    const controller = new AbortController();
    const loadingTimeout = setTimeout(() => {
      if (!controller.signal.aborted) {
        setHomeRecoveryState({ status: 'loading' });
      }
    }, 0);
    const decisionIdAtStart = decisionRef.current?.decision_id ?? null;
    const weekStart = weekStartString(new Date(), me.profile?.timezone);
    const latestPlanRevisionRequest = api.getLatestWeeklyPlanRevision
      ? api
          .getLatestWeeklyPlanRevision(weekStart, controller.signal)
          .catch(() => null)
      : Promise.resolve(null);

    void (async () => {
      const [homeResult, latestPlanRevision] = await Promise.all([
        api
          .getHomeState(localDate, controller.signal)
          .then((data) => ({ status: 'success' as const, data }))
          .catch((error: unknown) => ({ status: 'error' as const, error })),
        latestPlanRevisionRequest,
      ]);
      if (controller.signal.aborted) {
        return;
      }
      clearTimeout(loadingTimeout);
      if (latestPlanRevision !== null) {
        setPlanRevision(latestPlanRevision);
      }
      if (homeResult.status === 'error') {
        setHomeRecoveryState({
          status: 'error',
          message: messageForError(homeResult.error),
          permissionDenied:
            isApiError(homeResult.error) &&
            homeResult.error.kind === 'permission',
        });
        return;
      }
      setTodaySession(homeResult.data.workout_session);
      setDecision((current) =>
        (current?.decision_id ?? null) === decisionIdAtStart
          ? homeResult.data.decision
          : current,
      );
      setHomeRecoveryState({ status: 'ready' });
    })();

    return () => {
      clearTimeout(loadingTimeout);
      controller.abort();
    };
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
  const toggleNotifications = useCallback(() => {
    if (notificationSheetOpen) {
      setNotificationSheetOpen(false);
      return;
    }
    setNotificationSheetOpen(true);
    void refreshNotifications();
  }, [notificationSheetOpen, refreshNotifications]);
  const selectNotification = useCallback(
    (notification: NotificationResponse) => {
      if (pendingNotificationId !== null) {
        return;
      }
      setPendingNotificationId(notification.notification_id);
      setNotificationError(null);
      void (async () => {
        try {
          await api.markNotificationRead(notification.notification_id);
          await refreshNotifications();
          if (notification.action_type === 'OPEN_KIKKI_HOME') {
            setNotificationSheetOpen(false);
            onTab('house');
          } else if (notification.action_type === 'CLAIM_DAILY_REWARD') {
            setNotificationSheetOpen(false);
            setStep({ name: 'rewards' });
          }
        } catch (error: unknown) {
          setNotificationStatus('error');
          setNotificationError(messageForError(error));
        } finally {
          setPendingNotificationId(null);
        }
      })();
    },
    [api, onTab, pendingNotificationId, refreshNotifications],
  );
  const routineStartLocalDate = me.profile
    ? localDateString(new Date(me.profile.created_at), me.profile.timezone)
    : undefined;
  const restToday =
    restLocalDate === localDate ||
    todaySession?.status_code === 'NOT_COMPLETED';

  switch (step.name) {
    case 'session':
      return (
        <WorkoutScreen
          api={api}
          exerciseGuideContext={{ locationCode: step.locationCode ?? null }}
          locationCode={step.locationCode}
          sessionId={step.sessionId}
          plan={step.plan}
          onOutcome={(outcome) => {
            if (outcome.kind === 'safetyStop') {
              // The day is rest from here, and Home says so -- but the user is
              // still asked how the session went before leaving, which is the
              // only place that question gets asked for a safety stop.
              setRestLocalDate(localDate);
              setHomeSafetyGuidance({
                localDate,
                message: outcome.event.guidance,
              });
            } else if (isRestOutcome(outcome)) {
              setRestLocalDate(localDate);
              setHomeSafetyGuidance(null);
              setRecoveryNonce((value) => value + 1);
              goHome();
              return;
            }
            setStep({ name: 'result', sessionId: step.sessionId, outcome });
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
          accountId={me.user_id}
          api={api}
          nickname={me.profile?.nickname ?? '회원'}
          onNavigate={onTab}
          timeZone={me.profile?.timezone}
        />
      );

    case 'rewards':
      return (
        <RewardsScreen
          api={api}
          backAccessibilityLabel="홈으로 돌아가기"
          onBack={goHome}
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
        />
      );

    case 'exercises':
      return <ExerciseCatalogScreen api={api} onBack={goHome} />;

    case 'home':
    default:
      return (
        <>
          <HomeContainer
            api={api}
            me={me}
            recoveryState={homeRecoveryState}
            restToday={restToday}
            safetyGuidance={
              homeSafetyGuidance?.localDate === localDate
                ? homeSafetyGuidance.message
                : undefined
            }
            decision={decision}
            todaySession={todaySession}
            alternativeUsedCount={
              alternativeUsage.localDate === localDate
                ? alternativeUsage.count
                : 0
            }
            hasUnreadNotification={
              (notificationResponse?.unread_count ?? 0) > 0
            }
            notificationPanel={
              <NotificationSheet
                errorMessage={notificationError}
                onRetry={() => void refreshNotifications()}
                onSelect={selectNotification}
                pendingNotificationId={pendingNotificationId}
                response={notificationResponse}
                status={notificationStatus}
                visible={notificationSheetOpen}
              />
            }
            onDismissNotificationPanel={
              notificationSheetOpen
                ? () => setNotificationSheetOpen(false)
                : undefined
            }
            notificationToastVisible={notificationToastVisible}
            onNotifications={toggleNotifications}
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
            onSessionStarted={(sessionId, plan, locationCode) => {
              setStep({ name: 'session', sessionId, plan, locationCode });
            }}
            onResumeWorkout={(locationCode) => {
              if (todaySession !== null && decision?.final_plan) {
                setStep({
                  name: 'session',
                  sessionId: todaySession.session_id,
                  plan: decision.final_plan,
                  locationCode,
                });
              }
            }}
            onCheckinDecisionSuccess={() => {
              setRestLocalDate(null);
              setTodaySession(null);
              setHomeSafetyGuidance(null);
            }}
            onRecoverDecision={recoverHomeDecision}
            onTab={onTab}
            onOpenCalendar={() => setStep({ name: 'calendar-report' })}
            onOpenExerciseCatalog={() => setStep({ name: 'exercises' })}
          />
        </>
      );
  }
}
