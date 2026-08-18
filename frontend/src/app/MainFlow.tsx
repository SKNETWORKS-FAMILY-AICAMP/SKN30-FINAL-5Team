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

import { useCallback, useState } from 'react';

import type { Api } from '../api/endpoints';
import type {
  DecisionResponse,
  MeResponse,
  WeeklyPlanRevisionResponse,
  WorkoutPlan,
} from '../api/types';
import { localDateString } from '../api/useAsync';
import type { TabId } from '../components/brand/BrandChrome';
import { CalendarStatusScreen } from '../features/calendar/CalendarStatusScreen';
import { HomeContainer } from '../features/home/HomeContainer';
import { MascotHouseScreen } from '../features/house/MascotHouseScreen';
import { AccountScreen } from '../features/profile/AccountScreen';
import {
  SessionScreen,
  type SessionOutcome,
} from '../features/workout/SessionScreen';
import { SessionResultScreen } from '../features/workout/SessionResultScreen';
import { WeeklyReportScreen } from '../features/weekly/WeeklyReportScreen';

type Step =
  | { name: 'home' }
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
  const [step, setStep] = useState<Step>({ name: 'home' });
  const [restDate, setRestDate] = useState<string | null>(null);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [planRevision, setPlanRevision] =
    useState<WeeklyPlanRevisionResponse | null>(null);

  const goHome = useCallback(() => setStep({ name: 'home' }), []);

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
    setStep({ name: 'home' });
  }, []);
  const restToday = restDate === localDateString();

  switch (step.name) {
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
          onDone={() => {
            // The session is over, so today's decision no longer describes what
            // the user can do next.
            setDecision(null);
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
        />
      );

    case 'weekly':
      return <WeeklyReportScreen api={api} onBack={goHome} />;

    case 'account':
      return (
        <AccountScreen
          api={api}
          me={me}
          onBack={goHome}
          onSignOut={onSignOut}
        />
      );

    case 'calendar':
      return <CalendarStatusScreen onBack={goHome} />;

    case 'home':
    default:
      return (
        <HomeContainer
          api={api}
          me={me}
          restToday={restToday}
          decision={decision}
          onDecisionChange={setDecision}
          planRevision={planRevision}
          onPlanRevisionChange={setPlanRevision}
          onSessionStarted={(sessionId, plan) =>
            setStep({ name: 'session', sessionId, plan })
          }
          onRestChosen={() => setRestDate(localDateString())}
          onTab={onTab}
          onOpenCalendar={() => setStep({ name: 'calendar' })}
        />
      );
  }
}
