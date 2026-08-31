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
  within,
} from '@testing-library/react-native';
import { Image, Platform, ScrollView, StyleSheet } from 'react-native';

import { ApiClient, createIdempotencyKey } from '../src/api/client';
import { ApiError } from '../src/api/errors';
import { createApi, type Api } from '../src/api/endpoints';
import type {
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  OnboardingRequest,
  OnboardingResponse,
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
    generation_mode_code: 'ORIGINAL',
    decision_engine_code: 'DETERMINISTIC',
    root_decision_id: 'decision-1',
    parent_decision_id: null,
    regeneration_sequence: 0,
    meaningful_difference_codes: null,
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
      attention_area_codes: ['KNEE'],
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
    regenerateDecision: jest.fn(),
    selectOption: jest.fn(),
    listWorkoutSessions: jest.fn(async () => ({
      items: [],
      next_cursor: null,
    })),
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

function completedOnboarding(): OnboardingResponse {
  return {
    user_id: 'user-1',
    onboarding_completed: true,
    profile_version: 1,
    coaching_style_code: 'SUPPORTIVE',
    ai_trial_started_at: '2026-08-18T00:00:00+09:00',
    ai_trial_ends_at: '2026-09-17T00:00:00+09:00',
    premium_status_code: 'TRIAL',
    created_at: '2026-08-18T00:00:00+09:00',
    updated_at: '2026-08-18T00:00:00+09:00',
  };
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

  it('opens the existing account screen route from the Home profile button', async () => {
    const onTab = jest.fn();
    renderHome(homeApi(), { onTab });

    fireEvent.press(await screen.findByRole('button', { name: '프로필 열기' }));
    expect(onTab).toHaveBeenCalledWith('my');
  });

  it('offers transient discomfort areas independently of onboarding attention areas', async () => {
    renderHome(homeApi());

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    expect(screen.queryByRole('button', { name: '무릎' })).toBeNull();
    fireEvent.press(screen.getByRole('button', { name: '있음' }));
    expect(screen.getByRole('button', { name: '무릎' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '어깨' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '허리' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '전신' })).toBeNull();
    expect(screen.queryByRole('button', { name: '기타 부위' })).toBeNull();
    expect(screen.queryByRole('button', { name: '목' })).toBeNull();
    expect(screen.queryByRole('button', { name: '가슴' })).toBeNull();
    expect(screen.queryByRole('button', { name: '복부' })).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '다른 부위 더 보기' }));
    expect(screen.getByRole('button', { name: '목' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '가슴' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '복부' })).toBeTruthy();
  });

  it('offers routine creation when none exists yet', async () => {
    renderHome(
      homeApi({
        getCurrentRoutine: jest.fn(notFound),
      } as unknown as Partial<Api>),
    );

    expect(await screen.findByText('기본 루틴이 아직 없어요')).toBeTruthy();
  });

  it('renders weekly progress from official workout-session records', async () => {
    const listWorkoutSessions = jest.fn(async () => ({
      items: [
        {
          session_id: 'session-completed',
          local_date: '2026-08-17',
          status_code: 'COMPLETED' as const,
          completed_item_count: 2,
          total_item_count: 2,
          requested_duration_minutes: 30,
          training_type_code: 'STRENGTH',
          not_completed_reason_code: null,
          started_at: '2026-08-17T09:00:00+09:00',
          finished_at: '2026-08-17T09:30:00+09:00',
        },
      ],
      next_cursor: null,
    }));

    renderHome(homeApi({ listWorkoutSessions }));

    expect(await screen.findAllByTestId('day-done-image')).toHaveLength(1);
    expect(listWorkoutSessions).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 100 }),
      expect.anything(),
    );
  });

  it('loads reviewed exercise instructions from a Home routine item', async () => {
    const getExercise = jest.fn(async (exerciseId: string) => ({
      exercise_id: exerciseId,
      exercise_name: '운동 1',
      training_type_code: 'STRENGTH',
      primary_body_area_codes: ['FULL_BODY'],
      instruction_summary: '검수된 운동 설명입니다.',
      form_cues: ['천천히 움직이기'],
      media_asset_key: null,
      mascot_animation_asset_key: null,
      instruction_content_version: 'test-v1',
    }));
    renderHome(
      homeApi({
        getDailyContext: jest.fn(async () => dailyContext()),
        getExercise,
      }),
      { decision: decision() },
    );

    fireEvent.press(
      await screen.findByRole('button', {
        name: /운동 1.*자세 보기/,
      }),
    );

    expect(
      await screen.findByText('검수된 운동 설명입니다.'),
    ).toBeOnTheScreen();
    expect(getExercise).toHaveBeenCalledWith('exercise-1', expect.anything());
  });

  it('stores a dragged Home order in the shared plan used to start Workout', async () => {
    const original = decision();
    const onDecisionChange = jest.fn();
    renderHome(
      homeApi({ getDailyContext: jest.fn(async () => dailyContext()) }),
      { decision: original, onDecisionChange },
    );

    fireEvent(
      await screen.findByTestId('routine-drag-item-1'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );

    const update = onDecisionChange.mock.calls[0]?.[0] as (
      current: DecisionResponse | null,
    ) => DecisionResponse | null;
    const reordered = update(original);
    expect(reordered?.final_plan?.items).toEqual([
      expect.objectContaining({ plan_item_id: 'item-2', sequence: 1 }),
      expect.objectContaining({ plan_item_id: 'item-1', sequence: 2 }),
    ]);
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
      expect.objectContaining({ sleep_minutes: null, available_slots: null }),
      undefined,
    );
  });

  it('preserves stored optional check-in codes that have no approved UI choices', async () => {
    const storedContext = {
      ...dailyContext(),
      fasting_state_code: 'FASTED',
      hydration_state_code: 'LOW',
    };
    const replaceDailyContext = jest.fn(async () => storedContext);
    renderHome(
      homeApi({
        getDailyContext: jest.fn(async () => storedContext),
        replaceDailyContext,
        createDecision: jest.fn(async () => decision()),
      }),
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    await waitFor(() => expect(replaceDailyContext).toHaveBeenCalled());
    expect(replaceDailyContext).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        fasting_state_code: 'FASTED',
        hydration_state_code: 'LOW',
      }),
      storedContext.context_version,
    );
  });

  it('sends discomfort severity and adverse reactions as stable API codes', async () => {
    const replaceDailyContext = jest.fn(async () => dailyContext());
    renderHome(
      homeApi({
        replaceDailyContext,
        createDecision: jest.fn(async () => decision()),
      }),
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '있음' }));
    fireEvent.press(screen.getByRole('button', { name: '무릎' }));
    fireEvent.press(screen.getByRole('button', { name: '심함' }));
    fireEvent.press(screen.getByRole('button', { name: '있어요' }));
    fireEvent.press(screen.getByRole('button', { name: '심한 어지럼' }));
    fireEvent.changeText(
      screen.getByLabelText('어젯밤 수면 시간 (시간)'),
      '6.5',
    );
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    await waitFor(() => expect(replaceDailyContext).toHaveBeenCalled());
    expect(replaceDailyContext).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        sleep_minutes: 390,
        discomforts: [{ body_area_code: 'KNEE', severity_code: 'SEVERE' }],
        adverse_reaction_codes: ['SEVERE_DIZZINESS'],
      }),
      undefined,
    );
  });

  it('sends multiple discomforts and the selected daily location', async () => {
    const replaceDailyContext = jest.fn(async () => dailyContext());
    const customMe = me();
    customMe.profile = {
      ...customMe.profile!,
      available_location_codes: ['HOME', 'GYM'],
      attention_area_codes: ['SHOULDER', 'KNEE'],
    };
    renderHome(
      homeApi({
        replaceDailyContext,
        createDecision: jest.fn(async () => decision()),
      }),
      { me: customMe },
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '헬스장' }));
    fireEvent.press(screen.getByRole('button', { name: '있음' }));
    fireEvent.press(screen.getByRole('button', { name: '어깨' }));
    fireEvent.press(screen.getByRole('button', { name: '보통' }));
    fireEvent.press(screen.getByRole('button', { name: '무릎' }));
    fireEvent.press(screen.getAllByRole('button', { name: '심함' })[1]!);
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    await waitFor(() => expect(replaceDailyContext).toHaveBeenCalled());
    expect(replaceDailyContext).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        location_code: 'GYM',
        discomforts: [
          { body_area_code: 'SHOULDER', severity_code: 'MODERATE' },
          { body_area_code: 'KNEE', severity_code: 'SEVERE' },
        ],
      }),
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

    await waitFor(() => expect(onRestChosen).toHaveBeenCalledWith(false));
    expect(selectOption).toHaveBeenCalledWith('decision-1', 'option-rest');
    expect(onSessionStarted).not.toHaveBeenCalled();
  });

  it('regenerates the current V3 decision with optimistic concurrency values', async () => {
    const regenerated = decision({
      decision_id: 'decision-2',
      generation_mode_code: 'REGENERATED',
      parent_decision_id: 'decision-1',
      regeneration_sequence: 1,
      meaningful_difference_codes: ['CORE_EXERCISE_CHANGED'],
    });
    const regenerateDecision = jest.fn(async () => regenerated);
    const onDecisionChange = jest.fn();
    renderHome(
      homeApi({
        regenerateDecision,
      }),
      { decision: decision(), onDecisionChange },
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '다른 루틴 추천 받기' }),
    );

    await waitFor(() => {
      expect(regenerateDecision).toHaveBeenCalledWith('decision-1', {
        expected_plan_id: 'plan-1',
        expected_regeneration_sequence: 0,
      });
      expect(onDecisionChange).toHaveBeenCalledWith(regenerated);
    });
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

    fireEvent.press(
      await screen.findByRole('button', { name: '운동 시작하기' }),
    );

    await waitFor(() =>
      expect(onSessionStarted).toHaveBeenCalledWith(
        'session-1',
        decision().final_plan,
      ),
    );
  });

  it('disables a routine option the backend marks as unselectable', async () => {
    const selectOption = jest.fn();
    const blockedDecision = decision({
      options: decision().options.map((option) =>
        option.option_code === 'FINAL_ROUTINE'
          ? {
              ...option,
              selectable: false,
              blocked_reason_code: 'CURRENT_LOCATION_UNSUPPORTED',
            }
          : option,
      ),
    });

    renderHome(homeApi({ selectOption } as unknown as Partial<Api>), {
      decision: blockedDecision,
    });

    expect(
      await screen.findByText('현재 장소에서 가능한 운동을 확인했어요.'),
    ).toBeOnTheScreen();
    const startButton = screen.getByRole('button', {
      name: '운동 시작하기',
    });
    expect(startButton.props.accessibilityState.disabled).toBe(true);
    fireEvent.press(startButton);
    expect(selectOption).not.toHaveBeenCalled();
  });

  it('does not offer a rest action the backend marks as unselectable', async () => {
    const selectOption = jest.fn();
    const blockedDecision = decision({
      action_code: 'REST',
      final_plan: null,
      options: decision().options.map((option) =>
        option.option_code === 'REST'
          ? {
              ...option,
              selectable: false,
              blocked_reason_code: 'OPTION_NOT_SELECTABLE',
            }
          : option,
      ),
    });

    renderHome(homeApi({ selectOption } as unknown as Partial<Api>), {
      decision: blockedDecision,
    });

    expect(await screen.findByText('오늘은 휴식을 추천해요')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '오늘은 쉬기' })).toBeNull();
    expect(selectOption).not.toHaveBeenCalled();
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
  function fillRequiredOnboardingSteps({
    attentionArea,
    birthdate = '1997-08-11',
    selectLocations,
    selectOptionalPreferences = true,
  }: {
    attentionArea?: string;
    birthdate?: string;
    selectLocations?: () => void;
    selectOptionalPreferences?: boolean;
  } = {}) {
    fireEvent.changeText(
      screen.getByPlaceholderText('앱에서 불릴 이름'),
      '헬끼',
    );
    const [year, month, day] = birthdate.split('-').map(Number);
    fireEvent.press(screen.getByLabelText(`연도 ${year}년`));
    fireEvent.press(screen.getByLabelText(`월 ${month}월`));
    fireEvent.press(screen.getByLabelText(`일 ${day}일`));
    fireEvent.press(screen.getByText('다음'));
    fireEvent.press(screen.getByText('여성'));
    fireEvent.press(screen.getByText('다음'));
    fireEvent.changeText(screen.getByLabelText('키'), '172.4');
    fireEvent.changeText(screen.getByLabelText('체중'), '68.5');
    fireEvent.press(screen.getByText('다음'));
    fireEvent.press(screen.getByText('체력 증진'));
    fireEvent.press(screen.getByText('다음'));
    expect(screen.getByRole('button', { name: '초급' })).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    fireEvent.press(screen.getByText('다음'));
    if (selectOptionalPreferences) {
      fireEvent.press(screen.getByText('간결하게'));
    }
    fireEvent.press(screen.getByText('다음'));
    if (selectLocations) {
      selectLocations();
    } else {
      fireEvent.press(screen.getByText('집'));
    }
    fireEvent.press(screen.getByText('다음'));
    fireEvent.press(screen.getByText('다음'));
    fireEvent.press(screen.getByText('다음'));
    if (attentionArea) {
      fireEvent.press(screen.getByText('있어요'));
      fireEvent.press(screen.getByText(attentionArea));
    } else {
      fireEvent.press(screen.getByText('없어요'));
    }
    fireEvent.press(screen.getByText('다음'));
  }

  function acceptRequiredConsents() {
    fireEvent.press(
      screen.getByRole('checkbox', { name: '개인정보 수집 및 이용' }),
    );
    fireEvent.press(
      screen.getByRole('checkbox', { name: '건강 관련 민감정보 처리' }),
    );
  }

  it('offers a way out for a signed-in account that has not onboarded', () => {
    const onSignOut = jest.fn();
    render(
      <OnboardingScreen
        api={stubApi()}
        onCompleted={jest.fn()}
        onSignOut={onSignOut}
      />,
    );

    // The first Previous action returns to login so an account cannot become
    // trapped before onboarding has been completed.
    fireEvent.press(screen.getByText('이전'));
    expect(onSignOut).toHaveBeenCalled();
  });

  it('shows one onboarding question at a time with progress navigation', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    expect(screen.getByText('1 / 11')).toBeOnTheScreen();
    expect(screen.getByText('기본 정보를 알려주세요')).toBeOnTheScreen();
    expect(
      screen.queryByText('만 14세 이상만 선택할 수 있어요.'),
    ).not.toBeOnTheScreen();
    expect(screen.queryByText(/선택 가능한 최근 날짜는/)).not.toBeOnTheScreen();
    expect(screen.queryByText('성별을 선택해주세요')).not.toBeOnTheScreen();

    fireEvent.changeText(
      screen.getByPlaceholderText('앱에서 불릴 이름'),
      '헬끼',
    );
    fireEvent.press(screen.getByLabelText('연도 1997년'));
    fireEvent.press(screen.getByLabelText('월 8월'));
    fireEvent.press(screen.getByLabelText('일 11일'));
    fireEvent.press(screen.getByText('다음'));

    expect(screen.getByText('2 / 11')).toBeOnTheScreen();
    expect(screen.getByText('성별을 선택해주세요')).toBeOnTheScreen();
    expect(screen.getByText('맞춤 운동 추천에 참고해요.')).toBeOnTheScreen();
    expect(
      screen.queryByText('운동 강도와 권장 범위를 조정하는 데 사용해요.'),
    ).not.toBeOnTheScreen();
    expect(screen.getByText('여성')).toBeOnTheScreen();
    expect(screen.getByText('남성')).toBeOnTheScreen();
    expect(screen.queryByText('선택 안 함')).not.toBeOnTheScreen();
    expect(screen.queryByText('기본 정보를 알려주세요')).not.toBeOnTheScreen();
  });

  it('only exposes birthdates that meet the age requirement', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.changeText(
      screen.getByPlaceholderText('앱에서 불릴 이름'),
      '가'.repeat(70),
    );
    expect(screen.getByLabelText('닉네임')).toHaveProp(
      'value',
      '가'.repeat(64),
    );

    const today = new Date();
    const latestEligibleYear = today.getFullYear() - 14;
    const latestEligibleMonth = today.getMonth() + 1;
    const latestEligibleDay = Math.min(
      today.getDate(),
      new Date(latestEligibleYear, latestEligibleMonth, 0).getDate(),
    );
    expect(
      screen.getByLabelText(`연도 ${latestEligibleYear}년`),
    ).toBeOnTheScreen();
    expect(
      screen.queryByLabelText(`연도 ${latestEligibleYear + 1}년`),
    ).not.toBeOnTheScreen();
    expect(screen.getByLabelText(`연도 ${latestEligibleYear}년`)).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    expect(screen.getByLabelText(`월 ${latestEligibleMonth}월`)).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    expect(screen.getByLabelText(`일 ${latestEligibleDay}일`)).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    expect(screen.queryByLabelText('연도 선택')).not.toBeOnTheScreen();
    expect(screen.getByText('다음')).toBeEnabled();

    fireEvent(screen.getByLabelText('연도 선택 스크롤'), 'momentumScrollEnd', {
      nativeEvent: { contentOffset: { y: 44 } },
    });
    expect(
      screen.getByLabelText(`연도 ${latestEligibleYear - 1}년`),
    ).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    expect(screen.getByLabelText('월 12월')).toBeOnTheScreen();

    fireEvent.press(screen.getByLabelText(`연도 ${latestEligibleYear}년`));
    if (latestEligibleMonth < 12) {
      expect(
        screen.queryByLabelText(`월 ${latestEligibleMonth + 1}월`),
      ).not.toBeOnTheScreen();
    }
    fireEvent.press(screen.getByLabelText(`월 ${latestEligibleMonth}월`));
    expect(
      screen.queryByLabelText(`일 ${latestEligibleDay + 1}일`),
    ).not.toBeOnTheScreen();

    fireEvent.press(screen.getByLabelText('연도 1997년'));
    fireEvent.press(screen.getByLabelText('월 2월'));
    expect(screen.queryByLabelText('일 30일')).not.toBeOnTheScreen();
    fireEvent.press(screen.getByLabelText('일 28일'));
    fireEvent.press(screen.getByText('다음'));
    expect(screen.getByText('2 / 11')).toBeOnTheScreen();
  });

  it('uses the revised onboarding copy without the removed helper text', () => {
    const screenProps = {
      api: stubApi(),
      onCompleted: jest.fn(),
      onSignOut: jest.fn(),
    };
    const goal = render(<OnboardingScreen {...screenProps} initialStep={4} />);
    expect(screen.getByText('다이어트')).toBeOnTheScreen();
    expect(screen.getByText('근력 증가')).toBeOnTheScreen();
    expect(screen.getByText('체력 증진')).toBeOnTheScreen();
    goal.unmount();

    const experience = render(
      <OnboardingScreen {...screenProps} initialStep={5} />,
    );
    expect(screen.getByRole('button', { name: '초급' })).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ selected: true }),
    );
    expect(screen.getByRole('button', { name: '중급' })).toBeOnTheScreen();
    experience.unmount();

    const location = render(
      <OnboardingScreen {...screenProps} initialStep={7} />,
    );
    expect(screen.getByText('어디에서 운동해요?')).toBeOnTheScreen();
    expect(
      screen.queryByText('주로 어디에서 운동하나요?'),
    ).not.toBeOnTheScreen();
    location.unmount();

    const attention = render(
      <OnboardingScreen {...screenProps} initialStep={10} />,
    );
    expect(screen.getByText('평소에 통증 부위가 있나요?')).toBeOnTheScreen();
    expect(screen.getByText('평소에 통증 부위가 있나요?')).toHaveProp(
      'numberOfLines',
      1,
    );
    expect(screen.getByText('평소에 통증 부위가 있나요?').props.style).toEqual(
      expect.objectContaining({ fontSize: 22 }),
    );
    expect(
      screen.queryByText('주의가 필요한 부위가 있나요?'),
    ).not.toBeOnTheScreen();
    expect(
      screen.queryByText('먼저 있음 또는 없음을 선택해주세요.'),
    ).not.toBeOnTheScreen();
    attention.unmount();

    render(<OnboardingScreen {...screenProps} initialStep={11} />);
    expect(
      screen.queryByText('필수 2개만 동의하면 시작할 수 있어요.'),
    ).not.toBeOnTheScreen();
  });

  it('snaps mouse-wheel and touch scrolling to the nearest date item', () => {
    const originalPlatform = Platform.OS;
    jest.useFakeTimers();
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: 'web',
    });
    try {
      render(
        <OnboardingScreen
          api={stubApi()}
          onCompleted={jest.fn()}
          onSignOut={jest.fn()}
        />,
      );

      fireEvent.press(screen.getByLabelText('연도 1997년'));
      fireEvent.press(screen.getByLabelText('월 6월'));
      const monthWheel = screen.getByLabelText('월 선택 스크롤');
      const preventDefault = jest.fn();
      expect(monthWheel).toHaveProp('disableIntervalMomentum', true);

      fireEvent(monthWheel, 'wheel', {
        nativeEvent: { deltaMode: 0, deltaY: 100 },
        preventDefault,
      });
      expect(preventDefault).toHaveBeenCalled();
      fireEvent(monthWheel, 'wheel', {
        nativeEvent: { deltaMode: 0, deltaY: 100 },
        preventDefault,
      });
      expect(screen.getByLabelText('월 6월')).toHaveProp(
        'accessibilityState',
        expect.objectContaining({ selected: true }),
      );

      act(() => {
        jest.advanceTimersByTime(45);
      });
      expect(screen.getByLabelText('월 7월')).toHaveProp(
        'accessibilityState',
        expect.objectContaining({ selected: true }),
      );

      // A strong wheel gesture keeps its intent and advances several items.
      fireEvent(monthWheel, 'wheel', {
        nativeEvent: { deltaMode: 0, deltaY: 540 },
        preventDefault,
      });
      act(() => {
        jest.advanceTimersByTime(45);
      });
      expect(screen.getByLabelText('월 12월')).toHaveProp(
        'accessibilityState',
        expect.objectContaining({ selected: true }),
      );

      fireEvent(monthWheel, 'momentumScrollEnd', {
        nativeEvent: { contentOffset: { y: 2.6 * 44 } },
      });
      expect(screen.getByLabelText('월 4월')).toHaveProp(
        'accessibilityState',
        expect.objectContaining({ selected: true }),
      );
    } finally {
      jest.clearAllTimers();
      jest.useRealTimers();
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  });

  it('keeps the animated wheel movement when a date item is pressed', () => {
    const scrollTo = jest.spyOn(ScrollView.prototype, 'scrollTo');
    try {
      render(
        <OnboardingScreen
          api={stubApi()}
          onCompleted={jest.fn()}
          onSignOut={jest.fn()}
        />,
      );
      scrollTo.mockClear();

      fireEvent.press(screen.getByLabelText('연도 1997년'));

      const scrollRequests = scrollTo.mock.calls
        .map(([request]) => request)
        .filter(
          (
            request,
          ): request is {
            animated?: boolean;
            x?: number;
            y?: number;
          } => typeof request === 'object' && request !== null,
        );
      const animatedSelection = scrollRequests.find(
        (request) => request.animated === true,
      );
      expect(animatedSelection).toEqual({
        animated: true,
        y: expect.any(Number),
      });
      expect(scrollRequests).not.toContainEqual({
        animated: false,
        y: animatedSelection?.y,
      });
      expect(screen.getByLabelText('연도 1997년')).toHaveProp(
        'accessibilityState',
        expect.objectContaining({ selected: true }),
      );
    } finally {
      scrollTo.mockRestore();
    }
  });

  it('separates four consent checkboxes into required and optional items', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={11}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    const requiredLabels = ['개인정보 수집 및 이용', '건강 관련 민감정보 처리'];
    const optionalLabels = ['웨어러블 연동', '마케팅 정보 수신'];

    expect(screen.getAllByRole('checkbox')).toHaveLength(4);
    expect(
      screen.queryByRole('checkbox', { name: '캘린더 연동' }),
    ).not.toBeOnTheScreen();
    requiredLabels.forEach((label) => {
      expect(
        within(screen.getByRole('checkbox', { name: label })).getByText('필수'),
      ).toBeOnTheScreen();
    });
    optionalLabels.forEach((label) => {
      expect(
        within(screen.getByRole('checkbox', { name: label })).getByText('선택'),
      ).toBeOnTheScreen();
    });
  });

  it('explains the purpose of every consent item', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={11}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    [
      '닉네임·생년월일·키·체중으로 나에게 맞는 운동 강도를 계산해요.',
      '통증 부위와 컨디션 체크인을 받아 위험한 동작을 빼요.',
      '워치 데이터로 컨디션 입력을 줄여줘요. 없어도 앱은 그대로 써요.',
      '새 기능과 이벤트 소식을 보내요.',
    ].forEach((description) => {
      expect(screen.getByText(description)).toBeOnTheScreen();
    });
  });

  it('names every remaining required consent and enables submission only after both are checked', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={11}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        '남은 필수 동의: 개인정보 수집 및 이용, 건강 관련 민감정보 처리\n안전한 루틴을 만들려면 이 동의가 필요해요.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(
      screen.getByRole('checkbox', { name: '개인정보 수집 및 이용' }),
    );
    expect(
      screen.getByText(
        '남은 필수 동의: 건강 관련 민감정보 처리\n안전한 루틴을 만들려면 이 동의가 필요해요.',
      ),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();

    fireEvent.press(
      screen.getByRole('checkbox', { name: '건강 관련 민감정보 처리' }),
    );
    expect(screen.getByRole('button', { name: '시작하기' })).toBeEnabled();
    expect(screen.queryByText(/남은 필수 동의:/)).not.toBeOnTheScreen();
  });

  it('submits optional consents as false when only required consents are checked', async () => {
    const submitOnboarding = jest.fn(async (_request: OnboardingRequest) =>
      completedOnboarding(),
    );
    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps();
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(submitOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({
          consents: {
            general_personal_data: true,
            sensitive_data: true,
            wearable_integration: false,
            calendar_integration: false,
            marketing: false,
          },
        }),
      );
    });
  });

  it('submits enabled optional consent values while calendar consent stays disabled', async () => {
    const submitOnboarding = jest.fn(async (_request: OnboardingRequest) =>
      completedOnboarding(),
    );
    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps();
    acceptRequiredConsents();
    fireEvent.press(screen.getByRole('checkbox', { name: '웨어러블 연동' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '마케팅 정보 수신' }));
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(submitOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({
          consents: {
            general_personal_data: true,
            sensitive_data: true,
            wearable_integration: true,
            calendar_integration: false,
            marketing: true,
          },
        }),
      );
    });
  });

  it('still handles the server age block as a defense in depth', async () => {
    const submitOnboarding = jest.fn(async () => {
      throw new ApiError({
        kind: 'permission',
        code: 'AGE_REQUIREMENT_NOT_MET',
        status: 403,
        message: '만 14세 미만은 이용할 수 없습니다.',
      });
    });
    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps();
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(submitOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({ date_of_birth: '1997-08-11' }),
      );
      expect(screen.getByText('1 / 11')).toBeOnTheScreen();
      expect(
        screen.getByText('만 14세 미만은 이용할 수 없습니다.'),
      ).toBeOnTheScreen();
    });
  });

  it('requires explicit location and attention answers without showing an equipment page', () => {
    const { rerender } = render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={7}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();
    fireEvent.press(screen.getByText('집'));
    fireEvent.press(screen.getByText('다음'));
    expect(
      screen.getByText('한 번에 몇 분 운동하고 싶나요?'),
    ).toBeOnTheScreen();
    expect(screen.queryByText('사용할 수 있는 장비가 있나요?')).toBeNull();

    rerender(
      <OnboardingScreen
        api={stubApi()}
        initialStep={10}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );
    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();
    fireEvent.press(screen.getByText('있어요'));
    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();
    fireEvent.press(screen.getByText('무릎'));
    expect(screen.getByText('무릎 통증 정도')).toBeOnTheScreen();
    const slider = screen.getByRole('adjustable', {
      name: '무릎 통증 정도',
    });
    expect(slider).toHaveAccessibilityValue({
      min: 1,
      max: 10,
      now: 1,
      text: '10점 중 1점',
    });
    fireEvent(slider, 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });
    expect(slider).toHaveAccessibilityValue({
      min: 1,
      max: 10,
      now: 2,
      text: '10점 중 2점',
    });
    expect(screen.getByRole('button', { name: '다음' })).toBeEnabled();
  });

  it('aligns multiple pain controls without wrapping labels and uses the safety-notice palette', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={10}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByText('있어요'));
    fireEvent.press(screen.getByText('손목·손'));
    fireEvent.press(screen.getByText('발목·발'));

    expect(screen.getAllByRole('adjustable')).toHaveLength(2);
    expect(screen.getByText('손목·손 통증 정도').props.numberOfLines).toBe(1);
    expect(screen.getByText('발목·발 통증 정도').props.numberOfLines).toBe(1);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('onboarding-pain-slider-card-손목·손').props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#FBEAE7',
      borderColor: '#F1BFAE',
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('onboarding-pain-intensity-value-손목·손').props
          .style,
      ),
    ).toMatchObject({
      backgroundColor: '#FFFFFF',
      color: '#8E3226',
      fontWeight: '400',
    });
  });

  it('lets users select every integer pain score from 1 to 10 on the slider', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={10}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );
    fireEvent.press(screen.getByText('있어요'));
    fireEvent.press(screen.getByText('무릎'));
    const slider = screen.getByRole('adjustable', {
      name: '무릎 통증 정도',
    });

    fireEvent(slider, 'layout', { nativeEvent: { layout: { width: 180 } } });
    fireEvent(slider, 'responderGrant', {
      nativeEvent: { locationX: 120 },
    });

    expect(slider).toHaveAccessibilityValue({
      min: 1,
      max: 10,
      now: 7,
      text: '10점 중 7점',
    });
    expect(screen.getByText('7')).toBeOnTheScreen();
  });

  it('hides unsupported and extended attention areas until expanded', () => {
    render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={10}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByText('있어요'));
    expect(screen.queryByRole('button', { name: '전신' })).toBeNull();
    expect(screen.queryByRole('button', { name: '기타 부위' })).toBeNull();
    expect(screen.queryByRole('button', { name: '목' })).toBeNull();
    expect(screen.queryByRole('button', { name: '가슴' })).toBeNull();
    expect(screen.queryByRole('button', { name: '복부' })).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '다른 부위 더 보기' }));
    expect(screen.getByRole('button', { name: '목' })).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '가슴' })).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '복부' })).toBeOnTheScreen();
  });

  it('adjusts duration by 10 minutes and weekly frequency from 1 to 7', () => {
    const view = render(
      <OnboardingScreen
        api={stubApi()}
        initialStep={8}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    expect(screen.getByText('30분')).toBeOnTheScreen();
    fireEvent.press(screen.getByLabelText('운동 시간 10분 늘리기'));
    expect(screen.getByText('40분')).toBeOnTheScreen();
    fireEvent.press(screen.getByLabelText('운동 시간 10분 줄이기'));
    expect(screen.getByText('30분')).toBeOnTheScreen();

    view.rerender(
      <OnboardingScreen
        api={stubApi()}
        initialStep={9}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );
    expect(screen.getByText('주 3회')).toBeOnTheScreen();
    for (let count = 3; count < 7; count += 1) {
      fireEvent.press(screen.getByLabelText('주간 운동 횟수 1회 늘리기'));
    }
    expect(screen.getByText('주 7회')).toBeOnTheScreen();
    expect(screen.getByLabelText('주간 운동 횟수 1회 늘리기')).toBeDisabled();
  });

  it('maps Profile gender and body values to the backend onboarding contract', async () => {
    const submitOnboarding = jest.fn(async (_request: OnboardingRequest) => ({
      user_id: 'user-1',
      onboarding_completed: true,
      profile_version: 1,
      coaching_style_code: 'SUPPORTIVE',
      ai_trial_started_at: '2026-08-18T00:00:00+09:00',
      ai_trial_ends_at: '2026-09-17T00:00:00+09:00',
      premium_status_code: 'TRIAL',
      created_at: '2026-08-18T00:00:00+09:00',
      updated_at: '2026-08-18T00:00:00+09:00',
    }));
    const onCompleted = jest.fn();

    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={onCompleted}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps({ attentionArea: '무릎' });
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(submitOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({
          sex_code: 'FEMALE',
          height_cm: 172.4,
          weight_kg: 68.5,
          primary_goal_code: 'GENERAL_FITNESS',
          experience_level_code: 'BEGINNER',
          preferred_exercise_type_codes: [],
          coaching_style_code: 'CONCISE',
          attention_area_codes: ['KNEE'],
        }),
      );
      expect(submitOnboarding.mock.calls[0]?.[0]).not.toHaveProperty(
        'attention_severities',
      );
      expect(submitOnboarding.mock.calls[0]?.[0]).not.toHaveProperty(
        'equipment_codes',
      );
      expect(onCompleted).toHaveBeenCalledTimes(1);
    });
  });

  it('allows optional preferences to be skipped and uses the backend coaching default', async () => {
    const submitOnboarding = jest.fn(async (_request: OnboardingRequest) => ({
      user_id: 'user-1',
      onboarding_completed: true,
      profile_version: 1,
      coaching_style_code: 'SUPPORTIVE',
      ai_trial_started_at: '2026-08-18T00:00:00+09:00',
      ai_trial_ends_at: '2026-09-17T00:00:00+09:00',
      premium_status_code: 'TRIAL',
      created_at: '2026-08-18T00:00:00+09:00',
      updated_at: '2026-08-18T00:00:00+09:00',
    }));

    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps({ selectOptionalPreferences: false });
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      const request = submitOnboarding.mock.calls[0]?.[0];
      expect(request).toEqual(
        expect.objectContaining({
          preferred_exercise_type_codes: [],
          attention_area_codes: [],
          preferred_location_code: 'HOME',
        }),
      );
      expect(request).not.toHaveProperty('coaching_style_code');
      expect(request).not.toHaveProperty('equipment_codes');
    });
  });

  it('only offers home and gym as available workout locations', async () => {
    const submitOnboarding = jest.fn(async (_request: OnboardingRequest) =>
      completedOnboarding(),
    );
    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps({
      selectLocations: () => {
        expect(screen.queryByText('야외')).not.toBeOnTheScreen();
        fireEvent.press(screen.getByText('집'));
        fireEvent.press(screen.getByText('헬스장'));
        fireEvent.press(
          screen.getByRole('button', { name: '대표 운동 장소: 헬스장' }),
        );
      },
    });
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(submitOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({
          available_location_codes: ['HOME', 'GYM'],
          preferred_location_code: 'GYM',
        }),
      );
    });
  });

  it('returns to the field step when the server reports an onboarding field error', async () => {
    const submitOnboarding = jest.fn(async () => {
      throw new ApiError({
        kind: 'validation',
        code: 'INVALID_REQUEST',
        status: 422,
        message: '닉네임을 다시 확인해주세요.',
        details: [{ field: 'body.nickname', type: 'string_too_long' }],
      });
    });

    render(
      <OnboardingScreen
        api={stubApi({ submitOnboarding })}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );

    fillRequiredOnboardingSteps();
    acceptRequiredConsents();
    fireEvent.press(screen.getByText('시작하기'));

    await waitFor(() => {
      expect(screen.getByText('1 / 11')).toBeOnTheScreen();
      expect(screen.getByText('닉네임을 다시 확인해주세요.')).toBeOnTheScreen();
    });
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
  it('shows the room and its mini-game collection', async () => {
    const onNavigate = jest.fn();
    render(
      <MascotHouseScreen
        api={stubApi({
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
        now={new Date('2026-08-22T10:00:00+09:00')}
        onNavigate={onNavigate}
        timeZone="Asia/Seoul"
      />,
    );

    expect(await screen.findByText('끼끼와 놀기')).toBeTruthy();
    expect(screen.getByText('바나나 받기')).toBeTruthy();
    expect(screen.queryByText('주 3회 운동하기')).toBeNull();
    expect(screen.queryByText('0 / 3 회')).toBeNull();
    expect(screen.getByTestId('house-scene')).toBeTruthy();

    // 홈 is reached from the tab bar; the screen has no duplicate corner button.
    expect(screen.queryByLabelText('홈으로')).toBeNull();
    expect(screen.queryByLabelText('설정')).toBeNull();
    fireEvent.press(screen.getByLabelText('홈'));
    expect(onNavigate).toHaveBeenCalledWith('home');
  });

  it('exposes every tab, including the mascot house', async () => {
    render(
      <MascotHouseScreen
        api={stubApi({
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
