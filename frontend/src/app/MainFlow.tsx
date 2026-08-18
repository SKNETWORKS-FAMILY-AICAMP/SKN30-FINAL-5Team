/**
 * The signed-in vertical slice, as an explicit screen state machine.
 *
 * The journey is linear by design — the product shows one final recommended
 * routine per day — so an explicit `Step` union keeps the legal transitions
 * visible instead of spreading them across navigation callbacks.
 *
 * `restToday` is held here rather than re-read per screen so that once the user
 * chooses rest, every screen for the rest of that day stops prompting them to
 * work out.
 */

import { useCallback, useState } from 'react';

import type { Api } from '../api/endpoints';
import type {
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  RoutineResponse,
  WorkoutPlan,
} from '../api/types';
import { localDateString } from '../api/useAsync';
import type { TabId } from '../components/brand/BrandChrome';
import { CalendarStatusScreen } from '../features/calendar/CalendarStatusScreen';
import { MascotHouseScreen } from '../features/house/MascotHouseScreen';
import { CheckInScreen } from '../features/checkin/CheckInScreen';
import { DecisionScreen } from '../features/decision/DecisionScreen';
import { AccountScreen } from '../features/profile/AccountScreen';
import { TodayScreen } from '../features/today/TodayScreen';
import {
  SessionScreen,
  type SessionOutcome,
} from '../features/workout/SessionScreen';
import { SessionResultScreen } from '../features/workout/SessionResultScreen';
import { WeeklyReportScreen } from '../features/weekly/WeeklyReportScreen';

type Step =
  | { name: 'today' }
  | {
      name: 'checkIn';
      routine: RoutineResponse;
      /** Today's stored check-in, so a replacement can send its version. */
      context: DailyContextResponse | null;
    }
  | { name: 'decision'; decision: DecisionResponse }
  | { name: 'session'; sessionId: string; plan: WorkoutPlan }
  | { name: 'result'; sessionId: string; outcome: SessionOutcome }
  | { name: 'weekly' }
  | { name: 'account' }
  | { name: 'house' }
  | { name: 'calendar' };

export function MainFlow({
  api,
  me,
  onSignOut,
}: {
  api: Api;
  me: MeResponse;
  onSignOut: () => void;
}) {
  const [step, setStep] = useState<Step>({ name: 'today' });
  const [restDate, setRestDate] = useState<string | null>(null);

  const goToday = useCallback(() => setStep({ name: 'today' }), []);

  // One tab handler for every screen that shows the bar, so the destinations
  // stay identical wherever it appears.
  const onTab = useCallback((tab: TabId) => {
    if (tab === 'house') {
      setStep({ name: 'house' });
      return;
    }
    if (tab === 'report') {
      setStep({ name: 'weekly' });
      return;
    }
    if (tab === 'my') {
      setStep({ name: 'account' });
      return;
    }
    setStep({ name: 'today' });
  }, []);
  const restToday = restDate === localDateString();

  switch (step.name) {
    case 'checkIn':
      return (
        <CheckInScreen
          api={api}
          routine={step.routine}
          locationCode={
            me.profile?.available_location_codes[0] ??
            me.profile?.preferred_location_code ??
            'HOME'
          }
          existingContext={step.context}
          onDecided={(decision) => setStep({ name: 'decision', decision })}
          onCancel={goToday}
        />
      );

    case 'decision':
      return (
        <DecisionScreen
          api={api}
          decision={step.decision}
          onSessionStarted={(selection, decision) => {
            if (
              selection.workout_session === null ||
              decision.final_plan === null
            ) {
              goToday();
              return;
            }
            setStep({
              name: 'session',
              sessionId: selection.workout_session.session_id,
              plan: decision.final_plan,
            });
          }}
          onRestChosen={() => {
            setRestDate(localDateString());
            goToday();
          }}
          onBack={goToday}
        />
      );

    case 'session':
      return (
        <SessionScreen
          api={api}
          sessionId={step.sessionId}
          plan={step.plan}
          onOutcome={(outcome) =>
            setStep({ name: 'result', sessionId: step.sessionId, outcome })
          }
        />
      );

    case 'result':
      return (
        <SessionResultScreen
          api={api}
          sessionId={step.sessionId}
          outcome={step.outcome}
          onDone={goToday}
        />
      );

    case 'house':
      return (
        <MascotHouseScreen
          api={api}
          nickname={me.profile?.nickname ?? '회원'}
          onNavigate={onTab}
        />
      );

    case 'weekly':
      return <WeeklyReportScreen api={api} onBack={goToday} />;

    case 'account':
      return (
        <AccountScreen
          api={api}
          me={me}
          onBack={goToday}
          onSignOut={onSignOut}
        />
      );

    case 'calendar':
      return <CalendarStatusScreen onBack={goToday} />;

    case 'today':
    default:
      return (
        <TodayScreen
          api={api}
          nickname={me.profile?.nickname ?? '회원'}
          restToday={restToday}
          onCheckIn={(routine, context) =>
            setStep({ name: 'checkIn', routine, context })
          }
          onTab={onTab}
          onOpenCalendar={() => setStep({ name: 'calendar' })}
        />
      );
  }
}
