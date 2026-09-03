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
export type DecisionGenerationModeCode = 'ORIGINAL' | 'REGENERATED';
export type DecisionEngineCode =
  'DETERMINISTIC' | 'LLM_MULTI_AGENT' | 'DETERMINISTIC_FALLBACK';
export type RegenerationSequence = 0 | 1 | 2;
export type MeaningfulDifferenceCode =
  | 'CORE_EXERCISE_CHANGED'
  | 'SET_REP_STRUCTURE_CHANGED'
  | 'EXERCISE_ORDER_CHANGED'
  | 'ROUTINE_STRUCTURE_CHANGED';

export type SexCode = 'FEMALE' | 'MALE' | 'PREFER_NOT_TO_SAY';

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

export type PainAreaInput = {
  body_area_code: string;
  intensity_score: number;
};

export type MeProfile = {
  nickname: string;
  profile_image_url?: string | null;
  age: number | null;
  primary_goal_code: string;
  experience_level_code: string;
  timezone: string;
  preferred_location_code: string;
  available_location_codes: string[];
  default_requested_duration_minutes: number;
  desired_weekly_workout_count: number;
  coaching_style_code: string;
  attention_area_codes: string[];
  /** Present only after the additive pain-intensity profile contract is available. */
  pain_areas?: PainAreaInput[];
  /** Daily Check-in defaults; never treat these as submitted daily pain. */
  persistent_pains?: PainAreaInput[];
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
  marketing: boolean;
};

export type ConsentState = {
  consent_type_code: string;
  granted: boolean;
  policy_version: string;
  updated_at: string;
};

export type ConsentResponse = {
  user_id: string;
  consents: ConsentState[];
};

export type ProfileSettingsUpdateRequest = {
  primary_goal_code?: string;
  desired_weekly_workout_count?: number;
  default_requested_duration_minutes?: number;
  preferred_location_code?: string;
  available_location_codes?: string[];
  attention_area_codes?: string[];
  /** Daily Check-in defaults; never send with attention_area_codes. */
  persistent_pains?: PainAreaInput[];
  preferred_exercise_type_codes?: string[];
  coaching_style_code?: string;
  experience_level_code?: string;
  nickname?: string;
  height_cm?: number;
  weight_kg?: number;
  sex_code?: SexCode;
  timezone?: string;
  date_of_birth?: string;
};

export type ProfileSettingsUpdateResponse = {
  profile_version: number;
  updated_at: string;
};

/** A device-picked image ready for the profile image multipart endpoint. */
export type ProfileImageUpload = {
  uri: string;
  fileName: string;
  mimeType: string;
  fileSize?: number;
  /** Expo provides a File on web; native uploads use uri/name/type instead. */
  webFile?: Blob;
};

export type ProfileImageMutationResponse = {
  profile_image_url: string | null;
  profile_version: number;
  updated_at: string;
};

export type OnboardingRequest = {
  nickname: string;
  date_of_birth: string;
  medical_exercise_restriction: boolean;
  weight_kg: number;
  primary_goal_code: string;
  experience_level_code: string;
  weekly_target_sessions: number;
  coaching_style_code: string;
  timezone: string;
  terms_version: string;
  persistent_pains: PainAreaInput[];
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

export type AvailabilitySlotInput = {
  start_at: string;
  end_at: string;
};

export type DailyContextRequest = {
  fatigue_level_code: FatigueLevelCode;
  available_time_minutes: number;
  location_code: string;
  sleep_minutes?: number | null;
  sleep_source_code?: 'MANUAL' | 'WEARABLE' | null;
  pain_present: boolean;
  red_flag_present: boolean;
  pains: PainAreaInput[];
};

export type DailyContextResponse = DailyContextRequest & {
  id: string;
  local_date: string;
  context_version: number;
  created_at: string;
  updated_at: string;
  /** Transitional read compatibility for screens that still render archived contexts. */
  requested_duration_minutes?: number;
  duration_adjustment_source_code?: 'PROFILE' | 'USER_OVERRIDE';
  discomforts?: DiscomfortInput[];
  adverse_reaction_codes?: string[];
  available_slots?: AvailabilitySlotInput[] | null;
  availability_source_code?: 'MANUAL' | 'ROUTINE_DEFAULT';
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
  adjustment_reason_codes?: string[] | null;
  summary: string;
  guidance: Guidance | null;
  public_agent_summaries: AgentSummary[] | null;
  safety_summary: SafetySummary | null;
  /** Absent on historical and legacy-engine decisions. */
  generation_mode_code?: DecisionGenerationModeCode | null;
  decision_engine_code?: DecisionEngineCode | null;
  root_decision_id?: string | null;
  parent_decision_id?: string | null;
  regeneration_sequence?: RegenerationSequence | null;
  meaningful_difference_codes?: MeaningfulDifferenceCode[] | null;
  created_at: string;
};

export type DecisionRegenerationRequest = {
  expected_plan_id: string;
  expected_regeneration_sequence: 0 | 1;
};

export type WorkoutSessionSummary = {
  session_id: string;
  status_code: 'PLANNED';
};

export type WorkoutSessionLogSummary = {
  session_id: string;
  local_date: string;
  status_code: SessionStatusCode;
  completed_item_count: number;
  total_item_count: number;
  requested_duration_minutes: number;
  training_type_code: string;
  not_completed_reason_code: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type WorkoutSessionListResponse = {
  items: WorkoutSessionLogSummary[];
  next_cursor: string | null;
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

export type WorkoutAdditionalActivityResponse = {
  activity_id: string;
  session_id: string;
  activity_type_code: string;
  duration_seconds: number;
  intensity_code: string | null;
  note: string | null;
  created_at: string;
  session_status_code: 'IN_PROGRESS';
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

export type WorkoutSessionItemResult = {
  plan_item_id: string;
  exercise_id: string;
  exercise_name: string;
  status_code: BlockStatusCode;
  sets: number;
  reps: number | null;
  work_seconds_per_set: number | null;
  completed_at: string | null;
};

export type WorkoutFeedbackSummary = {
  perceived_difficulty_code: string | null;
  post_workout_discomfort_reported: boolean;
};

export type WorkoutFeedbackResponse = {
  session_id: string;
  session_status_code:
    'COMPLETED' | 'PARTIAL' | 'NOT_COMPLETED' | 'STOPPED_FOR_SAFETY';
  created_at: string;
  guidance_code: string | null;
  guidance: string | null;
  pressure_notifications_allowed: boolean;
};

export type WorkoutSessionDetailResponse = {
  session_id: string;
  local_date: string;
  status_code: SessionStatusCode;
  completed_item_count: number;
  total_item_count: number;
  requested_duration_minutes: number;
  items: WorkoutSessionItemResult[];
  feedback: WorkoutFeedbackSummary | null;
  not_completed_reason_code: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ExerciseListItem = {
  id: string;
  name: string;
  training_type_code: string;
  difficulty_code: string;
  primary_body_area_codes: string[];
  required_equipment_codes: string[];
  media_asset_key: string | null;
};

export type ExerciseListResponse = {
  items: ExerciseListItem[];
  next_cursor: string | null;
  catalog_version: string;
};

export type ExerciseDetailResponse = {
  exercise_id: string;
  exercise_name: string;
  training_type_code: string;
  primary_body_area_codes: string[];
  instruction_summary: string;
  form_cues: string[];
  media_asset_key: string | null;
  /** Short-lived URL resolved by the backend; absent until the backend PR lands. */
  media_url?: string | null;
  mascot_animation_asset_key: string | null;
  instruction_content_version: string;
};

export type ExerciseVariantItem = {
  exercise_id: string;
  exercise_name: string;
  required_equipment_codes: string[];
  instruction_summary: string;
  form_cues: string[];
  media_asset_key: string | null;
  goal_preservation_code: string;
};

export type ExerciseVariantsResponse = {
  source_exercise_id: string;
  source_required_equipment_codes: string[];
  items: ExerciseVariantItem[];
  catalog_version: string;
  alternative_set_version: string | null;
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
  report_status_code: 'GENERATED' | 'ACKNOWLEDGED' | 'FAILED' | null;
};

export type PlanRevisionSourceCode = 'INITIAL' | 'AI' | 'USER';

export type PlanSafetyStatusCode =
  'PASS' | 'NEEDS_INPUT' | 'REVISE' | 'BLOCKED' | 'FAILED';

/**
 * A USER plan revision references a stored routine version and a location, not
 * an arbitrary exercise list. The server re-checks duration, location,
 * equipment and the saved safety exclusions against it.
 */
export type WeeklyPlanUserEdits = {
  routine_id: string;
  location_code: string;
};

export type WeeklyPlanRevisionRequest = {
  source_code: 'AI' | 'USER';
  expected_revision_sequence: number;
  user_edits: WeeklyPlanUserEdits | null;
};

export type WeeklyPlanRevisionResponse = {
  revision_id: string;
  week_start: string;
  week_end: string;
  revision_sequence: number;
  /** Coordinator-authored revisions only; the third AI request is refused. */
  ai_revision_count: 0 | 1 | 2;
  source_code: PlanRevisionSourceCode;
  source_weekly_report_id: string | null;
  safety_status_code: PlanSafetyStatusCode;
  routine: RoutineResponse | null;
  selected_location_code: string | null;
  finalized: boolean;
  finalized_at: string | null;
  revision_reason_codes: string[];
  finalization_reason_codes: string[];
  created_at: string;
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
  weekday_failure_summary: Record<
    string,
    {
      partial: number;
      not_completed: number;
      stopped_for_safety: number;
    }
  >;
  pattern_summary: {
    high_completion_windows: string[];
    high_completion_exercise_types: string[];
    high_completion_intensity_codes: string[];
    blocker_reason_codes: string[];
  };
  agent_summaries: Record<string, unknown> | null;
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
