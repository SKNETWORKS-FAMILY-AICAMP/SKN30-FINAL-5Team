/**
 * Restart recovery in MainFlow.
 *
 * A reload loses the flow's in-memory decision and session step, so MainFlow
 * reads back today's stored decision and unfinished session on mount and when
 * the user returns to Home.
 * These tests stub the transport and assert what the client asks the server
 * and where it routes — never a decision of its own making.
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import { ApiClient } from '../src/api/client';
import { createApi, type Api } from '../src/api/endpoints';
import { ApiError } from '../src/api/errors';
import type {
  DailyRewardClaimResponse,
  DecisionResponse,
  HomeStateResponse,
  MeResponse,
  NotificationListResponse,
  NotificationResponse,
  RoutineResponse,
  WeeklyPlanRevisionResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
  WorkoutSessionListResponse,
} from '../src/api/types';
import { weekStartString } from '../src/api/useAsync';
import { MainFlow } from '../src/app/MainFlow';
import { homePreviewProps } from '../src/features/preview/homePreview';

const LOCAL_DATE = new Date().toISOString().slice(0, 10);

function me(): MeResponse {
  return {
    user_id: 'user-1',
    status_code: 'ACTIVE',
    onboarding_completed: true,
    consent_policy_version: 'v1',
    code_set_version: 'v1',
    profile_version: 1,
    profile: {
      nickname: '헬끼',
      age: null,
      primary_goal_code: 'GENERAL_FITNESS',
      experience_level_code: 'BEGINNER',
      timezone: 'Asia/Seoul',
      preferred_location_code: 'HOME',
      default_requested_duration_minutes: 30,
      desired_weekly_workout_count: 3,
      coaching_style_code: 'SUPPORTIVE',
      attention_area_codes: [],
      preferred_exercise_type_codes: [],
      available_location_codes: ['HOME'],
    },
  } as unknown as MeResponse;
}

function plan(): WorkoutPlan {
  return {
    plan_id: 'plan-1',
    action_code: 'KEEP',
    training_type_code: 'STRENGTH',
    body_focus_code: null,
    requested_duration_minutes: 30,
    estimated_duration_seconds: 1800,
    estimated_calories_burned: null,
    setup_seconds: 0,
    warmup_seconds: 60,
    cooldown_seconds: 60,
    items: [
      {
        plan_item_id: 'item-1',
        exercise_id: 'ex-1',
        exercise_name: '스쿼트',
        sequence: 1,
        tier_code: 'CORE',
        sets: 1,
        reps: 10,
        work_seconds: 1620,
        rest_seconds: 0,
        transition_seconds: 60,
        estimated_item_seconds: 1680,
        instruction_available: false,
        mascot_animation_asset_key: null,
        replacement_of_exercise_id: null,
      },
    ],
  };
}

function decision(): DecisionResponse {
  return {
    decision_id: 'decision-1',
    local_date: LOCAL_DATE,
    status_code: 'COMPLETED',
    safety_status_code: 'PASS',
    action_code: 'KEEP',
    requested_duration_minutes: 30,
    duration_adjustment_source_code: 'PROFILE',
    final_plan: plan(),
    options: [],
    reason_codes: [],
    summary: '오늘 조건에서는 준비된 루틴을 그대로 진행합니다.',
    generation_mode_code: 'REGENERATED',
    decision_engine_code: 'LLM_MULTI_AGENT',
    root_decision_id: 'decision-root',
    parent_decision_id: 'decision-root',
    regeneration_sequence: 1,
    meaningful_difference_codes: ['CORE_EXERCISE_CHANGED'],
    created_at: '2026-08-19T00:00:00+09:00',
  } as unknown as DecisionResponse;
}

function sessions(
  items: WorkoutSessionListResponse['items'],
): WorkoutSessionListResponse {
  return { items, next_cursor: null };
}

function sessionDetail(
  overrides: Partial<WorkoutSessionDetailResponse> = {},
): WorkoutSessionDetailResponse {
  return {
    session_id: 'session-1',
    local_date: LOCAL_DATE,
    status_code: 'IN_PROGRESS',
    completed_item_count: 0,
    total_item_count: 1,
    requested_duration_minutes: 30,
    items: [
      {
        plan_item_id: 'item-1',
        exercise_id: 'ex-1',
        exercise_name: '스쿼트',
        status_code: 'PENDING',
        sets: 1,
        reps: 10,
        work_seconds_per_set: 1620,
        completed_at: null,
      },
    ],
    completed_plan_item_ids: [],
    current_plan_item_id: 'item-1',
    feedback: null,
    not_completed_reason_code: null,
    started_at: '2026-08-19T09:00:00+09:00',
    finished_at: null,
    ...overrides,
  };
}

function homeState(
  overrides: Partial<HomeStateResponse> = {},
): HomeStateResponse {
  const storedDecision = decision();
  return {
    local_date: LOCAL_DATE,
    decision: storedDecision,
    final_plan: storedDecision.final_plan,
    workout_session: null,
    ...overrides,
  };
}

function routine(): RoutineResponse {
  return {
    id: 'routine-1',
    version: 1,
    goal_code: 'GENERAL_FITNESS',
    status_code: 'ACTIVE',
    effective_from: LOCAL_DATE,
    catalog_version: 'catalog-v1',
    days: [],
    created_at: '2026-08-19T00:00:00+09:00',
  };
}

function notification(
  overrides: Partial<NotificationResponse> = {},
): NotificationResponse {
  return {
    notification_id: 'notification-1',
    type: 'KIKKI_RETURN',
    title: '끼끼가 기다리고 있어요',
    message: '끼끼의 집에 들러주세요.',
    created_at: '2026-09-04T09:00:00+09:00',
    read_at: null,
    is_read: false,
    action_type: 'OPEN_KIKKI_HOME',
    payload: {},
    ...overrides,
  };
}

function latestPlanRevision(): WeeklyPlanRevisionResponse {
  return {
    revision_id: 'revision-2',
    week_start: '2026-08-17',
    week_end: '2026-08-23',
    revision_sequence: 2,
    ai_revision_count: 1,
    source_code: 'AI',
    source_weekly_report_id: null,
    safety_status_code: 'PASS',
    routine: routine(),
    selected_location_code: 'HOME',
    finalized: true,
    finalized_at: '2026-08-19T00:00:00+09:00',
    revision_reason_codes: ['REVISION_ALLOWED'],
    finalization_reason_codes: ['FINALIZE_ALLOWED'],
    created_at: '2026-08-19T00:00:00+09:00',
  };
}

/** Routes requests by path; unrouted paths get 404 so optional reads stay absent. */
function apiWithRoutes(routes: Record<string, unknown>) {
  const calls: string[] = [];
  const configuredRoutes = {
    '/home?': homeState(),
    '/routines/current?': routine(),
    '/workout-sessions?': sessions([]),
    ...routes,
  };
  const client = new ApiClient({
    baseUrl: 'http://test.local',
    getToken: async () => 'token',
    fetchImpl: async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const key = url.pathname.replace('/api/v1', '') + (url.search ? '?' : '');
      calls.push(key);
      const match = Object.entries(configuredRoutes).find(([route]) =>
        key.startsWith(route),
      );
      if (!match) {
        return new Response(
          JSON.stringify({
            error: { code: 'NOT_FOUND', message: '', request_id: 't' },
          }),
          { status: 404, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify(match[1]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  return { api: createApi(client), calls };
}

describe('MainFlow restart recovery', () => {
  it.each([0, 1])(
    'stops a session with %i completed blocks without ending it, then asks how it went',
    async (completedCount) => {
      const storedPlan = plan();
      storedPlan.items.push({
        ...storedPlan.items[0]!,
        plan_item_id: 'item-2',
        sequence: 2,
      });
      const initial = sessionDetail();
      const storedSession = sessionDetail({
        total_item_count: 2,
        completed_item_count: completedCount,
        items: [
          {
            ...initial.items[0]!,
            status_code: completedCount ? 'COMPLETED' : 'PENDING',
          },
          {
            ...initial.items[0]!,
            plan_item_id: 'item-2',
            status_code: 'PENDING',
          },
        ],
      });
      let stopped = false;
      const { api } = apiWithRoutes({});
      const stopSession = jest.fn<
        ReturnType<Api['stopSession']>,
        Parameters<Api['stopSession']>
      >(async () => {
        stopped = true;
        return {
          session_id: 'session-1',
          completion_code: null,
          execution_state_code: 'STOPPED_RESUMABLE',
          stop_reason_code: 'RESUME_LATER',
          is_resumable: true,
          accumulated_progress_seconds: 0,
          accumulated_rest_seconds: 0,
          accumulated_paused_seconds: 0,
        };
      });
      const submitFeedback = jest.fn<
        ReturnType<Api['submitFeedback']>,
        Parameters<Api['submitFeedback']>
      >(async () => ({
        session_id: 'session-1',
        session_status_code: 'PARTIAL',
        created_at: new Date().toISOString(),
        guidance_code: null,
        guidance: null,
        pressure_notifications_allowed: true,
      }));
      const markNotCompleted = jest.fn<
        ReturnType<Api['markNotCompleted']>,
        Parameters<Api['markNotCompleted']>
      >(async (_id, endedAt, reason) => ({
        session_id: 'session-1',
        status_code: 'NOT_COMPLETED',
        reason_code: reason,
        ended_at: endedAt,
      }));
      const finishSession = jest.fn<
        ReturnType<Api['finishSession']>,
        Parameters<Api['finishSession']>
      >(async (_id, endedAt) => ({
        session_id: 'session-1',
        status_code: 'PARTIAL',
        completed_item_count: 1,
        total_item_count: 2,
        actual_elapsed_seconds: 0,
        estimated_calories_burned: null,
        ended_at: endedAt,
      }));
      const liveApi: Api = {
        ...api,
        getHomeState: async () =>
          homeState({
            decision: { ...decision(), final_plan: storedPlan },
            final_plan: storedPlan,
            // A stop no longer ends the session, so Home keeps reading it as
            // IN_PROGRESS and keeps offering 이어하기.
            workout_session: { ...storedSession, status_code: 'IN_PROGRESS' },
          }),
        getWorkoutSession: async () => storedSession,
        recordTimerEvent: async () => ({ event_id: 'timer-1' }),
        markNotCompleted,
        stopSession,
        finishSession,
        submitFeedback,
      };
      render(
        <MainFlow
          api={liveApi}
          me={me()}
          onRefreshMe={async () => undefined}
          onSignOut={() => {}}
        />,
      );
      fireEvent.press(await screen.findByRole('button', { name: '이어하기' }));
      await waitFor(() =>
        expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
      );
      fireEvent.press(screen.getByRole('button', { name: '운동 중단' }));
      fireEvent.press(screen.getByRole('radio', { name: '시간이 부족해요.' }));
      fireEvent.press(
        screen.getByRole('button', { name: '이 사유로 중단하기' }),
      );
      // How many blocks were checked no longer decides the path: both go
      // through the resumable stop, and neither closes the session.
      const save = await screen.findByRole('button', {
        name: '피드백 저장하고 홈으로',
      });
      expect(stopSession).toHaveBeenCalledTimes(1);
      expect(stopSession).toHaveBeenCalledWith(
        'session-1',
        expect.any(String),
        'TIME_SHORTAGE',
      );
      expect(markNotCompleted).not.toHaveBeenCalled();
      expect(finishSession).not.toHaveBeenCalled();
      expect(save).toBeDisabled();

      fireEvent.press(screen.getByRole('radio', { name: '적당했어요' }));
      expect(save).toBeEnabled();
      fireEvent.press(save);
      await waitFor(() => expect(submitFeedback).toHaveBeenCalledTimes(1));

      // Back on Home the session is still there to continue.
      expect(await screen.findByTestId('home-screen')).toBeOnTheScreen();
      expect(stopped).toBe(true);
      expect(
        await screen.findByRole('button', { name: '이어하기' }),
      ).toBeOnTheScreen();
    },
  );

  it.each(['HOME', 'GYM'])(
    'preserves %s equipment guidance when resuming through MainFlow',
    async (locationCode) => {
      const storedPlan = plan();
      storedPlan.items[0]!.instruction_available = true;
      const { api } = apiWithRoutes({
        '/home?': homeState({
          decision: { ...decision(), final_plan: storedPlan },
          final_plan: storedPlan,
          workout_session: sessionDetail(),
        }),
        '/daily-contexts/': {
          ...homePreviewProps('routine').context!,
          location_code: locationCode,
        },
        '/workout-sessions/session-1': sessionDetail(),
        '/exercises/ex-1/variants': {
          source_exercise_id: 'ex-1',
          source_required_equipment_codes: [],
          items: [],
          catalog_version: 'test-v1',
          alternative_set_version: null,
        },
        '/exercises/ex-1': {
          exercise_id: 'ex-1',
          exercise_name: '스쿼트',
          training_type_code: 'STRENGTH',
          body_focus_code: null,
          primary_body_area_codes: ['HIP'],
          instruction_summary: '천천히 앉았다가 일어나요.',
          form_cues: [],
          household_equipment_guides: [
            {
              equipment_code: 'CHAIR',
              proposal_ko: '흔들리지 않는 의자를 준비해요.',
              examples_ko: [],
              cautions_ko: [],
            },
          ],
          gym_equipment_starting_guides: [
            {
              equipment_code: 'BARBELL',
              proposal_ko: '가벼운 바부터 동작을 확인해요.',
              examples_ko: [],
              cautions_ko: [],
            },
          ],
          media_asset_key: null,
          media_url: null,
          mascot_animation_asset_key: null,
          instruction_content_version: 'test-v1',
        },
      });

      render(
        <MainFlow
          api={api}
          me={me()}
          onRefreshMe={async () => undefined}
          onSignOut={() => {}}
        />,
      );
      await screen.findByRole('button', { name: '이어하기' });
      fireEvent.press(screen.getByRole('button', { name: '이어하기' }));
      await screen.findByTestId('workout-header-top-row');
      await waitFor(() =>
        expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
      );
      fireEvent.press(screen.getByRole('button', { name: '자세 보기' }));
      const expected =
        locationCode === 'HOME'
          ? 'household-equipment-guides'
          : 'gym-equipment-starting-guides';
      const excluded =
        locationCode === 'HOME'
          ? 'gym-equipment-starting-guides'
          : 'household-equipment-guides';
      expect(await screen.findByTestId(expected)).toBeOnTheScreen();
      expect(screen.queryByTestId(excluded)).toBeNull();
    },
  );

  it('restores the latest weekly revision when the read capability is available', async () => {
    const { api } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });
    const getLatestWeeklyPlanRevision = jest.fn(async () =>
      latestPlanRevision(),
    );
    const capableApi: Api = { ...api, getLatestWeeklyPlanRevision };

    render(
      <MainFlow
        api={capableApi}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(getLatestWeeklyPlanRevision).toHaveBeenCalledWith(
        weekStartString(new Date(), 'Asia/Seoul'),
        expect.any(AbortSignal),
      );
    });
    expect(await screen.findByText('다른 루틴 · 1회 남음')).toBeOnTheScreen();
  }, 20_000);

  it('restores one consistent Home snapshot without composing legacy reads', async () => {
    const { api, calls } = apiWithRoutes({
      '/decisions?': decision(),
      '/workout-sessions?': sessions([]),
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(calls.some((path) => path.startsWith('/home?'))).toBe(true);
    });
    expect(calls.some((path) => path.startsWith('/decisions?'))).toBe(false);
    expect(
      calls.some((path) => path.startsWith('/workout-sessions/session-')),
    ).toBe(false);
  });

  it('re-reads the stored decision whenever the user returns to Home', async () => {
    const { api, calls } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    const homeReadCount = () =>
      calls.filter((path) => path.startsWith('/home?')).length;
    await waitFor(() => expect(homeReadCount()).toBe(1));

    fireEvent.press(screen.getAllByRole('tab')[1]!);
    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(4));
    fireEvent.press(screen.getAllByRole('tab')[0]!);

    await waitFor(() => expect(homeReadCount()).toBe(2));
  });

  it('treats an aggregate response with no decision or session as an empty Home', async () => {
    const { api, calls } = apiWithRoutes({
      '/home?': homeState({
        decision: null,
        final_plan: null,
        workout_session: null,
      }),
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    expect(
      await screen.findByRole('button', { name: '운동 체크인' }),
    ).toBeOnTheScreen();
    expect(calls.some((path) => path.startsWith('/decisions?'))).toBe(false);
  });

  it('retries a transient aggregate failure from the Home error state', async () => {
    const { api } = apiWithRoutes({});
    const getHomeState = jest
      .fn<Promise<HomeStateResponse>, [string, AbortSignal?]>()
      .mockRejectedValueOnce(
        new ApiError({
          kind: 'unavailable',
          code: 'SERVICE_UNAVAILABLE',
          status: 503,
          message: '잠시 후 다시 시도해주세요.',
        }),
      )
      .mockResolvedValueOnce(homeState());

    render(
      <MainFlow
        api={{ ...api, getHomeState }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '다시 준비하기' }),
    );
    await waitFor(() => expect(getHomeState).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText('컨디션에 맞춘 운동을 준비했어요'),
    ).toBeOnTheScreen();
  });

  it('shows aggregate permission denial without a retry action', async () => {
    const { api } = apiWithRoutes({});
    const getHomeState = jest.fn(async () => {
      throw new ApiError({
        kind: 'permission',
        code: 'ACCOUNT_DISABLED',
        status: 403,
        message: '이 계정으로는 접근할 수 없습니다.',
      });
    });

    render(
      <MainFlow
        api={{ ...api, getHomeState }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    expect(
      await screen.findByText('오늘의 운동 정보에 접근할 권한이 없어요.'),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '다시 준비하기' })).toBeNull();
  });

  it('restores an unfinished session on Home and resumes on demand', async () => {
    const { api, calls } = apiWithRoutes({
      '/home?': homeState({ workout_session: sessionDetail() }),
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([
        {
          session_id: 'session-1',
          local_date: LOCAL_DATE,
          status_code: 'IN_PROGRESS',
          completed_item_count: 0,
          total_item_count: 1,
          requested_duration_minutes: 30,
          training_type_code: 'STRENGTH',
          not_completed_reason_code: null,
          started_at: '2026-08-19T09:00:00+09:00',
          finished_at: null,
        },
      ]),
      '/workout-sessions/session-1': {
        session_id: 'session-1',
        local_date: LOCAL_DATE,
        status_code: 'IN_PROGRESS',
        completed_item_count: 0,
        total_item_count: 1,
        requested_duration_minutes: 30,
        items: [
          {
            plan_item_id: 'item-1',
            exercise_id: 'ex-1',
            exercise_name: '스쿼트',
            status_code: 'PENDING',
            sets: 1,
            reps: 10,
            work_seconds_per_set: 1620,
            completed_at: null,
          },
        ],
        feedback: null,
        not_completed_reason_code: null,
        started_at: '2026-08-19T09:00:00+09:00',
        finished_at: null,
      },
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    // Home reads progress but does not reopen the workout without a user action.
    await waitFor(() => {
      expect(calls.some((path) => path.startsWith('/home?'))).toBe(true);
    });
    const detailReadCount = () =>
      calls.filter((path) => path.startsWith('/workout-sessions/session-1'))
        .length;
    expect(detailReadCount()).toBe(0);
    const beforeResume = detailReadCount();
    fireEvent.press(await screen.findByRole('button', { name: '이어하기' }));
    await waitFor(() =>
      expect(detailReadCount()).toBeGreaterThan(beforeResume),
    );
  }, 20_000);

  it('leaves the session resumable after the user stops with a reason', async () => {
    // Confirming a stop used to close the session, which is what took 이어하기
    // away. It now goes through `/stop`, and the terminal endpoints stay
    // untouched -- checked against the real client rather than a stub, because
    // the bug was in which endpoint the screen picked.
    const { api, calls } = apiWithRoutes({
      '/home?': homeState({ workout_session: sessionDetail() }),
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([
        {
          session_id: 'session-1',
          local_date: LOCAL_DATE,
          status_code: 'IN_PROGRESS',
          completed_item_count: 0,
          total_item_count: 1,
          requested_duration_minutes: 30,
          training_type_code: 'STRENGTH',
          not_completed_reason_code: null,
          started_at: '2026-08-19T09:00:00+09:00',
          finished_at: null,
        },
      ]),
      '/workout-sessions/session-1/stop': {
        session_id: 'session-1',
        execution_state_code: 'STOPPED_RESUMABLE',
        is_resumable: true,
        completion_code: null,
        stop_reason_code: 'TIME_SHORTAGE',
        accumulated_progress_seconds: 0,
        accumulated_rest_seconds: 0,
        accumulated_paused_seconds: 0,
      },
      '/workout-sessions/session-1': sessionDetail(),
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    fireEvent.press(await screen.findByRole('button', { name: '이어하기' }));
    await screen.findByTestId('workout-header-top-row');
    await waitFor(() =>
      expect(screen.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 중단' }));
    fireEvent.press(screen.getByRole('radio', { name: '시간이 부족해요.' }));
    fireEvent.press(screen.getByRole('button', { name: '이 사유로 중단하기' }));

    // Asked how it went, and the session was never closed to ask.
    await screen.findByRole('button', { name: '피드백 저장하고 홈으로' });
    await waitFor(() =>
      expect(calls.some((path) => path.includes('/stop'))).toBe(true),
    );
    expect(
      calls.some(
        (path) => path.includes('/not-completed') || path.includes('/finish'),
      ),
    ).toBe(false);
    expect(
      screen.queryByRole('button', { name: '나중에 이어하기' }),
    ).toBeNull();
  }, 20_000);

  it("keeps the day's completed routine visible without reopening it", async () => {
    const { api, calls } = apiWithRoutes({
      '/home?': homeState({
        workout_session: sessionDetail({
          status_code: 'COMPLETED',
          completed_item_count: 1,
          items: [
            {
              ...sessionDetail().items[0]!,
              status_code: 'COMPLETED',
              completed_at: '2026-08-19T09:30:00+09:00',
            },
          ],
          finished_at: '2026-08-19T09:30:00+09:00',
        }),
      }),
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([
        {
          session_id: 'session-1',
          local_date: LOCAL_DATE,
          status_code: 'COMPLETED',
          completed_item_count: 1,
          total_item_count: 1,
          requested_duration_minutes: 30,
          training_type_code: 'STRENGTH',
          not_completed_reason_code: null,
          started_at: '2026-08-19T09:00:00+09:00',
          finished_at: '2026-08-19T09:30:00+09:00',
        },
      ]),
      '/workout-sessions/session-1': {
        session_id: 'session-1',
        local_date: LOCAL_DATE,
        status_code: 'COMPLETED',
        completed_item_count: 1,
        total_item_count: 1,
        requested_duration_minutes: 30,
        items: [
          {
            plan_item_id: 'item-1',
            exercise_id: 'ex-1',
            exercise_name: '스쿼트',
            status_code: 'COMPLETED',
            sets: 1,
            reps: 10,
            work_seconds_per_set: 1620,
            completed_at: '2026-08-19T09:30:00+09:00',
          },
        ],
        feedback: null,
        not_completed_reason_code: null,
        started_at: '2026-08-19T09:00:00+09:00',
        finished_at: '2026-08-19T09:30:00+09:00',
      },
    });

    render(
      <MainFlow
        api={api}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(calls.some((path) => path.startsWith('/workout-sessions?'))).toBe(
        true,
      );
    });
    expect(
      calls.some((path) => path.startsWith('/workout-sessions/session-1')),
    ).toBe(false);
    expect(await screen.findByText('운동 기록')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '이어하기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '세트·횟수 수정' })).toBeNull();
  });

  it('shows unread state, marks the selected notification, re-reads the count and opens the house', async () => {
    const { api } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });
    const item = notification();
    const listNotifications = jest.fn<
      Promise<NotificationListResponse>,
      [AbortSignal?]
    >(async () => ({ items: [item], unread_count: 1 }));
    const markNotificationRead = jest.fn(async () => ({
      ...item,
      is_read: true,
      read_at: '2026-09-04T09:01:00+09:00',
    }));

    render(
      <MainFlow
        api={{ ...api, listNotifications, markNotificationRead }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => expect(listNotifications).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('읽지 않은 알림 있음')).toBeVisible();

    fireEvent.press(screen.getByRole('button', { name: '알림 보기' }));
    fireEvent.press(
      await screen.findByRole('button', {
        name: '끼끼가 기다리고 있어요 알림 확인',
      }),
    );

    await waitFor(() => {
      expect(markNotificationRead).toHaveBeenCalledWith('notification-1');
      expect(listNotifications.mock.calls.length).toBeGreaterThanOrEqual(3);
      expect(
        screen.getByRole('tab', { name: '끼끼의 집' }).props.accessibilityState
          .selected,
      ).toBe(true);
    });
  });

  it('claims the daily reward inside the notification sheet instead of navigating', async () => {
    const { api } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });
    const item = notification({
      type: 'DAILY_REWARD',
      title: '오늘의 바나나가 도착했어요',
      message: '지금 받을 수 있어요.',
      action_type: 'CLAIM_DAILY_REWARD',
    });
    const listNotifications = jest.fn<
      Promise<NotificationListResponse>,
      [AbortSignal?]
    >(async () => ({ items: [item], unread_count: 1 }));
    const markNotificationRead = jest.fn(async () => ({
      ...item,
      is_read: true,
      read_at: '2026-09-04T09:01:00+09:00',
    }));
    const claimed: DailyRewardClaimResponse = {
      balance: 57,
      daily_reward: {
        local_date: LOCAL_DATE,
        reward_amount: 15,
        is_claimable: false,
        is_claimed: true,
        claimed_at: '2026-09-04T09:01:00+09:00',
      },
      transaction: {
        transaction_id: 'transaction-1',
        transaction_type: 'DAILY_REWARD',
        amount: 15,
        balance_after: 57,
        created_at: '2026-09-04T09:01:00+09:00',
      },
    };
    const claimDailyReward = jest.fn(async () => claimed);
    const getRewards = jest.fn(async () => ({
      balance: claimed.balance,
      daily_reward: claimed.daily_reward,
    }));

    render(
      <MainFlow
        api={{
          ...api,
          claimDailyReward,
          getRewards,
          listNotifications,
          markNotificationRead,
        }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => expect(listNotifications).toHaveBeenCalledTimes(1));
    fireEvent.press(screen.getByRole('button', { name: '알림 보기' }));
    fireEvent.press(
      await screen.findByRole('button', {
        name: '오늘의 바나나가 도착했어요 알림 확인',
      }),
    );

    await waitFor(() => {
      expect(markNotificationRead).toHaveBeenCalledWith('notification-1');
      expect(claimDailyReward).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByText('바나나 15개를 받았어요.'),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('notification-popover')).toBeOnTheScreen();
    expect(getRewards).not.toHaveBeenCalled();
    expect(screen.queryByText('바나나 지갑')).toBeNull();
  });

  it('keeps the sheet open with a retryable error when the claim fails', async () => {
    const { api } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });
    const item = notification({
      type: 'DAILY_REWARD',
      title: '오늘의 바나나가 도착했어요',
      message: '지금 받을 수 있어요.',
      action_type: 'CLAIM_DAILY_REWARD',
    });
    const listNotifications = jest.fn<
      Promise<NotificationListResponse>,
      [AbortSignal?]
    >(async () => ({ items: [item], unread_count: 1 }));
    const markNotificationRead = jest.fn(async () => ({
      ...item,
      is_read: true,
      read_at: '2026-09-04T09:01:00+09:00',
    }));
    const claimDailyReward = jest.fn(async () => {
      throw new ApiError({
        kind: 'unavailable',
        code: 'SERVICE_UNAVAILABLE',
        status: 503,
        message: '잠시 후 다시 시도해주세요.',
      });
    });

    render(
      <MainFlow
        api={{
          ...api,
          claimDailyReward,
          listNotifications,
          markNotificationRead,
        }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => expect(listNotifications).toHaveBeenCalledTimes(1));
    fireEvent.press(screen.getByRole('button', { name: '알림 보기' }));
    fireEvent.press(
      await screen.findByRole('button', {
        name: '오늘의 바나나가 도착했어요 알림 확인',
      }),
    );

    await waitFor(() => expect(claimDailyReward).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByRole('button', { name: '다시 불러오기' }),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('notification-popover')).toBeOnTheScreen();
    expect(screen.queryByTestId('notification-notice')).toBeNull();
  });

  it('shows one toast only when a later Home read contains a new unread id', async () => {
    const { api } = apiWithRoutes({
      '/decisions?': decision(),
      '/routines/current?': routine(),
      '/workout-sessions?': sessions([]),
    });
    const first = notification({ notification_id: 'existing' });
    const added = notification({
      notification_id: 'new',
      title: '새 소식',
    });
    const listNotifications = jest
      .fn<Promise<NotificationListResponse>, [AbortSignal?]>()
      .mockResolvedValueOnce({ items: [first], unread_count: 1 })
      .mockResolvedValueOnce({ items: [added, first], unread_count: 2 });

    render(
      <MainFlow
        api={{ ...api, listNotifications }}
        me={me()}
        onRefreshMe={async () => undefined}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => expect(listNotifications).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('끼끼가 소식을 가져왔어요!')).toBeNull();

    fireEvent.press(screen.getByRole('tab', { name: '끼끼의 집' }));
    fireEvent.press(await screen.findByRole('tab', { name: '홈' }));

    expect(
      await screen.findByText('끼끼가 소식을 가져왔어요!'),
    ).toBeOnTheScreen();
    expect(listNotifications).toHaveBeenCalledTimes(2);
  });
});
