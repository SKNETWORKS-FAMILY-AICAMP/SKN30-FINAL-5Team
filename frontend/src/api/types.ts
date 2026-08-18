/**
 * Response and request shapes for `/api/v1`.
 *
 * These mirror the backend Pydantic schemas field for field. They are stable
 * machine codes only; Korean presentation strings live in `labels.ts` so the
 * client never treats a user-facing label as a key.
 *
 * The client must not re-derive safety, duration, return-mode or coordinator
 * decisions from these values. It renders what the server decided.
 */

export type ActionCode =
  'KEEP' | 'DOWNSHIFT' | 'CHANGE' | 'RECOVERY' | 'REST' | 'STOP_AND_SEEK_HELP';

export type SafetyStatusCode = 'PASS' | 'REVISE' | 'BLOCKED';
export type OptionCode = 'FINAL_ROUTINE' | 'REST';
export type DiscomfortSeverityCode = 'MILD' | 'MODERATE' | 'SEVERE';
export type FatigueLevelCode = 'LOW' | 'MODERATE' | 'HIGH';
export type BlockStatusCode = 'PENDING' | 'COMPLETED';
export type ToneCode = 'SERIOUS' | 'NEUTRAL';

export type SessionStatusCode =
  | 'PLANNED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'PARTIAL'
  | 'NOT_COMPLETED'
  | 'STOPPED_FOR_SAFETY';

export type SafetyInstructionCode =
  'SHOW_CAUTION' | 'STOP_SESSION' | 'STOP_AND_SEEK_HELP';

export type NotCompletedReasonCode =
  | 'TIME_SHORTAGE'
  | 'FATIGUE'
  | 'MUSCLE_SORENESS'
  | 'PAIN'
  | 'SCHEDULE_CHANGE'
  | 'LOCATION_EQUIPMENT'
  | 'WEATHER'
  | 'DIFFICULTY'
  | 'LOW_INTEREST'
  | 'LOW_MOTIVATION';

export type MeProfile = {
  nickname: string;
  age: number | null;
  primary_goal_code: string;
  experience_level_code: string;
  timezone: string;
  preferred_location_code: string;
  available_location_codes: string[];
  default_requested_duration_minutes: number;
  desired_weekly_workout_count: number;
  coaching_style_code: string;
  equipment_codes: string[];
  attention_area_codes: string[];
  preferred_exercise_type_codes: string[];
  profile_version: number;
  created_at: string;
  updated_at: string;
};

export type MeResponse = {
  user_id: string;
  status_code: string;
  onboarding_completed: boolean;
  premium_status_code: string;
  ai_trial_started_at: string;
  ai_trial_ends_at: string;
  profile: MeProfile | null;
};

export type ConsentValues = {
  general_personal_data: boolean;
  sensitive_data: boolean;
  wearable_integration: boolean;
  calendar_integration: boolean;
  marketing: boolean;
};

export type OnboardingRequest = {
  nickname: string;
  date_of_birth: string;
  primary_goal_code: string;
  experience_level_code: string;
  timezone: string;
  preferred_location_code: string;
  available_location_codes: string[];
  default_requested_duration_minutes: number;
  desired_weekly_workout_count: number;
  equipment_codes: string[];
  attention_area_codes: string[];
  preferred_exercise_type_codes: string[];
  coaching_style_code: string;
  consents: ConsentValues;
};

export type OnboardingResponse = {
  user_id: string;
  onboarding_completed: boolean;
  profile_version: number;
  coaching_style_code: string;
  ai_trial_started_at: string;
  ai_trial_ends_at: string;
  premium_status_code: string;
  created_at: string;
  updated_at: string;
};

export type RoutineItem = {
  id: string;
  exercise_id: string;
  exercise_name: string;
  sequence: number;
  phase_code: 'WARMUP' | 'MAIN' | 'COOLDOWN';
  tier_code: 'CORE' | 'SUPPORT' | 'OPTIONAL';
  sets: number;
  reps: number | null;
  work_seconds_per_set: number | null;
  rest_seconds_per_set: number;
  instruction_available: boolean;
};

export type RoutineDay = {
  id: string;
  sequence: number;
  title: string;
  training_type_code: string;
  body_focus_code: string | null;
  requested_duration_minutes: number;
  estimated_duration_seconds: number;
  estimated_calories_burned: number | null;
  items: RoutineItem[];
};

export type RoutineResponse = {
  id: string;
  version: number;
  goal_code: string;
  status_code: 'DRAFT' | 'ACTIVE' | 'ARCHIVED';
  effective_from: string;
  catalog_version: string;
  days: RoutineDay[];
  created_at: string;
};

export type DiscomfortInput = {
  body_area_code: string;
  severity_code: DiscomfortSeverityCode;
};

export type DailyContextRequest = {
  fatigue_level_code: FatigueLevelCode;
  requested_duration_minutes: number;
  duration_adjustment_source_code: 'PROFILE' | 'USER_OVERRIDE';
  location_code: string;
  sleep_minutes?: number | null;
  discomforts: DiscomfortInput[];
  adverse_reaction_codes: string[];
};

export type DailyContextResponse = DailyContextRequest & {
  id: string;
  local_date: string;
  context_version: number;
  created_at: string;
  updated_at: string;
};

export type WorkoutPlanItem = {
  plan_item_id: string;
  exercise_id: string;
  exercise_name: string;
  sequence: number;
  tier_code: string;
  sets: number;
  reps: number | null;
  work_seconds: number;
  rest_seconds: number;
  transition_seconds: number;
  estimated_item_seconds: number;
  instruction_available: boolean;
  mascot_animation_asset_key: string | null;
  replacement_of_exercise_id: string | null;
};

export type WorkoutPlan = {
  plan_id: string;
  action_code: ActionCode;
  training_type_code: string;
  body_focus_code: string | null;
  requested_duration_minutes: number;
  estimated_duration_seconds: number;
  estimated_calories_burned: number | null;
  setup_seconds: number;
  warmup_seconds: number;
  cooldown_seconds: number;
  items: WorkoutPlanItem[];
};

export type DecisionOption = {
  option_id: string;
  option_code: OptionCode;
  action_code: ActionCode;
  plan_id: string | null;
  selectable: boolean;
  blocked_reason_code: string | null;
};

export type Guidance = {
  code: string;
  title: string;
  message: string;
  tone_code: ToneCode;
};

export type AgentSummary = {
  agent_type_code: string;
  recommendation_code: string | null;
  reason_codes: string[];
  summary: string;
};

export type SafetySummary = {
  safety_status_code: string;
  vetoed: boolean;
  reason_codes: string[];
  summary: string;
};

export type DecisionResponse = {
  decision_id: string;
  local_date: string;
  status_code: 'COMPLETED';
  safety_status_code: SafetyStatusCode;
  action_code: ActionCode;
  requested_duration_minutes: number;
  duration_adjustment_source_code: string;
  final_plan: WorkoutPlan | null;
  options: DecisionOption[];
  reason_codes: string[];
  summary: string;
  guidance: Guidance | null;
  public_agent_summaries: AgentSummary[] | null;
  safety_summary: SafetySummary | null;
  created_at: string;
};

export type WorkoutSessionSummary = {
  session_id: string;
  status_code: 'PLANNED';
};

export type DecisionSelectionResponse = {
  selection_id: string;
  decision_id: string;
  option_id: string;
  selected_action_code: ActionCode;
  workout_session: WorkoutSessionSummary | null;
  selected_at: string;
  pressure_notifications_allowed: boolean | null;
};

export type SessionItem = {
  plan_item_id: string;
  status_code: BlockStatusCode;
  completed_at: string | null;
};

export type SessionStartResponse = {
  session_id: string;
  status_code: 'IN_PROGRESS';
  started_at: string;
  items: SessionItem[];
  current_plan_item_id: string | null;
};

export type SessionItemUpdateResponse = {
  session_id: string;
  status_code: 'IN_PROGRESS';
  item: SessionItem;
  completed_item_count: number;
  total_item_count: number;
  next_pending_plan_item_id: string | null;
};

export type SafetyEventResponse = {
  event_id: string;
  instruction_code: SafetyInstructionCode;
  resulting_action_code: 'REST' | 'STOP_AND_SEEK_HELP' | null;
  session_status_code: 'IN_PROGRESS' | 'STOPPED_FOR_SAFETY';
  guidance_code: string;
  guidance: string;
  pressure_notifications_allowed: boolean;
};

export type SessionFinishResponse = {
  session_id: string;
  status_code: SessionStatusCode;
  completed_item_count: number;
  total_item_count: number;
  actual_elapsed_seconds: number;
  estimated_calories_burned: number | null;
  ended_at: string;
};

export type SessionNotCompletedResponse = {
  session_id: string;
  status_code: 'NOT_COMPLETED';
  reason_code: NotCompletedReasonCode;
  ended_at: string;
};

export type ExerciseDetailResponse = {
  exercise_id: string;
  exercise_name: string;
  training_type_code: string;
  primary_body_area_codes: string[];
  instruction_summary: string;
  form_cues: string[];
  media_asset_key: string | null;
  mascot_animation_asset_key: string | null;
  instruction_content_version: string;
};

export type WeekResponse = {
  week_id: string;
  week_start: string;
  week_end: string;
  timezone: string;
  target_workout_count: number;
  plan_origin_code: string;
  cold_start_applied: boolean;
  status_code: 'OPEN' | 'CLOSED';
  closed_at: string | null;
  report_id: string | null;
  report_status_code: string | null;
};

export type WeeklyReportResponse = {
  report_id: string;
  week_start: string;
  week_end: string;
  status_code: 'GENERATED' | 'ACKNOWLEDGED';
  counts: {
    completed: number;
    partial: number;
    not_completed: number;
    stopped_for_safety: number;
  };
  primary_miss_reason_code: string | null;
  completion_rate: number;
  persistence_rate: number;
  negotiation_success_rate: number | null;
  decision_summary: string;
  adjustment_direction_code: string;
  next_action: string;
  summary: string;
  acknowledged_at: string | null;
  generated_at: string;
};
