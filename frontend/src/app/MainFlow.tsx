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
import { messageForError } from '../api/errors';
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
import { HomeContainer } from '../features/home/HomeContainer';
import { MyPageContainer } from '../features/home/MyPageContainer';
import {
  NotificationSheet,
  type NotificationLoadStatus,
} from '../features/home/NotificationSheet';
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
  const openNotifications = useCallback(() => {
    setNotificationSheetOpen(true);
    void refreshNotifications();
  }, [refreshNotifications]);
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
        <>
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
            hasUnreadNotification={
              (notificationResponse?.unread_count ?? 0) > 0
            }
            notificationToastVisible={notificationToastVisible}
            onNotifications={openNotifications}
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
          <NotificationSheet
            errorMessage={notificationError}
            onClose={() => setNotificationSheetOpen(false)}
            onRetry={() => void refreshNotifications()}
            onSelect={selectNotification}
            pendingNotificationId={pendingNotificationId}
            response={notificationResponse}
            status={notificationStatus}
            visible={notificationSheetOpen}
          />
        </>
      );
  }
}
