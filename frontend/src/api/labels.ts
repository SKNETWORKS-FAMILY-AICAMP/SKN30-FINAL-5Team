/**
 * Presentation labels for stable machine codes.
 *
 * The server owns the decision; this file only owns how a code reads in Korean.
 * Unknown codes fall back to the code itself rather than guessing, so a new
 * server code shows up as visibly unmapped instead of silently mislabelled.
 */

import type {
  ActionCode,
  DiscomfortSeverityCode,
  FatigueLevelCode,
  NotCompletedReasonCode,
  SessionStatusCode,
} from './types';

function lookup<T extends string>(
  table: Record<string, string>,
  code: T | string,
): string {
  return table[code] ?? code;
}

const ACTION: Record<string, string> = {
  KEEP: '계획대로 진행',
  DOWNSHIFT: '강도 낮춰 진행',
  CHANGE: '구성 변경',
  RECOVERY: '회복 운동',
  REST: '오늘은 휴식',
  STOP_AND_SEEK_HELP: '운동 중단',
};

const ACTION_DESCRIPTION: Record<string, string> = {
  KEEP: '오늘 상태에 맞춰 계획한 루틴을 그대로 진행해요.',
  DOWNSHIFT: '요청한 시간은 그대로 두고 부담만 낮췄어요.',
  CHANGE: '오늘 상태에 맞게 운동 구성을 바꿨어요.',
  RECOVERY: '가볍게 몸을 회복하는 구성으로 준비했어요.',
  REST: '오늘은 쉬어가는 것이 좋겠어요.',
  STOP_AND_SEEK_HELP: '운동을 중단하고 도움을 받아주세요.',
};

const SESSION_STATUS: Record<string, string> = {
  PLANNED: '시작 전',
  IN_PROGRESS: '진행 중',
  COMPLETED: '완료',
  PARTIAL: '일부 완료',
  NOT_COMPLETED: '미수행',
  STOPPED_FOR_SAFETY: '안전 중단',
};

const FATIGUE: Record<string, string> = {
  LOW: '가벼움',
  MODERATE: '보통',
  HIGH: '높음',
};

const SEVERITY: Record<string, string> = {
  MILD: '가벼움',
  MODERATE: '보통',
  SEVERE: '심함',
};

const BODY_AREA: Record<string, string> = {
  NECK: '목',
  SHOULDER: '어깨',
  ELBOW: '팔꿈치',
  WRIST_HAND: '손목·손',
  UPPER_BACK: '등 위쪽',
  LOWER_BACK: '허리',
  HIP: '고관절',
  KNEE: '무릎',
  ANKLE_FOOT: '발목·발',
  CHEST: '가슴',
  ABDOMEN: '복부',
  GENERALIZED: '전신',
  OTHER: '기타 부위',
};

const ADVERSE_REACTION: Record<string, string> = {
  CHEST_DISCOMFORT: '가슴 압박감 또는 통증',
  UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH: '예상하지 못한 심한 숨참',
  SEVERE_DIZZINESS: '심한 어지럼',
  FAINTING: '실신',
  SUDDEN_WEAKNESS_OR_NUMBNESS: '갑작스러운 힘 빠짐 또는 저림',
  RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS:
    '증상을 동반한 빠르거나 불규칙한 심박',
  SUDDEN_SEVERE_PAIN: '갑작스러운 심한 통증',
  ACUTE_SWELLING_OR_DEFORMITY: '급성 부종 또는 변형',
  CANNOT_BEAR_WEIGHT: '체중을 싣기 어려움',
  OTHER_SERIOUS_REACTION: '그 밖의 심각한 이상 반응',
};

const NOT_COMPLETED_REASON: Record<string, string> = {
  TIME_SHORTAGE: '시간이 부족했어요',
  FATIGUE: '피로가 컸어요',
  MUSCLE_SORENESS: '근육통이 있었어요',
  PAIN: '통증이 있었어요',
  SCHEDULE_CHANGE: '일정이 바뀌었어요',
  LOCATION_EQUIPMENT: '장소나 장비가 맞지 않았어요',
  WEATHER: '날씨 때문이었어요',
  DIFFICULTY: '동작이 어려웠어요',
  LOW_INTEREST: '흥미가 생기지 않았어요',
  LOW_MOTIVATION: '오늘은 마음이 내키지 않았어요',
};

const PHASE: Record<string, string> = {
  WARMUP: '준비',
  MAIN: '본운동',
  COOLDOWN: '마무리',
};

const TRAINING_TYPE: Record<string, string> = {
  STRENGTH: '근력',
  CARDIO: '유산소',
  MOBILITY: '가동성',
};

const BODY_FOCUS: Record<string, string> = {
  UPPER_BODY: '상체',
  LOWER_BODY: '하체',
  CORE: '코어',
  FULL_BODY: '전신',
};

const LOCATION: Record<string, string> = {
  HOME: '집',
  GYM: '헬스장',
  OUTDOOR: '야외',
};

const EQUIPMENT: Record<string, string> = {
  BODYWEIGHT: '맨몸',
  DUMBBELL: '덤벨',
  BARBELL: '바벨',
  KETTLEBELL: '케틀벨',
  CABLE_MACHINE: '케이블',
  MACHINE: '머신',
  HOUSEHOLD_WEIGHT: '생활용품',
  BENCH: '벤치',
  PULL_UP_BAR: '철봉',
  RESISTANCE_BAND: '밴드',
  MAT: '매트',
  STABILITY_BALL: '짐볼',
  CHAIR: '의자',
};

const PRIMARY_GOAL: Record<string, string> = {
  GENERAL_FITNESS: '건강 유지',
};

const EXPERIENCE_LEVEL: Record<string, string> = {
  BEGINNER: '입문·초급',
};

const COACHING_STYLE: Record<string, string> = {
  SUPPORTIVE: '든든하게',
  CONCISE: '간결하게',
  ENERGETIC: '활기차게',
  // Older preview fixtures used this value before the stable contract landed.
  FRIENDLY: '든든하게',
};

const AGENT_TYPE: Record<string, string> = {
  TRAINING: '트레이닝',
  RECOVERY: '회복',
  SAFETY: '안전',
  FEASIBILITY: '실행 가능성',
  COORDINATOR: '조정',
};

const ADJUSTMENT_DIRECTION: Record<string, string> = {
  MAINTAIN: '현재 수준 유지',
  INCREASE: '조금 늘리기',
  REDUCE: '조금 줄이기',
  MIXED: '수행 결과에 맞춰 조정',
  // Kept for older cached responses that predate the current API contract.
  DECREASE: '조금 줄이기',
};

const DECISION_REASON: Record<string, string> = {
  PRIMARY_GOAL_PRESERVED: '운동 목표를 유지했어요.',
  MODERATE_FATIGUE_DOWNSHIFT: '오늘의 피로도를 고려해 부담을 낮췄어요.',
  LOW_FATIGUE_LOAD_ACCEPTED: '현재 피로도에 맞는 운동량을 유지했어요.',
  AVAILABLE_EQUIPMENT_INSUFFICIENT: '사용 가능한 장비를 고려했어요.',
  CURRENT_LOCATION_UNSUPPORTED: '현재 장소에서 가능한 운동을 확인했어요.',
  TIME_LOCATION_EQUIPMENT_MATCHED:
    '희망 시간과 장소, 장비 조건을 모두 확인했어요.',
  EMERGENCY_REACTION_REPORTED: '보고한 이상 반응을 안전 판단에 반영했어요.',
  ACUTE_OR_SEVERE_INPUT_REPORTED:
    '강한 통증이나 이상 반응을 안전 판단에 반영했어요.',
  NO_SAFETY_SIGNAL_REPORTED: '보고된 위험 신호가 없는지 확인했어요.',
  SAFETY_EXERCISES_REPLACED:
    '부담이 될 수 있는 운동을 안전한 구성으로 바꿨어요.',
  APPROVED_ALTERNATIVE_UNAVAILABLE: '안전하게 대체할 운동을 확인하지 못했어요.',
  NO_APPLICABLE_SAFETY_RESTRICTION:
    '현재 상태에 필요한 안전 제한을 확인했어요.',
  COMMON_CANDIDATE_SELECTED: '여러 조건을 함께 만족하는 루틴을 선택했어요.',
};

const PLAN_REVISION_REASON: Record<string, string> = {
  REVISION_ALLOWED: '요청한 루틴 조정을 적용했어요.',
  AI_REVISION_LIMIT_REACHED: '이번 주 추천 가능 횟수를 모두 사용했어요.',
  ROUTINE_REQUIRED: '적용할 수 있는 루틴이 필요해요.',
  ROUTINE_FORBIDDEN: '현재 상태에서는 해당 루틴을 적용할 수 없어요.',
  REQUESTED_DURATION_NOT_PRESERVED:
    '희망 운동 시간을 유지할 수 없어 조정을 적용하지 않았어요.',
  LOCATION_CONSTRAINT_NOT_SATISFIED:
    '선택한 장소에서 진행 가능한 구성을 찾지 못했어요.',
  EQUIPMENT_CONSTRAINT_NOT_SATISFIED:
    '현재 장비로 진행 가능한 구성을 찾지 못했어요.',
  SAFETY_OPINION_NOT_APPLIED:
    '안전 기준을 충족하지 않아 조정을 적용하지 않았어요.',
  REVISION_REJECTED: '요청한 루틴 조정을 적용하지 못했어요.',
  REVISION_STATUS_BLOCKS_FINALIZE:
    '안전 확인이 끝나지 않아 루틴을 확정하지 않았어요.',
  PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED:
    '지난 주 리포트를 확인한 뒤 다음 계획을 확정할 수 있어요.',
  FINALIZE_ALLOWED: '안전 확인을 마치고 루틴을 확정했어요.',
};

export const actionLabel = (code: ActionCode | string) => lookup(ACTION, code);
export const actionDescription = (code: ActionCode | string) =>
  lookup(ACTION_DESCRIPTION, code);
export const sessionStatusLabel = (code: SessionStatusCode | string) =>
  lookup(SESSION_STATUS, code);
export const fatigueLabel = (code: FatigueLevelCode | string) =>
  lookup(FATIGUE, code);
export const severityLabel = (code: DiscomfortSeverityCode | string) =>
  lookup(SEVERITY, code);
export const bodyAreaLabel = (code: string) => lookup(BODY_AREA, code);
export const adverseReactionLabel = (code: string) =>
  lookup(ADVERSE_REACTION, code);
export const notCompletedReasonLabel = (
  code: NotCompletedReasonCode | string,
) => lookup(NOT_COMPLETED_REASON, code);
export const phaseLabel = (code: string) => lookup(PHASE, code);
export const trainingTypeLabel = (code: string) => lookup(TRAINING_TYPE, code);
export const bodyFocusLabel = (code: string) => lookup(BODY_FOCUS, code);
export const locationLabel = (code: string) => lookup(LOCATION, code);
export const equipmentLabel = (code: string) => lookup(EQUIPMENT, code);
export const primaryGoalLabel = (code: string) => lookup(PRIMARY_GOAL, code);
export const experienceLevelLabel = (code: string) =>
  lookup(EXPERIENCE_LEVEL, code);
export const coachingStyleLabel = (code: string) =>
  lookup(COACHING_STYLE, code);
export const agentTypeLabel = (code: string) => lookup(AGENT_TYPE, code);
export const adjustmentDirectionLabel = (code: string) =>
  lookup(ADJUSTMENT_DIRECTION, code);
export const decisionReasonLabel = (code: string): string | null =>
  DECISION_REASON[code] ?? null;
export const planRevisionReasonLabel = (code: string): string | null =>
  PLAN_REVISION_REASON[code] ?? null;

export const BODY_AREA_OPTIONS = Object.entries(BODY_AREA).map(
  ([code, label]) => ({ code, label }),
);

export const ADVERSE_REACTION_OPTIONS = Object.entries(ADVERSE_REACTION).map(
  ([code, label]) => ({ code, label }),
);

export const NOT_COMPLETED_REASON_OPTIONS = Object.entries(
  NOT_COMPLETED_REASON,
).map(([code, label]) => ({ code: code as NotCompletedReasonCode, label }));

export const SEVERITY_OPTIONS = (
  ['MILD', 'MODERATE', 'SEVERE'] as DiscomfortSeverityCode[]
).map((code) => ({ code, label: severityLabel(code) }));

export const FATIGUE_OPTIONS = (
  ['LOW', 'MODERATE', 'HIGH'] as FatigueLevelCode[]
).map((code) => ({ code, label: fatigueLabel(code) }));

/**
 * A serious safety screen must not carry playful presentation. Screens ask this
 * rather than checking action codes themselves.
 */
export function isSeriousAction(code: ActionCode | string): boolean {
  return code === 'STOP_AND_SEEK_HELP' || code === 'REST';
}

export function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function formatMinutes(totalSeconds: number): string {
  return `${Math.round(totalSeconds / 60)}분`;
}

export function formatExercisePrescription({
  reps,
  sets,
  workSeconds,
}: {
  reps: number | null;
  sets: number;
  workSeconds?: number;
}): string {
  const prescription =
    reps === null
      ? `${sets}세트${
          workSeconds !== undefined && workSeconds > 0
            ? ` × ${formatKoreanDuration(workSeconds)}`
            : ''
        }`
      : `${sets}세트 × ${reps}회`;
  return prescription;
}

function formatKoreanDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}초`;
  if (seconds === 0) return `${minutes}분`;
  return `${minutes}분 ${seconds}초`;
}
