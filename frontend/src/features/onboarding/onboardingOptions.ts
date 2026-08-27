export const ONBOARDING_LOCATION_OPTIONS = [
  { code: 'HOME', label: '집' },
  { code: 'GYM', label: '헬스장' },
  { code: 'OUTDOOR', label: '야외' },
] as const;

export const ONBOARDING_EQUIPMENT_OPTIONS = [
  { code: 'BODYWEIGHT', label: '맨몸' },
  { code: 'DUMBBELL', label: '덤벨' },
  { code: 'BARBELL', label: '바벨' },
  { code: 'EZ_BAR', label: '이지바' },
  { code: 'KETTLEBELL', label: '케틀벨' },
  { code: 'CABLE_MACHINE', label: '케이블 머신' },
  { code: 'MACHINE', label: '웨이트 머신' },
  { code: 'HOUSEHOLD_WEIGHT', label: '생활 소도구' },
  { code: 'BENCH', label: '벤치' },
  { code: 'PULL_UP_BAR', label: '철봉' },
  { code: 'MAT', label: '매트' },
  { code: 'RESISTANCE_BAND', label: '밴드' },
  { code: 'STRETCH_STRAP', label: '스트레칭 스트랩' },
  { code: 'STABILITY_BALL', label: '짐볼' },
  { code: 'ELLIPTICAL_MACHINE', label: '일립티컬' },
  { code: 'JUMP_ROPE', label: '줄넘기' },
  { code: 'FOAM_ROLLER', label: '폼롤러' },
  { code: 'STATIONARY_BIKE', label: '실내 자전거' },
  { code: 'STEP_BOX', label: '스텝 박스' },
  { code: 'CHAIR', label: '의자' },
] as const;

// The complete goal and experience code lists are not yet public API
// contracts. Keep these options to deployment-approved codes and extend them
// only when docs/API_CONTRACT.md defines the additional machine codes.
export const ONBOARDING_GOAL_OPTIONS = [
  {
    code: 'GENERAL_FITNESS',
    label: '건강 유지',
    description: '꾸준히 움직이며 기초 체력을 만들고 싶어요.',
  },
] as const;

export const ONBOARDING_EXPERIENCE_OPTIONS = [
  {
    code: 'BEGINNER',
    label: '입문·초급',
    description: '운동이 처음이거나 아직 정해진 루틴이 없어요.',
  },
] as const;

export const ONBOARDING_EXERCISE_TYPE_OPTIONS = [
  { code: 'STRENGTH', label: '근력' },
  { code: 'CARDIO', label: '유산소' },
  { code: 'MOBILITY', label: '스트레칭' },
] as const;

export const ONBOARDING_DURATION = {
  min: 10,
  max: 240,
  step: 10,
} as const;

export const ONBOARDING_WEEKLY_COUNT = {
  min: 1,
  max: 7,
  step: 1,
} as const;
