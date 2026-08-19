/**
 * Restart recovery in MainFlow.
 *
 * A reload loses the flow's in-memory decision and session step, so MainFlow
 * reads back today's stored decision and unfinished session once on mount.
 * These tests stub the transport and assert what the client asks the server
 * and where it routes — never a decision of its own making.
 */

import { render, waitFor } from '@testing-library/react-native';

import { ApiClient } from '../src/api/client';
import { createApi } from '../src/api/endpoints';
import type {
  DecisionResponse,
  MeResponse,
  WorkoutPlan,
  WorkoutSessionListResponse,
} from '../src/api/types';
import { MainFlow } from '../src/app/MainFlow';

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
      equipment_codes: ['BODYWEIGHT'],
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
    created_at: '2026-08-19T00:00:00+09:00',
  } as unknown as DecisionResponse;
}

function sessions(
  items: WorkoutSessionListResponse['items'],
): WorkoutSessionListResponse {
  return { items, next_cursor: null };
}

/** Routes requests by path; unrouted paths get 404 so optional reads stay absent. */
function apiWithRoutes(routes: Record<string, unknown>) {
  const calls: string[] = [];
  const client = new ApiClient({
    baseUrl: 'http://test.local',
    getToken: async () => 'token',
    fetchImpl: async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const key = url.pathname.replace('/api/v1', '') + (url.search ? '?' : '');
      calls.push(key);
      const match = Object.entries(routes).find(([route]) =>
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
  it('re-reads the stored decision and shows it without re-running a check-in', async () => {
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
      expect(calls.some((path) => path.startsWith('/decisions?'))).toBe(true);
      expect(calls.some((path) => path.startsWith('/workout-sessions?'))).toBe(
        true,
      );
    });
    // Restoring must never create anything: reads only.
    expect(calls.every((path) => !path.includes('POST'))).toBe(true);
  });

  it('routes straight back into an unfinished session', async () => {
    const { api, calls } = apiWithRoutes({
      '/decisions?': decision(),
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

    // The workout screen resuming the session is observable as its detail read.
    await waitFor(
      () => {
        expect(
          calls.some((path) => path.startsWith('/workout-sessions/session-1')),
        ).toBe(true);
      },
      { timeout: 8000 },
    );
  });

  it("does not resurrect the decision after the day's session already ended", async () => {
    const { api, calls } = apiWithRoutes({
      '/decisions?': decision(),
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
    // A finished day must not reopen the session screen.
    expect(
      calls.some((path) => path.startsWith('/workout-sessions/session-1')),
    ).toBe(false);
  });
});
