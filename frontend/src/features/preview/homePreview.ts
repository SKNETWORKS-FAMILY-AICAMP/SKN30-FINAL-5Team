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
} from '../../api/types';
import type { HomeScreenProps } from '../home/HomeScreen';
import type { HomePreviewState } from '../home/homeModel';

const LOCAL_DATE = '2026-08-11';
const WEEK_START = '2026-08-10';

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
  requested_duration_minutes: 40,
  duration_adjustment_source_code: 'PROFILE',
  location_code: 'HOME',
  sleep_minutes: 420,
  discomforts: [],
  adverse_reaction_codes: [],
  created_at: `${LOCAL_DATE}T08:00:00+09:00`,
  updated_at: `${LOCAL_DATE}T08:00:00+09:00`,
};

const WEEK: WeekResponse = {
  week_id: '44444444-4444-4444-8444-444444444444',
  week_start: WEEK_START,
  week_end: '2026-08-16',
  timezone: 'Asia/Seoul',
  target_workout_count: 4,
  plan_origin_code: 'INITIAL',
  cold_start_applied: true,
  status_code: 'OPEN',
  closed_at: null,
  report_id: null,
  report_status_code: null,
};

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
        reps: null,
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
    reason_codes: [],
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
    public_agent_summaries: null,
    safety_summary: null,
    created_at: `${LOCAL_DATE}T08:05:00+09:00`,
  };
}

export function homePreviewProps(state: HomePreviewState): HomeScreenProps {
  const showsRoutine =
    state === 'routine' || state === 'adjusted' || state === 'editing';

  return {
    nickname: '헬끼',
    localDate: LOCAL_DATE,
    status: 'ready',
    routine: ROUTINE,
    context: state === 'pre-checkin' ? null : CONTEXT,
    decision: showsRoutine ? decision(state === 'adjusted') : null,
    week: WEEK,
    planRevision: null,
    defaultDurationMinutes: 40,
    locationCodes: ['HOME', 'GYM'],
    busy: state === 'generating' ? 'checkin' : null,
    previewState: state,
  };
}
