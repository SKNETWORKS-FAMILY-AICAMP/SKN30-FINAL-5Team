import type { Api } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import type {
  DailyContextResponse,
  DecisionResponse,
  MeResponse,
  RoutineResponse,
  WeekResponse,
  WorkoutPlan,
} from '../../api/types';
import type { PreviousHomeScreenProps } from '../home/PreviousHomeScreen';

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
      items: [
        {
          id: 'routine-item-squat',
          exercise_id: 'exercise-squat',
          exercise_name: '의자 스쿼트',
          sequence: 1,
          phase_code: 'MAIN',
          tier_code: 'CORE',
          sets: 3,
          reps: 10,
          work_seconds_per_set: null,
          rest_seconds_per_set: 60,
          instruction_available: true,
        },
        {
          id: 'routine-item-pushup',
          exercise_id: 'exercise-pushup',
          exercise_name: '벽 푸시업',
          sequence: 2,
          phase_code: 'MAIN',
          tier_code: 'CORE',
          sets: 3,
          reps: 10,
          work_seconds_per_set: null,
          rest_seconds_per_set: 60,
          instruction_available: true,
        },
        {
          id: 'routine-item-march',
          exercise_id: 'exercise-march',
          exercise_name: '제자리 걷기',
          sequence: 3,
          phase_code: 'COOLDOWN',
          tier_code: 'SUPPORT',
          sets: 1,
          reps: null,
          work_seconds_per_set: 300,
          rest_seconds_per_set: 0,
          instruction_available: true,
        },
      ],
    },
  ],
  created_at: '2026-08-18T00:00:00+09:00',
};

const PLAN: WorkoutPlan = {
  plan_id: 'plan-preview',
  action_code: 'KEEP',
  training_type_code: 'STRENGTH',
  body_focus_code: 'FULL_BODY',
  requested_duration_minutes: 30,
  estimated_duration_seconds: 1800,
  estimated_calories_burned: null,
  setup_seconds: 0,
  warmup_seconds: 120,
  cooldown_seconds: 60,
  items:
    ROUTINE.days[0]?.items.map((item) => ({
      plan_item_id: `plan-${item.id}`,
      exercise_id: item.exercise_id,
      exercise_name: item.exercise_name,
      sequence: item.sequence,
      tier_code: item.tier_code,
      sets: item.sets,
      reps: item.reps,
      work_seconds: item.work_seconds_per_set ?? 60,
      rest_seconds: item.rest_seconds_per_set,
      transition_seconds: 15,
      estimated_item_seconds: 540,
      instruction_available: item.instruction_available,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    })) ?? [],
};

const DECISION: DecisionResponse = {
  decision_id: 'decision-preview',
  local_date: '2026-08-18',
  status_code: 'COMPLETED',
  safety_status_code: 'PASS',
  action_code: 'KEEP',
  requested_duration_minutes: 30,
  duration_adjustment_source_code: 'PROFILE',
  final_plan: PLAN,
  options: [
    {
      option_id: 'option-routine-preview',
      option_code: 'FINAL_ROUTINE',
      action_code: 'KEEP',
      plan_id: PLAN.plan_id,
      selectable: true,
      blocked_reason_code: null,
    },
    {
      option_id: 'option-rest-preview',
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
  root_decision_id: 'decision-preview',
  parent_decision_id: null,
  regeneration_sequence: 0,
  meaningful_difference_codes: null,
  created_at: '2026-08-18T08:05:00+09:00',
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

/**
 * The previous API-driven Home presentation, kept only for visual comparison
 * with the current Home transcription. These are typed server-shaped fixtures;
 * no request leaves the preview gallery.
 */
export function previousHomePreviewProps(
  state: TodayPreviewState,
): PreviousHomeScreenProps {
  const status =
    state === 'loading'
      ? 'loading'
      : state === 'error' || state === 'permission'
        ? 'error'
        : 'ready';
  const hasRoutine = state !== 'empty';
  const hasContext = state === 'checked-in' || state === 'rest';

  return {
    nickname: PREVIEW_ME.profile?.nickname ?? '미리보기',
    localDate: '2026-08-18',
    status,
    errorMessage:
      state === 'error'
        ? '서버에 연결하지 못했습니다. 네트워크를 확인해주세요.'
        : state === 'permission'
          ? '접근할 권한이 없습니다.'
          : undefined,
    permissionDenied: state === 'permission',
    routine: hasRoutine ? ROUTINE : null,
    context: hasContext ? dailyContext('2026-08-18') : null,
    decision: state === 'checked-in' ? DECISION : null,
    week: WEEK,
    planRevision: null,
    restToday: state === 'rest',
    defaultDurationMinutes: 30,
    locationCodes: ['HOME', 'GYM'],
    busy: null,
    onRetry: () => undefined,
    onCreateRoutine: () => undefined,
    onSubmitCheckin: () => undefined,
    onStartWorkout: () => undefined,
    onChooseRest: () => undefined,
    onRequestAiRevision: () => undefined,
    onSubmitUserEdits: () => undefined,
    onNavigateTab: () => undefined,
    onOpenCalendar: () => undefined,
  };
}
