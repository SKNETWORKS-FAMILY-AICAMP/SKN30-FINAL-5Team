import type { Api } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import type {
  DailyContextResponse,
  MeResponse,
  RoutineResponse,
  WeekResponse,
} from '../../api/types';

export const TODAY_PREVIEW_OPTIONS = [
  { id: 'loading', label: '로딩' },
  { id: 'pre-checkin', label: '체크인 전' },
  { id: 'checked-in', label: '체크인 후' },
  { id: 'empty', label: '빈 상태' },
  { id: 'error', label: '오류' },
  { id: 'permission', label: '권한 없음' },
  { id: 'rest', label: '휴식' },
] as const;

export type TodayPreviewState = (typeof TODAY_PREVIEW_OPTIONS)[number]['id'];

const ROUTINE: RoutineResponse = {
  id: 'routine-preview',
  version: 1,
  goal_code: 'GENERAL_FITNESS',
  status_code: 'ACTIVE',
  effective_from: '2026-08-18',
  catalog_version: 'preview',
  days: [
    {
      id: 'routine-day-preview',
      sequence: 1,
      title: '전신 기본 루틴',
      training_type_code: 'STRENGTH',
      body_focus_code: 'FULL_BODY',
      requested_duration_minutes: 30,
      estimated_duration_seconds: 1800,
      estimated_calories_burned: null,
      items: [],
    },
  ],
  created_at: '2026-08-18T00:00:00+09:00',
};

function dailyContext(localDate: string): DailyContextResponse {
  return {
    id: 'daily-context-preview',
    local_date: localDate,
    context_version: 1,
    fatigue_level_code: 'MODERATE',
    requested_duration_minutes: 30,
    duration_adjustment_source_code: 'PROFILE',
    location_code: 'HOME',
    sleep_minutes: 420,
    discomforts: [],
    adverse_reaction_codes: [],
    created_at: `${localDate}T08:00:00+09:00`,
    updated_at: `${localDate}T08:00:00+09:00`,
  };
}

const WEEK: WeekResponse = {
  week_id: 'week-preview',
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

/** Enough of `/me` for the home screen's greeting and profile defaults. */
export const PREVIEW_ME: MeResponse = {
  user_id: 'user-preview',
  status_code: 'ACTIVE',
  onboarding_completed: true,
  premium_status_code: 'TRIAL',
  ai_trial_started_at: '2026-08-01T00:00:00+09:00',
  ai_trial_ends_at: '2026-08-31T00:00:00+09:00',
  profile: {
    nickname: '미리보기',
    age: null,
    primary_goal_code: 'GENERAL_FITNESS',
    experience_level_code: 'BEGINNER',
    timezone: 'Asia/Seoul',
    preferred_location_code: 'HOME',
    available_location_codes: ['HOME', 'GYM'],
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

function previewError(kind: 'network' | 'notFound' | 'permission'): ApiError {
  if (kind === 'notFound') {
    return new ApiError({
      kind,
      code: 'NOT_FOUND',
      status: 404,
      message: '요청한 정보를 찾을 수 없습니다.',
    });
  }

  if (kind === 'permission') {
    return new ApiError({
      kind,
      code: 'ACCESS_DENIED',
      status: 403,
      message: '접근할 권한이 없습니다.',
    });
  }

  return new ApiError({
    kind,
    code: 'NETWORK_UNAVAILABLE',
    status: 0,
    message: '서버에 연결하지 못했습니다. 네트워크를 확인해주세요.',
  });
}

/**
 * Development-only server responses for visually checking the API-backed
 * Today screen. The fixture chooses response shapes, never workout decisions.
 */
export function createTodayPreviewApi(state: TodayPreviewState): Api {
  const api: Pick<
    Api,
    'createRoutine' | 'getCurrentRoutine' | 'getDailyContext' | 'getWeek'
  > = {
    async getWeek() {
      if (state === 'loading') {
        return new Promise<WeekResponse>(() => undefined);
      }
      return WEEK;
    },
    async createRoutine(body) {
      return { ...ROUTINE, effective_from: body.effective_from };
    },
    async getCurrentRoutine() {
      if (state === 'loading') {
        return new Promise<RoutineResponse>(() => undefined);
      }
      if (state === 'empty') {
        throw previewError('notFound');
      }
      if (state === 'error') {
        throw previewError('network');
      }
      if (state === 'permission') {
        throw previewError('permission');
      }
      return ROUTINE;
    },
    async getDailyContext(localDate) {
      if (state === 'pre-checkin' || state === 'empty') {
        throw previewError('notFound');
      }
      return dailyContext(localDate);
    },
  };

  return api as Api;
}
