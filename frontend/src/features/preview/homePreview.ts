/**
 * Development-only server responses for visually checking the home screen.
 *
 * These fixtures choose response *shapes* so each visual state can be looked
 * at; they never stand in for a workout decision. Everything the home screen
 * shows still comes from a field the real contract defines.
 */

import type {
  DailyContextResponse,
  DecisionResponse,
  RoutineResponse,
  WeekResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import type { Api } from '../../api/endpoints';
import { localDateString, weekStartString } from '../../api/useAsync';
import type { HomeScreenProps } from '../home/HomeScreen';
import type { HomePreviewState } from '../home/homeModel';

const PREVIEW_TIME_ZONE = 'Asia/Seoul';
const PREVIEW_NOW = new Date();
const LOCAL_DATE = localDateString(PREVIEW_NOW, PREVIEW_TIME_ZONE);
const WEEK_START = weekStartString(PREVIEW_NOW, PREVIEW_TIME_ZONE);
const WEEK_END = addDays(WEEK_START, 6);
const COMPLETED_DATES =
  LOCAL_DATE === WEEK_START ? [LOCAL_DATE] : [WEEK_START, LOCAL_DATE];

const SESSIONS: WorkoutSessionLogSummary[] = COMPLETED_DATES.map(
  (localDate, index) => ({
    session_id: `session-preview-${index + 1}`,
    local_date: localDate,
    status_code: 'COMPLETED',
    completed_item_count: 3,
    total_item_count: 3,
    requested_duration_minutes: 40,
    training_type_code: 'STRENGTH',
    not_completed_reason_code: null,
    started_at: `${localDate}T08:00:00+09:00`,
    finished_at: `${localDate}T08:40:00+09:00`,
  }),
);

const HOME_EXERCISE_PREVIEW_API: Pick<
  Api,
  'getExercise' | 'getExerciseVariants'
> = {
  async getExercise(exerciseId: string) {
    const names: Record<string, string> = {
      'exercise-0': '준비 운동',
      'exercise-1': '푸시업',
      'exercise-2': '밴드 로우',
    };
    return {
      exercise_id: exerciseId,
      exercise_name: names[exerciseId] ?? '운동',
      training_type_code: 'STRENGTH',
      primary_body_area_codes: ['UPPER_BACK'],
      instruction_summary: '통증이 없는 범위에서 천천히 움직여주세요.',
      form_cues: ['호흡을 멈추지 않기', '편안한 가동 범위 유지하기'],
      media_asset_key: null,
      mascot_animation_asset_key: null,
      instruction_content_version: 'home-preview-v1',
    };
  },
  async getExerciseVariants(exerciseId: string) {
    const hasVariant = exerciseId === 'exercise-2';
    return {
      source_exercise_id: exerciseId,
      source_required_equipment_codes: hasVariant
        ? ['BODYWEIGHT', 'RESISTANCE_BAND']
        : ['BODYWEIGHT'],
      items: hasVariant
        ? [
            {
              exercise_id: 'exercise-2-bodyweight-variant',
              exercise_name: '엎드려 등 당기기',
              required_equipment_codes: ['BODYWEIGHT'],
              instruction_summary:
                '밴드 없이 엎드린 자세에서 팔꿈치를 몸통 쪽으로 당겨요.',
              form_cues: [
                '어깨를 귀에서 멀리 유지하기',
                '허리가 꺾이지 않게 복부에 힘주기',
              ],
              media_asset_key: null,
              goal_preservation_code: 'GENERAL_FITNESS',
            },
          ]
        : [],
      catalog_version: 'exercise-catalog-v2.0.1-final',
      alternative_set_version: hasVariant ? 'alternative-set-v2.0.1' : null,
    };
  },
};

const ROUTINE: RoutineResponse = {
  id: '11111111-1111-4111-8111-111111111111',
  version: 1,
  goal_code: 'GENERAL_FITNESS',
  status_code: 'ACTIVE',
  effective_from: LOCAL_DATE,
  catalog_version: 'preview',
  created_at: `${LOCAL_DATE}T00:00:00+09:00`,
  days: [
    {
      id: '22222222-2222-4222-8222-222222222222',
      sequence: 1,
      title: '상체 근력',
      training_type_code: 'STRENGTH',
      body_focus_code: 'UPPER_BODY',
      requested_duration_minutes: 40,
      estimated_duration_seconds: 2400,
      estimated_calories_burned: null,
      items: [
        {
          id: 'routine-item-1',
          exercise_id: 'exercise-1',
          exercise_name: '푸시업',
          sequence: 1,
          phase_code: 'MAIN',
          tier_code: 'CORE',
          sets: 3,
          reps: 10,
          work_seconds_per_set: null,
          rest_seconds_per_set: 45,
          instruction_available: true,
        },
        {
          id: 'routine-item-2',
          exercise_id: 'exercise-2',
          exercise_name: '밴드 로우',
          sequence: 2,
          phase_code: 'MAIN',
          tier_code: 'CORE',
          sets: 3,
          reps: 12,
          work_seconds_per_set: null,
          rest_seconds_per_set: 45,
          instruction_available: true,
        },
      ],
    },
  ],
};

const CONTEXT: DailyContextResponse = {
  id: '33333333-3333-4333-8333-333333333333',
  local_date: LOCAL_DATE,
  context_version: 1,
  fatigue_level_code: 'MODERATE',
  available_time_minutes: 40,
  location_code: 'HOME',
  sleep_minutes: 420,
  sleep_source_code: 'MANUAL',
  pain_present: false,
  red_flag_present: false,
  pains: [],
  created_at: `${LOCAL_DATE}T08:00:00+09:00`,
  updated_at: `${LOCAL_DATE}T08:00:00+09:00`,
};

const WEEK: WeekResponse = {
  week_id: '44444444-4444-4444-8444-444444444444',
  week_start: WEEK_START,
  week_end: WEEK_END,
  timezone: PREVIEW_TIME_ZONE,
  target_workout_count: 4,
  plan_origin_code: 'INITIAL',
  cold_start_applied: true,
  status_code: 'OPEN',
  closed_at: null,
  report_id: null,
  report_status_code: null,
};

function addDays(localDate: string, days: number): string {
  const [year, month, day] = localDate.split('-').map(Number);
  const date = new Date(Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1));
  date.setUTCDate(date.getUTCDate() + days);
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

function plan(): WorkoutPlan {
  return {
    plan_id: '55555555-5555-4555-8555-555555555555',
    action_code: 'KEEP',
    training_type_code: 'STRENGTH',
    body_focus_code: 'UPPER_BODY',
    requested_duration_minutes: 40,
    estimated_duration_seconds: 2280,
    estimated_calories_burned: null,
    setup_seconds: 0,
    warmup_seconds: 180,
    cooldown_seconds: 120,
    items: [
      {
        plan_item_id: 'plan-item-1',
        exercise_id: 'exercise-0',
        exercise_name: '준비 운동',
        sequence: 1,
        tier_code: 'SUPPORT',
        sets: 1,
        reps: 10,
        work_seconds: 180,
        rest_seconds: 0,
        transition_seconds: 10,
        estimated_item_seconds: 190,
        instruction_available: true,
        mascot_animation_asset_key: null,
        replacement_of_exercise_id: null,
      },
      {
        plan_item_id: 'plan-item-2',
        exercise_id: 'exercise-1',
        exercise_name: '푸시업',
        sequence: 2,
        tier_code: 'CORE',
        sets: 3,
        reps: 10,
        work_seconds: 45,
        rest_seconds: 45,
        transition_seconds: 10,
        estimated_item_seconds: 280,
        instruction_available: true,
        mascot_animation_asset_key: null,
        replacement_of_exercise_id: null,
      },
      {
        plan_item_id: 'plan-item-3',
        exercise_id: 'exercise-2',
        exercise_name: '밴드 로우',
        sequence: 3,
        tier_code: 'CORE',
        sets: 3,
        reps: 12,
        work_seconds: 45,
        rest_seconds: 45,
        transition_seconds: 10,
        estimated_item_seconds: 300,
        instruction_available: true,
        mascot_animation_asset_key: null,
        replacement_of_exercise_id: null,
      },
    ],
  };
}

function decision(adjusted: boolean): DecisionResponse {
  return {
    decision_id: '66666666-6666-4666-8666-666666666666',
    local_date: LOCAL_DATE,
    status_code: 'COMPLETED',
    safety_status_code: adjusted ? 'REVISE' : 'PASS',
    action_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
    requested_duration_minutes: 40,
    duration_adjustment_source_code: 'PROFILE',
    final_plan: { ...plan(), action_code: adjusted ? 'DOWNSHIFT' : 'KEEP' },
    options: [
      {
        option_id: 'option-routine',
        option_code: 'FINAL_ROUTINE',
        action_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
        plan_id: '55555555-5555-4555-8555-555555555555',
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
    reason_codes: [
      'PRIMARY_GOAL_PRESERVED',
      ...(adjusted ? ['MODERATE_FATIGUE_DOWNSHIFT'] : []),
    ],
    adjustment_reason_codes: adjusted ? ['MODERATE_FATIGUE_DOWNSHIFT'] : null,
    summary: adjusted
      ? '오늘 컨디션에 맞춰 부담을 낮췄어요.'
      : '오늘은 계획대로 진행해요.',
    guidance: adjusted
      ? {
          code: 'DOWNSHIFT_APPLIED',
          title: '부담을 낮췄어요',
          message: '요청한 시간은 그대로 두고 세트와 강도만 조정했어요.',
          tone_code: 'NEUTRAL',
        }
      : null,
    public_agent_summaries: [
      {
        agent_type_code: 'TRAINING',
        recommendation_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
        reason_codes: ['PRIMARY_GOAL_PRESERVED'],
        summary: '운동 목표와 희망 운동 시간을 유지했어요.',
      },
      {
        agent_type_code: 'RECOVERY',
        recommendation_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
        reason_codes: adjusted
          ? ['MODERATE_FATIGUE_DOWNSHIFT']
          : ['RECOVERY_CONTEXT_REVIEWED'],
        summary: adjusted
          ? '오늘의 피로도를 고려해 운동 부담을 낮추도록 제안했어요.'
          : '오늘의 회복 상태에서 계획한 운동을 진행할 수 있어요.',
      },
      {
        agent_type_code: 'SAFETY',
        recommendation_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
        reason_codes: adjusted
          ? ['MODERATE_FATIGUE_DOWNSHIFT']
          : ['NO_SAFETY_SIGNAL_REPORTED'],
        summary: adjusted
          ? '부담이 될 수 있는 운동 2개를 제외하고 강도를 중간 이하로 제한했어요.'
          : '제외한 운동 없이 계획한 강도 상한을 적용했어요.',
      },
      {
        agent_type_code: 'FEASIBILITY',
        recommendation_code: 'KEEP',
        reason_codes: ['TIME_LOCATION_EQUIPMENT_MATCHED'],
        summary: '희망 시간과 장소, 사용 가능한 장비에 맞는 구성이에요.',
      },
      {
        agent_type_code: 'COORDINATOR',
        recommendation_code: adjusted ? 'DOWNSHIFT' : 'KEEP',
        reason_codes: ['COMMON_CANDIDATE_SELECTED'],
        summary: adjusted
          ? '운동 목표와 희망 시간은 유지하고 세트와 강도만 조정했어요.'
          : '모든 조건을 함께 확인해 계획한 루틴을 최종 추천했어요.',
      },
    ],
    safety_summary: {
      safety_status_code: adjusted ? 'REVISE' : 'PASS',
      vetoed: false,
      reason_codes: adjusted
        ? ['MODERATE_FATIGUE_DOWNSHIFT']
        : ['NO_SAFETY_SIGNAL_REPORTED'],
      summary: adjusted
        ? '안전 기준을 유지하면서 운동 부담을 조정했어요.'
        : '현재 체크인에 적용할 안전 제한을 확인했어요.',
    },
    generation_mode_code: adjusted ? 'REGENERATED' : 'ORIGINAL',
    decision_engine_code: 'LLM_MULTI_AGENT',
    root_decision_id: '66666666-6666-4666-8666-666666666666',
    parent_decision_id: adjusted
      ? '66666666-6666-4666-8666-666666666666'
      : null,
    regeneration_sequence: adjusted ? 1 : 0,
    meaningful_difference_codes: adjusted
      ? ['SET_REP_STRUCTURE_CHANGED']
      : null,
    created_at: `${LOCAL_DATE}T08:05:00+09:00`,
  };
}

function sessionDetail(
  status: WorkoutSessionDetailResponse['status_code'],
): WorkoutSessionDetailResponse {
  const completedCount = status === 'COMPLETED' ? 3 : 1;
  return {
    session_id: `session-${status.toLowerCase()}`,
    local_date: LOCAL_DATE,
    status_code: status,
    completed_item_count: completedCount,
    total_item_count: 3,
    requested_duration_minutes: 40,
    items: plan().items.map((item, index) => ({
      plan_item_id: item.plan_item_id,
      exercise_id: item.exercise_id,
      exercise_name: item.exercise_name,
      status_code: index < completedCount ? 'COMPLETED' : 'PENDING',
      sets: item.sets,
      reps: item.reps,
      work_seconds_per_set: item.work_seconds,
      completed_at:
        index < completedCount ? `${LOCAL_DATE}T08:15:00+09:00` : null,
    })),
    feedback: null,
    not_completed_reason_code: null,
    started_at: `${LOCAL_DATE}T08:00:00+09:00`,
    finished_at:
      status === 'IN_PROGRESS' || status === 'PLANNED'
        ? null
        : `${LOCAL_DATE}T08:25:00+09:00`,
  };
}

export function homePreviewProps(state: HomePreviewState): HomeScreenProps {
  const showsRoutineLookup =
    state === 'routine-lookup-loading' || state === 'routine-lookup-failed';
  const showsRoutine =
    state === 'routine' ||
    state === 'decision-recovered' ||
    state === 'decision-retry' ||
    state === 'adjusted' ||
    state === 'editing' ||
    state === 'session-active' ||
    state === 'session-resumable' ||
    state === 'session-safety-stopped' ||
    state === 'session-completed';
  const showsGeneration =
    state === 'generating' || state === 'generating-final';
  const decisionResponseLost = state === 'decision-retry';

  return {
    nickname: '헬끼',
    localDate: LOCAL_DATE,
    status:
      state === 'routine-lookup-loading'
        ? 'loading'
        : state === 'routine-lookup-failed'
          ? 'error'
          : 'ready',
    routine: showsRoutineLookup ? null : ROUTINE,
    context: state === 'pre-checkin' || showsRoutineLookup ? null : CONTEXT,
    decision: showsRoutine ? decision(state === 'adjusted') : null,
    todaySession:
      state === 'session-active' || state === 'session-resumable'
        ? sessionDetail('IN_PROGRESS')
        : state === 'session-safety-stopped'
          ? sessionDetail('STOPPED_FOR_SAFETY')
          : state === 'session-completed'
            ? sessionDetail('COMPLETED')
            : null,
    localSessionState:
      state === 'session-resumable' ? 'STOPPED_RESUMABLE' : 'ACTIVE',
    week: WEEK,
    sessions: SESSIONS,
    planRevision: null,
    restToday: state === 'rest',
    exerciseApi: HOME_EXERCISE_PREVIEW_API,
    locationCodes: ['HOME', 'GYM'],
    busy: showsGeneration ? 'decision-generation' : null,
    errorMessage:
      state === 'routine-lookup-failed'
        ? '운동 계획을 준비하지 못했어요.'
        : undefined,
    actionError: decisionResponseLost
      ? '체크인은 저장됐지만 오늘 루틴 생성 결과를 확인하지 못했어요. 저장된 체크인으로 루틴 생성만 다시 시도할 수 있어요.'
      : null,
    onRetryDecision: decisionResponseLost ? () => undefined : undefined,
    routineLoadingPhaseCode:
      state === 'generating-final' ? 'FINAL_VALIDATION' : undefined,
    previewState: state,
  };
}
