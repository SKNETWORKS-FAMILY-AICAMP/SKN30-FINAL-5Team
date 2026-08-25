export type WorkoutPreviewState =
  | 'active'
  | 'offline'
  | 'partial'
  | 'all-blocks'
  | 'rest'
  | 'not-completed'
  | 'safety'
  | 'symptom-mild'
  | 'symptom-severe'
  | 'completed'
  | 'stopped';

export const WORKOUT_PREVIEW_OPTIONS = [
  { id: 'active', label: '일반 진행' },
  { id: 'offline', label: '오프라인 진행' },
  { id: 'partial', label: '일부 블록 완료' },
  { id: 'all-blocks', label: '전체 블록 체크' },
  { id: 'rest', label: '선택 휴식' },
  { id: 'not-completed', label: '미수행 이유' },
  { id: 'safety', label: '안전 중단 확인' },
  { id: 'symptom-mild', label: '경미한 불편' },
  { id: 'symptom-severe', label: '중대한 이상 반응' },
  { id: 'completed', label: '완료 결과' },
  { id: 'stopped', label: '안전 중단 결과' },
] as const satisfies readonly {
  id: WorkoutPreviewState;
  label: string;
}[];

export const WORKOUT_CAROUSEL = {
  CARD_WIDTH: 230,
  GAP: 20,
  STRIDE: 250,
  CARD_HEIGHT: 320,
} as const;

export type WorkoutResponsiveLayout = {
  cardHeight: number;
  cardWidth: number;
  contentMaxWidth: number;
  gap: number;
  headerTopPadding: number;
  mascotHeight: number;
  stride: number;
};

/**
 * Keeps controls readable on large browser viewports without scaling the
 * phone composition indefinitely, while reclaiming vertical space on short
 * phones. The workout order stays timer -> mascot -> ordered blocks at every
 * breakpoint.
 */
export function getWorkoutResponsiveLayout({
  height,
  width,
}: {
  height: number;
  width: number;
}): WorkoutResponsiveLayout {
  const tablet = width >= 600;
  const desktop = width >= 1024;
  const cardWidth = desktop ? 340 : tablet ? 300 : WORKOUT_CAROUSEL.CARD_WIDTH;
  const gap = tablet ? 24 : WORKOUT_CAROUSEL.GAP;

  let cardHeight: number = WORKOUT_CAROUSEL.CARD_HEIGHT;
  let mascotHeight = 220;
  let headerTopPadding = 54;

  if (height < 650) {
    cardHeight = 210;
    mascotHeight = 90;
    headerTopPadding = 28;
  } else if (height < 800) {
    cardHeight = 240;
    mascotHeight = 130;
    headerTopPadding = 42;
  } else if (height < 900) {
    cardHeight = 280;
    mascotHeight = 180;
  }

  return {
    cardHeight,
    cardWidth,
    contentMaxWidth: 1100,
    gap,
    headerTopPadding,
    mascotHeight,
    stride: cardWidth + gap,
  };
}

export const WORKOUT_ARC = {
  INPUT_OFFSETS: [-2, -1, 0, 1, 2],
  LIFT: [104, 26, 0, 26, 104],
  SCALE: [0.74, 0.87, 1, 0.87, 0.74],
  OPACITY: [0.31, 0.43, 1, 0.43, 0.31],
  ROTATE: ['14deg', '7deg', '0deg', '-7deg', '-14deg'],
} as const;

export type WorkoutBlockStatus = 'PENDING' | 'COMPLETED';

export type WorkoutBlock = {
  id: string;
  name: string;
  meta: string;
  tips: readonly string[];
};

export const WORKOUT_BLOCKS: readonly WorkoutBlock[] = [
  {
    id: 'warm-up',
    name: '준비 운동',
    meta: '1세트 × 10회 · 스트레칭',
    tips: ['호흡을 편안하게 유지해요.', '천천히 움직임 범위를 넓혀요.'],
  },
  {
    id: 'push-up',
    name: '푸시업',
    meta: '3세트 × 10회 · 휴식 60초',
    tips: [
      '손은 어깨보다 살짝 넓게 짚어요.',
      '허리가 꺼지지 않게 배에 힘을 유지해요.',
      '힘들면 무릎을 대고 진행해도 좋아요.',
    ],
  },
  {
    id: 'band-row',
    name: '밴드 로우',
    meta: '3세트 × 12회 · 휴식 60초',
    tips: [
      '가슴을 펴고 견갑골을 뒤로 모아요.',
      '팔이 아니라 등으로 당기는 느낌으로 진행해요.',
    ],
  },
  {
    id: 'shoulder-press',
    name: '숄더 프레스',
    meta: '2세트 × 10회 · 휴식 90초',
    tips: [
      '허리를 젖히지 말고 갈비뼈를 닫아요.',
      '어깨에 불편함이 생기면 동작을 멈춰요.',
    ],
  },
  {
    id: 'cool-down',
    name: '마무리 스트레칭',
    meta: '1세트 × 10회 · 호흡 정리',
    tips: ['반동 없이 편안한 범위에서 유지해요.'],
  },
] as const;

export const WORKOUT_SYMPTOMS = [
  { code: 'PAIN', label: '통증' },
  { code: 'DIZZINESS', label: '어지러움' },
  { code: 'BREATHING_DIFFICULTY', label: '호흡 곤란' },
  { code: 'NAUSEA', label: '메스꺼움' },
  { code: 'EQUIPMENT_ISSUE', label: '기구 문제' },
  { code: 'OTHER', label: '기타' },
] as const;

export const WORKOUT_SEVERITIES = [
  { code: 'MILD', label: '가벼움' },
  { code: 'MODERATE', label: '보통' },
  { code: 'SEVERE', label: '심함' },
] as const;

export const NOT_COMPLETED_REASONS = [
  { code: 'TIME_SHORTAGE', label: '시간이 부족했어요' },
  { code: 'FATIGUE', label: '피로가 컸어요' },
  { code: 'MUSCLE_SORENESS', label: '근육통이 있었어요' },
  { code: 'PAIN', label: '통증이 있었어요' },
  { code: 'SCHEDULE_CHANGE', label: '일정이 바뀌었어요' },
  { code: 'LOW_MOTIVATION', label: '오늘은 마음이 내키지 않았어요' },
] as const;

export const SAFETY_GUIDANCE = {
  mild: '불편한 부위에 부담이 가는 동작은 제외하고 진행할게요. 움직이는 동안 불편함이 커지면 운동을 중단해주세요.',
  severePain:
    '오늘 운동은 진행하지 않는 것이 좋습니다. 갑작스럽거나 심한 통증, 붓기, 변형 또는 체중을 싣기 어려운 상태라면 의료 전문가의 확인을 받아주세요.',
  emergency:
    '운동을 즉시 중단해주세요. 가슴의 압박감이나 통증, 예상하지 못한 심한 숨참, 실신 또는 심한 어지럼 등의 증상이 있다면 즉시 지역 응급의료 도움을 요청하세요.',
} as const;

export type WorkoutSafetyInstruction =
  'SHOW_CAUTION' | 'STOP_SESSION' | 'STOP_AND_SEEK_HELP';

export type WorkoutSafetyReport = {
  symptomCode: (typeof WORKOUT_SYMPTOMS)[number]['code'];
  severityCode: (typeof WORKOUT_SEVERITIES)[number]['code'];
};
