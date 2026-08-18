/**
 * Invariant coverage for the API-backed demo screens.
 *
 * These use a stub API rather than the real backend, so they verify what the
 * *client* does with a given server answer: that it renders the server's
 * decision faithfully and never substitutes its own.
 */

import { jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { Image } from 'react-native';

import { ApiClient, createIdempotencyKey } from '../src/api/client';
import { ApiError } from '../src/api/errors';
import { createApi, type Api } from '../src/api/endpoints';
import type {
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  RoutineResponse,
  SessionItem,
  WeekResponse,
  WorkoutPlan,
} from '../src/api/types';
import { resolveEnvConfig } from '../src/config/env';
import { MascotStage } from '../src/components/brand/BrandChrome';
import { CalendarStatusScreen } from '../src/features/calendar/CalendarStatusScreen';
import { HomeContainer } from '../src/features/home/HomeContainer';
import { MascotHouseScreen } from '../src/features/house/MascotHouseScreen';
import { OnboardingScreen } from '../src/features/onboarding/OnboardingScreen';
import { SessionCarousel } from '../src/features/workout/SessionCarousel';
import { SessionScreen } from '../src/features/workout/SessionScreen';

function plan(itemCount = 2): WorkoutPlan {
  return {
    plan_id: 'plan-1',
    action_code: 'KEEP',
    training_type_code: 'STRENGTH',
    body_focus_code: 'FULL_BODY',
    requested_duration_minutes: 30,
    estimated_duration_seconds: 1800,
    estimated_calories_burned: null,
    setup_seconds: 0,
    warmup_seconds: 120,
    cooldown_seconds: 60,
    items: Array.from({ length: itemCount }, (_, index) => ({
      plan_item_id: `item-${index + 1}`,
      exercise_id: `exercise-${index + 1}`,
      exercise_name: `운동 ${index + 1}`,
      sequence: index + 1,
      tier_code: 'CORE',
      sets: 3,
      reps: null,
      work_seconds: 60,
      rest_seconds: 25,
      transition_seconds: 10,
      estimated_item_seconds: 240,
      instruction_available: true,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    })),
  };
}

function decision(overrides: Partial<DecisionResponse> = {}): DecisionResponse {
  return {
    decision_id: 'decision-1',
    local_date: '2026-08-17',
    status_code: 'COMPLETED',
    safety_status_code: 'PASS',
    action_code: 'KEEP',
    requested_duration_minutes: 30,
    duration_adjustment_source_code: 'PROFILE',
    final_plan: plan(),
    options: [
      {
        option_id: 'option-routine',
        option_code: 'FINAL_ROUTINE',
        action_code: 'KEEP',
        plan_id: 'plan-1',
        selectable: true,
        blocked_reason_code: null,
      },
      {
        option_id: 'option-rest',
        option_code: 'REST',
        action_code: 'REST',
        plan_id: null,
        selectable: true,
        blocked_reason_code: null,
      },
    ],
    reason_codes: [],
    summary: '오늘은 계획대로 진행해요.',
    guidance: null,
    public_agent_summaries: null,
    safety_summary: null,
    created_at: '2026-08-17T01:00:00+09:00',
    ...overrides,
  };
}

function routine(): RoutineResponse {
  return {
    id: 'routine-1',
    version: 1,
    goal_code: 'GENERAL_FITNESS',
    status_code: 'ACTIVE',
    effective_from: '2026-08-17',
    catalog_version: 'demo-synthetic-v1',
    created_at: '2026-08-17T00:00:00+09:00',
    days: [
      {
        id: 'day-1',
        sequence: 1,
        title: '루틴 1',
        training_type_code: 'STRENGTH',
        body_focus_code: 'FULL_BODY',
        requested_duration_minutes: 30,
        estimated_duration_seconds: 1800,
        estimated_calories_burned: null,
        items: [],
      },
    ],
  };
}

function dailyContext(): DailyContextResponse {
  return {
    id: 'context-1',
    local_date: '2026-08-17',
    context_version: 1,
    fatigue_level_code: 'MODERATE',
    requested_duration_minutes: 30,
    duration_adjustment_source_code: 'PROFILE',
    location_code: 'HOME',
    sleep_minutes: 420,
    discomforts: [],
    adverse_reaction_codes: [],
    created_at: '2026-08-17T00:00:00+09:00',
    updated_at: '2026-08-17T00:00:00+09:00',
  };
}

function week(): WeekResponse {
  return {
    week_id: 'week-1',
    week_start: '2026-08-17',
    week_end: '2026-08-23',
    timezone: 'Asia/Seoul',
    target_workout_count: 4,
    plan_origin_code: 'INITIAL',
    cold_start_applied: true,
    status_code: 'OPEN',
    closed_at: null,
    report_id: null,
    report_status_code: null,
  };
}

function me(): MeResponse {
  return {
    user_id: 'user-1',
    status_code: 'ACTIVE',
    onboarding_completed: true,
    premium_status_code: 'TRIAL',
    ai_trial_started_at: '2026-08-01T00:00:00+09:00',
    ai_trial_ends_at: '2026-08-31T00:00:00+09:00',
    profile: {
      nickname: '데모',
      age: null,
      primary_goal_code: 'GENERAL_FITNESS',
      experience_level_code: 'BEGINNER',
      timezone: 'Asia/Seoul',
      preferred_location_code: 'HOME',
      available_location_codes: ['HOME'],
      default_requested_duration_minutes: 30,
      desired_weekly_workout_count: 4,
      coaching_style_code: 'FRIENDLY',
      equipment_codes: [],
      attention_area_codes: [],
      preferred_exercise_type_codes: [],
      profile_version: 1,
      created_at: '2026-08-01T00:00:00+09:00',
      updated_at: '2026-08-01T00:00:00+09:00',
    },
  };
}

function stubApi(overrides: Partial<Api> = {}): Api {
  return {
    getMe: jest.fn(),
    submitOnboarding: jest.fn(),
    createRoutine: jest.fn(),
    getCurrentRoutine: jest.fn(),
    getExercise: jest.fn(),
    getDailyContext: jest.fn(),
    replaceDailyContext: jest.fn(),
    createDecision: jest.fn(),
    getDecision: jest.fn(),
    selectOption: jest.fn(),
    startSession: jest.fn(),
    updateSessionItem: jest.fn(),
    recordTimerEvent: jest.fn(),
    reportSafetyEvent: jest.fn(),
    finishSession: jest.fn(),
    markNotCompleted: jest.fn(),
    submitFeedback: jest.fn(),
    getWeek: jest.fn(),
    createInitialWeeklyPlan: jest.fn(),
    createPlanRevision: jest.fn(),
    createWeeklyReport: jest.fn(),
    getWeeklyReport: jest.fn(),
    acknowledgeWeeklyReport: jest.fn(),
    requestAccountDeletion: jest.fn(),
    ...overrides,
  } as unknown as Api;
}

const notFound = () =>
  Promise.reject(
    new ApiError({
      kind: 'notFound',
      code: 'ROUTINE_NOT_FOUND',
      status: 404,
      message: '없어요',
    }),
  );

describe('environment configuration', () => {
  it('fails closed when required values are missing', () => {
    const config = resolveEnvConfig({});
    expect(config.status).toBe('incomplete');
    if (config.status === 'incomplete') {
      expect(config.issues.map((issue) => issue.key)).toContain(
        'EXPO_PUBLIC_API_BASE_URL',
      );
      expect(config.issues.map((issue) => issue.key)).toContain(
        'EXPO_PUBLIC_FIREBASE_API_KEY',
      );
    }
  });

  it('accepts a complete configuration and trims the base URL', () => {
    const config = resolveEnvConfig({
      EXPO_PUBLIC_API_BASE_URL: 'http://10.0.2.2:8000/',
      EXPO_PUBLIC_FIREBASE_API_KEY: 'key',
      EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN: 'demo.firebaseapp.com',
      EXPO_PUBLIC_FIREBASE_PROJECT_ID: 'demo',
      EXPO_PUBLIC_FIREBASE_APP_ID: 'app',
    });
    expect(config.status).toBe('ready');
    if (config.status === 'ready') {
      expect(config.apiBaseUrl).toBe('http://10.0.2.2:8000');
    }
  });
});

describe('idempotency keys', () => {
  it('produces distinct v4 identifiers', () => {
    const first = createIdempotencyKey();
    const second = createIdempotencyKey();
    expect(first).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(first).not.toBe(second);
  });
});

describe('HomeContainer', () => {
  function homeApi(overrides: Partial<Api> = {}): Api {
    return stubApi({
      getCurrentRoutine: jest.fn(async () => routine()),
      getDailyContext: jest.fn(notFound),
      getWeek: jest.fn(async () => week()),
      ...overrides,
    } as unknown as Partial<Api>);
  }

  function renderHome(api: Api, overrides: Record<string, unknown> = {}) {
    const base = {
      api,
      me: me(),
      restToday: false,
      decision: null,
      onDecisionChange: jest.fn(),
      planRevision: null,
      onPlanRevisionChange: jest.fn(),
      onSessionStarted: jest.fn(),
      onRestChosen: jest.fn(),
      onTab: jest.fn(),
      onOpenCalendar: jest.fn(),
    };
    return render(<HomeContainer {...base} {...overrides} />);
  }

  it("shows a loading state while today's data is pending", () => {
    const pending = new Promise<never>(() => undefined);
    renderHome(
      homeApi({
        getCurrentRoutine: jest.fn(() => pending),
        getDailyContext: jest.fn(() => pending),
        getWeek: jest.fn(() => pending),
      } as unknown as Partial<Api>),
    );

    expect(screen.getByText('오늘 상태를 불러오는 중이에요')).toBeTruthy();
  });

  it('offers one check-in entry point before the check-in', async () => {
    renderHome(homeApi());

    expect(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeTruthy();
    expect(screen.getByText('아직 오늘의 운동이 없어요')).toBeTruthy();
  });

  it('offers routine creation when none exists yet', async () => {
    renderHome(
      homeApi({
        getCurrentRoutine: jest.fn(notFound),
      } as unknown as Partial<Api>),
    );

    expect(await screen.findByText('기본 루틴이 아직 없어요')).toBeTruthy();
  });

  it('writes the check-in and renders the decision the server returned', async () => {
    const replaceDailyContext = jest.fn(async () => dailyContext());
    const createDecision = jest.fn(async () => decision());
    const onDecisionChange = jest.fn();

    renderHome(
      homeApi({
        replaceDailyContext,
        createDecision,
      } as unknown as Partial<Api>),
      { onDecisionChange },
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    await waitFor(() => expect(createDecision).toHaveBeenCalled());
    expect(replaceDailyContext).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        fatigue_level_code: 'MODERATE',
        discomforts: [],
        adverse_reaction_codes: [],
      }),
      undefined,
    );
    // The decision is owned above this screen, so a tab switch cannot lose it.
    expect(onDecisionChange).toHaveBeenCalledWith(
      expect.objectContaining({ decision_id: 'decision-1' }),
    );
  });

  it('leaves an unset optional value unset rather than inferring it', async () => {
    const replaceDailyContext = jest.fn(async () => dailyContext());
    renderHome(
      homeApi({
        replaceDailyContext,
        createDecision: jest.fn(async () => decision()),
      } as unknown as Partial<Api>),
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    await waitFor(() => expect(replaceDailyContext).toHaveBeenCalled());
    expect(replaceDailyContext).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ sleep_minutes: null }),
      undefined,
    );
  });

  it('reports a rest selection without creating a session', async () => {
    const selectOption = jest.fn(async () => ({
      selection_id: 'sel-1',
      decision_id: 'decision-1',
      option_id: 'option-rest',
      selected_action_code: 'REST' as const,
      workout_session: null,
      selected_at: '2026-08-17T02:00:00+09:00',
      pressure_notifications_allowed: false,
    }));
    const onRestChosen = jest.fn();
    const onSessionStarted = jest.fn();

    renderHome(homeApi({ selectOption } as unknown as Partial<Api>), {
      decision: decision(),
      onRestChosen,
      onSessionStarted,
    });

    fireEvent.press(await screen.findByText('오늘은 쉬기'));

    await waitFor(() => expect(onRestChosen).toHaveBeenCalled());
    expect(selectOption).toHaveBeenCalledWith('decision-1', 'option-rest');
    expect(onSessionStarted).not.toHaveBeenCalled();
  });

  it('hands the started session to the flow above', async () => {
    const selectOption = jest.fn(async () => ({
      selection_id: 'sel-2',
      decision_id: 'decision-1',
      option_id: 'option-routine',
      selected_action_code: 'KEEP' as const,
      workout_session: {
        session_id: 'session-1',
        status_code: 'PLANNED' as const,
      },
      selected_at: '2026-08-17T02:00:00+09:00',
      pressure_notifications_allowed: null,
    }));
    const onSessionStarted = jest.fn();

    renderHome(homeApi({ selectOption } as unknown as Partial<Api>), {
      decision: decision(),
      onSessionStarted,
    });

    fireEvent.press(await screen.findByText('운동 시작하기  ›'));

    await waitFor(() =>
      expect(onSessionStarted).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ plan_id: 'plan-1' }),
      ),
    );
  });

  it('shows no workout prompt on a day the user chose rest', async () => {
    renderHome(homeApi(), { restToday: true, decision: decision() });

    expect(await screen.findByText('오늘은 휴식하기로 했어요')).toBeTruthy();
    expect(screen.queryByText('오늘 루틴 체크인')).toBeNull();
    expect(screen.queryByText('운동 시작하기  ›')).toBeNull();
  });

  it('surfaces a retryable error state', async () => {
    renderHome(
      homeApi({
        getCurrentRoutine: jest.fn(async () => {
          throw new ApiError({
            kind: 'network',
            code: 'NETWORK_UNAVAILABLE',
            status: 0,
            message: '서버에 연결하지 못했습니다.',
          });
        }),
      } as unknown as Partial<Api>),
    );

    expect(await screen.findByText('서버에 연결하지 못했습니다.')).toBeTruthy();
    expect(screen.getByText('다시 시도')).toBeTruthy();
  });

  it('shows a non-retryable permission-denied state', async () => {
    renderHome(
      homeApi({
        getCurrentRoutine: jest.fn(async () => {
          throw new ApiError({
            kind: 'permission',
            code: 'ACCOUNT_DISABLED',
            status: 403,
            message: '접근할 수 없습니다.',
          });
        }),
      } as unknown as Partial<Api>),
    );

    expect(
      await screen.findByText('오늘의 운동 정보에 접근할 권한이 없어요.'),
    ).toBeTruthy();
    expect(screen.queryByText('다시 시도')).toBeNull();
  });
});

describe('SessionScreen', () => {
  const startResponse = (itemCount: number) => ({
    session_id: 'session-1',
    status_code: 'IN_PROGRESS' as const,
    started_at: '2026-08-17T10:00:00+09:00',
    items: Array.from({ length: itemCount }, (_, index) => ({
      plan_item_id: `item-${index + 1}`,
      status_code: 'PENDING' as const,
      completed_at: null,
    })),
    current_plan_item_id: 'item-1',
  });

  it('keeps finish disabled until a block is explicitly completed', async () => {
    render(
      <SessionScreen
        api={stubApi({
          startSession: jest.fn(async () => startResponse(2)),
        } as unknown as Partial<Api>)}
        sessionId="session-1"
        plan={plan(2)}
        onOutcome={jest.fn()}
      />,
    );

    const finish = await screen.findByRole('button', { name: '운동 마치기' });
    expect(finish.props.accessibilityState.disabled).toBe(true);
    expect(screen.getByText(/완료한 블록이 하나도 없어요/)).toBeTruthy();
  });

  it('does not complete anything from elapsed time alone', async () => {
    jest.useFakeTimers();
    const updateSessionItem = jest.fn();
    const finishSession = jest.fn();

    render(
      <SessionScreen
        api={stubApi({
          startSession: jest.fn(async () => startResponse(2)),
          updateSessionItem,
          finishSession,
        } as unknown as Partial<Api>)}
        sessionId="session-1"
        plan={plan(2)}
        onOutcome={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.getByText('0 / 2 블록 완료')).toBeTruthy(),
    );
    act(() => {
      jest.advanceTimersByTime(60_000);
    });

    expect(updateSessionItem).not.toHaveBeenCalled();
    expect(finishSession).not.toHaveBeenCalled();
    expect(screen.getByText('0 / 2 블록 완료')).toBeTruthy();
    jest.useRealTimers();
  });

  it('takes block progress from the server response', async () => {
    const updateSessionItem = jest.fn(async () => ({
      session_id: 'session-1',
      status_code: 'IN_PROGRESS' as const,
      item: {
        plan_item_id: 'item-1',
        status_code: 'COMPLETED' as const,
        completed_at: '2026-08-17T10:05:00+09:00',
      },
      completed_item_count: 1,
      total_item_count: 2,
      next_pending_plan_item_id: 'item-2',
    }));

    render(
      <SessionScreen
        api={stubApi({
          startSession: jest.fn(async () => startResponse(2)),
          updateSessionItem,
        } as unknown as Partial<Api>)}
        sessionId="session-1"
        plan={plan(2)}
        onOutcome={jest.fn()}
      />,
    );

    const checks = await screen.findAllByText('완료 체크');
    fireEvent.press(checks[0]!);

    await waitFor(() =>
      expect(screen.getByText('1 / 2 블록 완료')).toBeTruthy(),
    );
    expect(updateSessionItem).toHaveBeenCalledWith(
      'session-1',
      'item-1',
      'COMPLETED',
      expect.any(String),
    );
  });

  it('ends the session when the server reports a safety stop', async () => {
    const onOutcome = jest.fn();
    const reportSafetyEvent = jest.fn(async () => ({
      event_id: 'event-1',
      instruction_code: 'STOP_SESSION' as const,
      resulting_action_code: 'REST' as const,
      session_status_code: 'STOPPED_FOR_SAFETY' as const,
      guidance_code: 'SEVERE_OR_ACUTE_STOP',
      guidance: '오늘 운동은 진행하지 않는 것이 좋습니다.',
      pressure_notifications_allowed: false,
    }));

    render(
      <SessionScreen
        api={stubApi({
          startSession: jest.fn(async () => startResponse(2)),
          reportSafetyEvent,
        } as unknown as Partial<Api>)}
        sessionId="session-1"
        plan={plan(2)}
        onOutcome={onOutcome}
      />,
    );

    fireEvent.press(await screen.findByText('통증·이상 반응 알리기'));
    fireEvent.press(screen.getByText('무릎'));
    fireEvent.press(screen.getByText('알리기'));

    await waitFor(() =>
      expect(onOutcome).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'safetyStop' }),
      ),
    );
  });
});

describe('CalendarStatusScreen', () => {
  it('states the integration is not available and offers no connect action', () => {
    render(<CalendarStatusScreen onBack={jest.fn()} />);

    expect(screen.getByText('연동 준비 중')).toBeTruthy();
    expect(screen.getByText('아직 연결할 수 없어요')).toBeTruthy();
    expect(screen.queryByText('캘린더 연결하기')).toBeNull();
    expect(screen.queryByRole('button', { name: /연결/ })).toBeNull();
  });

  it('restates that calendar data cannot change official completion', () => {
    render(<CalendarStatusScreen onBack={jest.fn()} />);
    expect(screen.getByText('운동 완료 기준은 그대로예요')).toBeTruthy();
  });
});

describe('MeResponse handling', () => {
  it('never carries a birthdate field', () => {
    const me: MeResponse = {
      user_id: 'user-1',
      status_code: 'ACTIVE',
      onboarding_completed: true,
      premium_status_code: 'NOT_AVAILABLE',
      ai_trial_started_at: '2026-08-17T00:00:00+09:00',
      ai_trial_ends_at: '2026-08-31T00:00:00+09:00',
      profile: {
        nickname: '데모',
        age: 29,
        primary_goal_code: 'GENERAL_FITNESS',
        experience_level_code: 'BEGINNER',
        timezone: 'Asia/Seoul',
        preferred_location_code: 'HOME',
        available_location_codes: ['HOME'],
        default_requested_duration_minutes: 30,
        desired_weekly_workout_count: 3,
        coaching_style_code: 'SUPPORTIVE',
        equipment_codes: ['BODYWEIGHT'],
        attention_area_codes: [],
        preferred_exercise_type_codes: ['STRENGTH'],
        profile_version: 1,
        created_at: '2026-08-17T00:00:00+09:00',
        updated_at: '2026-08-17T00:00:00+09:00',
      },
    };

    expect(Object.keys(me.profile ?? {})).not.toContain('date_of_birth');
    expect(Object.keys(me.profile ?? {})).not.toContain('protected_birthdate');
  });
});

describe('network error reporting', () => {
  it('names the configured base URL so a wrong address is diagnosable', async () => {
    const client = new ApiClient({
      baseUrl: 'http://10.0.2.2:8000',
      getToken: async () => 'token',
      fetchImpl: async () => {
        throw new TypeError('Failed to fetch');
      },
    });

    await expect(createApi(client).getMe()).rejects.toMatchObject({
      kind: 'network',
      message: expect.stringContaining('http://10.0.2.2:8000'),
    });
  });
});

describe('default fetch binding', () => {
  it('calls the global fetch with the global as receiver', async () => {
    // Browsers throw "Illegal invocation" when fetch is called with anything
    // other than the window as receiver, which is exactly what storing a bare
    // reference on the client instance would do. React Native does not enforce
    // this, so only a check like the one below catches the web-only failure.
    const original = globalThis.fetch;
    let receiver: unknown = 'never called';
    globalThis.fetch = function (this: unknown) {
      receiver = this;
      if (this !== globalThis && this !== undefined) {
        throw new TypeError(
          "Failed to execute 'fetch' on 'Window': Illegal invocation",
        );
      }
      return Promise.resolve(
        new Response('{"status_code":"OK"}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    } as typeof globalThis.fetch;

    try {
      const client = new ApiClient({
        baseUrl: 'http://127.0.0.1:8000',
        getToken: async () => 'token',
      });
      await expect(createApi(client).getMe()).resolves.toBeDefined();
      expect(receiver).toBe(globalThis);
    } finally {
      globalThis.fetch = original;
    }
  });
});

describe('OnboardingScreen', () => {
  it('offers a way out for a signed-in account that has not onboarded', () => {
    const onSignOut = jest.fn();
    render(
      <OnboardingScreen
        api={stubApi()}
        onCompleted={jest.fn()}
        onSignOut={onSignOut}
      />,
    );

    // Without this the account is trapped: onboarding is the first screen, and
    // the profile screen that holds sign-out is only reachable afterwards.
    fireEvent.press(screen.getByText('다른 계정으로 로그인'));
    expect(onSignOut).toHaveBeenCalled();
  });
});

describe('SessionCarousel', () => {
  const state = (id: string, done: boolean): SessionItem => ({
    plan_item_id: id,
    status_code: done ? 'COMPLETED' : 'PENDING',
    completed_at: done ? '2026-08-17T10:05:00+09:00' : null,
  });

  it('shows every block but centres the one the server still has pending', () => {
    render(
      <SessionCarousel
        items={plan(3).items}
        states={[
          state('item-1', true),
          state('item-2', false),
          state('item-3', false),
        ]}
        currentIndex={1}
        pending={false}
        onToggle={jest.fn()}
        onOpenDetail={jest.fn()}
        detailFor={null}
        detail={null}
      />,
    );

    // All three remain mounted; the centring is a transform, not a filter, so
    // the completed card slides out rather than disappearing.
    expect(screen.getByText('운동 1')).toBeTruthy();
    expect(screen.getByText('운동 2')).toBeTruthy();
    expect(screen.getByText('운동 3')).toBeTruthy();
    expect(screen.getAllByText('완료 취소')).toHaveLength(1);
  });

  it('sends the completion through the callback rather than advancing itself', () => {
    const onToggle = jest.fn();
    render(
      <SessionCarousel
        items={plan(2).items}
        states={[state('item-1', false), state('item-2', false)]}
        currentIndex={0}
        pending={false}
        onToggle={onToggle}
        onOpenDetail={jest.fn()}
        detailFor={null}
        detail={null}
      />,
    );

    fireEvent.press(screen.getAllByText('완료 체크')[0]!);
    expect(onToggle).toHaveBeenCalledWith('item-1', 'COMPLETED');
  });
});

describe('MascotStage', () => {
  it('shows the mascot artwork in its playful form', () => {
    const playful = render(
      <MascotStage
        eyebrow="지금 할 운동"
        title="스쿼트"
        caption="천천히 해요"
      />,
    );
    expect(playful.UNSAFE_getAllByType(Image)).toHaveLength(1);
    expect(playful.queryByText('!')).toBeNull();
    playful.unmount();
  });

  it('drops the mascot and colour in its serious form', () => {
    // Pain and adverse-response screens must not carry the mascot character.
    render(
      <MascotStage
        serious
        eyebrow="안전 안내"
        title="운동을 멈춰주세요"
        caption="도움을 받아주세요"
      />,
    );
    expect(screen.UNSAFE_queryAllByType(Image)).toHaveLength(0);
    expect(screen.getByText('!')).toBeTruthy();
    expect(screen.getByLabelText('안전 안내 화면')).toBeTruthy();
  });

  it('uses the completion artwork only when asked for it', () => {
    const progress = render(
      <MascotStage
        eyebrow="오늘의 결과"
        title="여기까지"
        caption="기록했어요"
      />,
    );
    const progressSource = progress.UNSAFE_getAllByType(Image)[0]!.props.source;
    progress.unmount();

    const complete = render(
      <MascotStage
        art="complete"
        eyebrow="오늘의 결과"
        title="전부 해냈어요"
        caption="기록했어요"
      />,
    );
    const completeSource = complete.UNSAFE_getAllByType(Image)[0]!.props.source;
    expect(completeSource).not.toEqual(progressSource);
  });
});

describe('MascotHouseScreen', () => {
  it('is reachable from the tab bar and shows the real routine', async () => {
    const onNavigate = jest.fn();
    render(
      <MascotHouseScreen
        api={stubApi({
          getCurrentRoutine: jest.fn(async () => routine()),
          getWeek: jest.fn(async () => ({
            week_id: 'week-1',
            week_start: '2026-08-17',
            week_end: '2026-08-23',
            timezone: 'Asia/Seoul',
            target_workout_count: 3,
            plan_origin_code: 'COLD_START',
            cold_start_applied: true,
            status_code: 'OPEN' as const,
            closed_at: null,
            report_id: null,
            report_status_code: null,
          })),
        } as unknown as Partial<Api>)}
        nickname="데모"
        onNavigate={onNavigate}
      />,
    );

    expect(await screen.findByText('목표 3회')).toBeTruthy();
    // The routine shown is the server's, not a fixture.
    expect(screen.getByText('지금 내 루틴')).toBeTruthy();
    // The real mascot artwork, not a drawn placeholder.
    expect(screen.getByLabelText('끼끼와 운동 섬')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('홈'));
    expect(onNavigate).toHaveBeenCalledWith('home');
  });

  it('exposes every tab, including the mascot house', async () => {
    render(
      <MascotHouseScreen
        api={stubApi({
          getCurrentRoutine: jest.fn(notFound),
          getWeek: jest.fn(async () => {
            throw new Error('unavailable');
          }),
        } as unknown as Partial<Api>)}
        nickname="데모"
        onNavigate={jest.fn()}
      />,
    );

    for (const label of ['홈', '끼끼의 집', '리포트', '마이페이지']) {
      expect(await screen.findByLabelText(label)).toBeTruthy();
    }
  });
});
