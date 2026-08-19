import type { Api } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import type {
  ConsentValues,
  RoutineResponse,
  SafetyEventResponse,
  NotCompletedReasonCode,
  SessionFinishResponse,
  SessionNotCompletedResponse,
  WeekResponse,
  WeeklyReportResponse,
  WorkoutPlan,
} from '../../api/types';
import type { SessionOutcome } from '../workout/SessionScreen';

export const HOUSE_PREVIEW_OPTIONS = [
  { id: 'loaded', label: '루틴 있음' },
  { id: 'empty', label: '루틴 없음' },
  { id: 'error', label: '오류' },
] as const;

export type HousePreviewState = (typeof HOUSE_PREVIEW_OPTIONS)[number]['id'];

export const SESSION_PREVIEW_OPTIONS = [
  { id: 'active', label: '진행 중' },
  { id: 'error', label: '시작 오류' },
] as const;

export type SessionPreviewState =
  (typeof SESSION_PREVIEW_OPTIONS)[number]['id'];

export const SESSION_RESULT_PREVIEW_OPTIONS = [
  { id: 'completed', label: '완료' },
  { id: 'partial', label: '일부 완료' },
  { id: 'not-completed', label: '미수행' },
  { id: 'safety-stop', label: '안전 중단' },
] as const;

export type SessionResultPreviewState =
  (typeof SESSION_RESULT_PREVIEW_OPTIONS)[number]['id'];

export const WEEKLY_REPORT_PREVIEW_OPTIONS = [
  { id: 'open', label: '진행 중인 주' },
  { id: 'closed', label: '마감된 주' },
  { id: 'error', label: '오류' },
] as const;

export type WeeklyReportPreviewState =
  (typeof WEEKLY_REPORT_PREVIEW_OPTIONS)[number]['id'];

export const PREVIEW_PLAN: WorkoutPlan = {
  plan_id: 'plan-preview',
  action_code: 'KEEP',
  training_type_code: 'STRENGTH',
  body_focus_code: 'FULL_BODY',
  requested_duration_minutes: 30,
  estimated_duration_seconds: 1800,
  estimated_calories_burned: 128,
  setup_seconds: 0,
  warmup_seconds: 120,
  cooldown_seconds: 60,
  items: [
    {
      plan_item_id: 'plan-item-squat',
      exercise_id: 'exercise-squat',
      exercise_name: '의자 스쿼트',
      sequence: 1,
      tier_code: 'CORE',
      sets: 3,
      reps: 10,
      work_seconds: 180,
      rest_seconds: 60,
      transition_seconds: 15,
      estimated_item_seconds: 600,
      instruction_available: true,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    },
    {
      plan_item_id: 'plan-item-pushup',
      exercise_id: 'exercise-pushup',
      exercise_name: '벽 푸시업',
      sequence: 2,
      tier_code: 'CORE',
      sets: 3,
      reps: 10,
      work_seconds: 180,
      rest_seconds: 60,
      transition_seconds: 15,
      estimated_item_seconds: 600,
      instruction_available: true,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    },
    {
      plan_item_id: 'plan-item-march',
      exercise_id: 'exercise-march',
      exercise_name: '제자리 걷기',
      sequence: 3,
      tier_code: 'SUPPORT',
      sets: 3,
      reps: null,
      work_seconds: 180,
      rest_seconds: 60,
      transition_seconds: 15,
      estimated_item_seconds: 420,
      instruction_available: true,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    },
  ],
};

const PREVIEW_ROUTINE: RoutineResponse = {
  id: 'routine-preview',
  version: 2,
  goal_code: 'GENERAL_FITNESS',
  status_code: 'ACTIVE',
  effective_from: '2026-08-17',
  catalog_version: 'preview-synthetic-v1',
  created_at: '2026-08-17T00:00:00+09:00',
  days: [
    {
      id: 'routine-day-preview',
      sequence: 1,
      title: '전신 기본 루틴',
      training_type_code: PREVIEW_PLAN.training_type_code,
      body_focus_code: PREVIEW_PLAN.body_focus_code,
      requested_duration_minutes: PREVIEW_PLAN.requested_duration_minutes,
      estimated_duration_seconds: PREVIEW_PLAN.estimated_duration_seconds,
      estimated_calories_burned: PREVIEW_PLAN.estimated_calories_burned,
      items: PREVIEW_PLAN.items.map((item) => ({
        id: `routine-${item.plan_item_id}`,
        exercise_id: item.exercise_id,
        exercise_name: item.exercise_name,
        sequence: item.sequence,
        phase_code: item.sequence === 3 ? 'COOLDOWN' : 'MAIN',
        tier_code: item.tier_code === 'SUPPORT' ? 'SUPPORT' : 'CORE',
        sets: item.sets,
        reps: item.reps,
        work_seconds_per_set: item.reps === null ? item.work_seconds : null,
        rest_seconds_per_set: item.rest_seconds,
        instruction_available: item.instruction_available,
      })),
    },
  ],
};

function previewWeek(status: 'OPEN' | 'CLOSED'): WeekResponse {
  return {
    week_id: 'week-preview',
    week_start: '2026-08-17',
    week_end: '2026-08-23',
    timezone: 'Asia/Seoul',
    target_workout_count: 4,
    plan_origin_code: 'INITIAL',
    cold_start_applied: true,
    status_code: status,
    closed_at: status === 'CLOSED' ? '2026-08-23T23:59:59+09:00' : null,
    report_id: null,
    report_status_code: null,
  };
}

const PREVIEW_REPORT: WeeklyReportResponse = {
  report_id: 'report-preview',
  week_start: '2026-08-17',
  week_end: '2026-08-23',
  status_code: 'GENERATED',
  counts: {
    completed: 3,
    partial: 1,
    not_completed: 0,
    stopped_for_safety: 0,
  },
  primary_miss_reason_code: null,
  completion_rate: 0.75,
  persistence_rate: 1,
  negotiation_success_rate: 1,
  decision_summary: '몸 상태에 맞춰 강도를 조절하며 꾸준히 움직였어요.',
  adjustment_direction_code: 'MAINTAIN',
  next_action: '다음 주에도 같은 빈도로 이어가요.',
  summary: '이번 주 목표에 맞춰 차근차근 운동했어요.',
  acknowledged_at: null,
  generated_at: '2026-08-23T23:59:59+09:00',
};

function previewError(
  message: string,
  kind: 'network' | 'notFound' = 'network',
) {
  return new ApiError({
    kind,
    code: kind === 'notFound' ? 'ROUTINE_NOT_FOUND' : 'NETWORK_UNAVAILABLE',
    status: kind === 'notFound' ? 404 : 0,
    message,
  });
}

export function createHousePreviewApi(state: HousePreviewState): Api {
  return {
    async getCurrentRoutine() {
      if (state === 'empty') {
        throw previewError('아직 만들어진 루틴이 없어요.', 'notFound');
      }
      if (state === 'error') {
        throw previewError('루틴을 불러오지 못했습니다.');
      }
      return PREVIEW_ROUTINE;
    },
    async getWeek() {
      return previewWeek('OPEN');
    },
  } as unknown as Api;
}

export function createSessionPreviewApi(state: SessionPreviewState): Api {
  return {
    async getWorkoutSession() {
      if (state === 'error') {
        throw previewError('세션을 불러오지 못했습니다.');
      }
      return {
        session_id: 'session-preview',
        local_date: '2026-08-18',
        status_code: 'PLANNED',
        completed_item_count: 0,
        total_item_count: PREVIEW_PLAN.items.length,
        requested_duration_minutes: PREVIEW_PLAN.requested_duration_minutes,
        items: PREVIEW_PLAN.items.map((item) => ({
          plan_item_id: item.plan_item_id,
          exercise_id: item.exercise_id,
          exercise_name: item.exercise_name,
          status_code: 'PENDING',
          sets: item.sets,
          reps: item.reps,
          work_seconds_per_set: item.reps === null ? item.work_seconds : null,
          completed_at: null,
        })),
        feedback: null,
        not_completed_reason_code: null,
        started_at: null,
        finished_at: null,
      };
    },
    async startSession(_sessionId: string, startedAt: string) {
      if (state === 'error') {
        throw previewError('세션을 시작하지 못했습니다.');
      }
      return {
        session_id: 'session-preview',
        status_code: 'IN_PROGRESS',
        started_at: startedAt,
        items: PREVIEW_PLAN.items.map((item) => ({
          plan_item_id: item.plan_item_id,
          status_code: 'PENDING',
          completed_at: null,
        })),
        current_plan_item_id: PREVIEW_PLAN.items[0]?.plan_item_id ?? null,
      };
    },
    async updateSessionItem(
      _sessionId: string,
      planItemId: string,
      statusCode: 'PENDING' | 'COMPLETED',
      recordedAt: string,
    ) {
      const index = PREVIEW_PLAN.items.findIndex(
        (item) => item.plan_item_id === planItemId,
      );
      return {
        session_id: 'session-preview',
        status_code: 'IN_PROGRESS',
        item: {
          plan_item_id: planItemId,
          status_code: statusCode,
          completed_at: statusCode === 'COMPLETED' ? recordedAt : null,
        },
        completed_item_count: statusCode === 'COMPLETED' ? 1 : 0,
        total_item_count: PREVIEW_PLAN.items.length,
        next_pending_plan_item_id:
          PREVIEW_PLAN.items[index + 1]?.plan_item_id ?? null,
      };
    },
    async recordTimerEvent() {
      return { event_id: 'timer-event-preview' };
    },
    async recordAdditionalActivity(
      _sessionId: string,
      body: {
        activity_type_code: string;
        duration_seconds: number;
        intensity_code?: string | null;
        note?: string | null;
      },
    ) {
      return {
        activity_id: 'activity-preview',
        session_id: 'session-preview',
        activity_type_code: body.activity_type_code,
        duration_seconds: body.duration_seconds,
        intensity_code: body.intensity_code ?? null,
        note: body.note ?? null,
        created_at: '2026-08-18T09:20:00+09:00',
        session_status_code: 'IN_PROGRESS',
      };
    },
    async getExercise(exerciseId: string) {
      const item = PREVIEW_PLAN.items.find(
        (candidate) => candidate.exercise_id === exerciseId,
      );
      return {
        exercise_id: exerciseId,
        exercise_name: item?.exercise_name ?? '운동',
        training_type_code: PREVIEW_PLAN.training_type_code,
        primary_body_area_codes: ['FULL_BODY'],
        instruction_summary: '통증이 없는 범위에서 천천히 움직여주세요.',
        form_cues: ['호흡을 멈추지 않기', '편안한 가동 범위 유지하기'],
        media_asset_key: null,
        mascot_animation_asset_key: null,
        instruction_content_version: 'preview-v1',
      };
    },
    async finishSession(
      _sessionId: string,
      finishedAt: string,
      actualElapsedSeconds: number,
    ) {
      return finishedOutcome(finishedAt, actualElapsedSeconds);
    },
    async markNotCompleted(
      _sessionId: string,
      endedAt: string,
      reasonCode: NotCompletedReasonCode,
    ) {
      return {
        session_id: 'session-preview',
        status_code: 'NOT_COMPLETED',
        reason_code: reasonCode,
        ended_at: endedAt,
      };
    },
    async reportSafetyEvent() {
      return safetyStopOutcome();
    },
  } as unknown as Api;
}

export function createWeeklyReportPreviewApi(
  state: WeeklyReportPreviewState,
): Api {
  return {
    async getWeek() {
      if (state === 'error') {
        throw previewError('주간 정보를 불러오지 못했습니다.');
      }
      return previewWeek(state === 'closed' ? 'CLOSED' : 'OPEN');
    },
    async createWeeklyReport() {
      if (state === 'open') {
        throw new ApiError({
          kind: 'conflict',
          code: 'WEEK_NOT_CLOSED',
          status: 409,
          message: '이번 주가 마감된 뒤 리포트를 만들 수 있어요.',
        });
      }
      return PREVIEW_REPORT;
    },
    async acknowledgeWeeklyReport(_reportId: string, acknowledgedAt: string) {
      return {
        ...PREVIEW_REPORT,
        status_code: 'ACKNOWLEDGED',
        acknowledged_at: acknowledgedAt,
      };
    },
  } as unknown as Api;
}

export const accountPreviewApi = {
  async requestAccountDeletion() {
    return {
      deletion_request_id: 'deletion-preview',
      status_code: 'PENDING',
      operational_data_delete_by: '2026-08-25T00:00:00+09:00',
      backup_expiry_days: 30,
    };
  },
  async getConsents() {
    return {
      user_id: 'user-preview',
      consents: [
        'GENERAL_PERSONAL_DATA',
        'SENSITIVE_DATA',
        'WEARABLE_INTEGRATION',
        'CALENDAR_INTEGRATION',
        'MARKETING',
      ].map((code) => ({
        consent_type_code: code,
        granted: code === 'GENERAL_PERSONAL_DATA' || code === 'SENSITIVE_DATA',
        policy_version: 'consent-preview-v1',
        updated_at: '2026-08-18T00:00:00+09:00',
      })),
    };
  },
  async replaceConsents(body: ConsentValues) {
    return {
      user_id: 'user-preview',
      consents: Object.entries(body).map(([key, granted]) => ({
        consent_type_code: key.toUpperCase(),
        granted,
        policy_version: 'consent-preview-v1',
        updated_at: '2026-08-18T00:00:00+09:00',
      })),
    };
  },
  async updateProfileSettings() {
    return {
      profile_version: 2,
      updated_at: '2026-08-18T00:00:00+09:00',
    };
  },
} as unknown as Api;

export const sessionResultPreviewApi = {
  async submitFeedback() {
    return {
      session_id: 'session-preview',
      session_status_code: 'COMPLETED',
      created_at: '2026-08-18T09:31:00+09:00',
      guidance_code: null,
      guidance: null,
      pressure_notifications_allowed: true,
    };
  },
} as unknown as Api;

function finishedOutcome(
  endedAt = '2026-08-18T09:30:00+09:00',
  actualElapsedSeconds = 1710,
  statusCode: 'COMPLETED' | 'PARTIAL' = 'COMPLETED',
): SessionFinishResponse {
  return {
    session_id: 'session-preview',
    status_code: statusCode,
    completed_item_count:
      statusCode === 'COMPLETED' ? PREVIEW_PLAN.items.length : 2,
    total_item_count: PREVIEW_PLAN.items.length,
    actual_elapsed_seconds: actualElapsedSeconds,
    estimated_calories_burned: 128,
    ended_at: endedAt,
  };
}

function notCompletedOutcome(): SessionNotCompletedResponse {
  return {
    session_id: 'session-preview',
    status_code: 'NOT_COMPLETED',
    reason_code: 'TIME_SHORTAGE',
    ended_at: '2026-08-18T09:10:00+09:00',
  };
}

function safetyStopOutcome(): SafetyEventResponse {
  return {
    event_id: 'safety-event-preview',
    instruction_code: 'STOP_SESSION',
    resulting_action_code: 'REST',
    session_status_code: 'STOPPED_FOR_SAFETY',
    guidance_code: 'STOP_FOR_SAFETY',
    guidance: '운동을 중단하고 상태를 확인해주세요.',
    pressure_notifications_allowed: false,
  };
}

export function sessionResultPreviewOutcome(
  state: SessionResultPreviewState,
): SessionOutcome {
  if (state === 'partial') {
    return {
      kind: 'finished',
      result: finishedOutcome(undefined, 1200, 'PARTIAL'),
    };
  }
  if (state === 'not-completed') {
    return { kind: 'notCompleted', result: notCompletedOutcome() };
  }
  if (state === 'safety-stop') {
    return { kind: 'safetyStop', event: safetyStopOutcome() };
  }
  return { kind: 'finished', result: finishedOutcome() };
}
