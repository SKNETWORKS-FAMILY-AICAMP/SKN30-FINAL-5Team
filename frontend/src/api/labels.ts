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
  DECREASE: '조금 줄이기',
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
export const agentTypeLabel = (code: string) => lookup(AGENT_TYPE, code);
export const adjustmentDirectionLabel = (code: string) =>
  lookup(ADJUSTMENT_DIRECTION, code);

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
