export const ONBOARDING_LOCATION_OPTIONS = [
  { code: 'HOME', label: '집' },
  { code: 'GYM', label: '헬스장' },
] as const;

// FAT_LOSS, MUSCLE_GAIN, and INTERMEDIATE are intentionally exposed ahead of
// the backend deployment update. The API must add these values to its approved
// onboarding code lists before those selections can be submitted successfully.
export const ONBOARDING_GOAL_OPTIONS = [
  {
    code: 'FAT_LOSS',
    label: '다이어트',
    description: '체지방 감량을 목표로 꾸준히 운동하고 싶어요.',
  },
  {
    code: 'MUSCLE_GAIN',
    label: '근력 증가',
    description: '근력과 근육량을 차근차근 늘리고 싶어요.',
  },
  {
    code: 'GENERAL_FITNESS',
    label: '체력 증진',
    description: '꾸준히 움직이며 기초 체력을 만들고 싶어요.',
  },
] as const;

export const ONBOARDING_EXPERIENCE_OPTIONS = [
  {
    code: 'BEGINNER',
    label: '초급',
    description: '운동이 처음이거나 아직 정해진 루틴이 없어요.',
  },
  {
    code: 'INTERMEDIATE',
    label: '중급',
    description: '기본 동작과 정해진 운동 루틴에 익숙해요.',
  },
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

// Onboarding and my page must offer the same coaching styles under the same
// names, so both screens read the labels from here.
export const ONBOARDING_COACHING_STYLE_OPTIONS = [
  {
    code: 'SUPPORTIVE',
    label: '차근차근',
    description: '응원과 함께 편안하게 운동을 안내해요.',
  },
  {
    code: 'CONCISE',
    label: '딱 필요한 만큼',
    description: '꼭 필요한 내용만 간단하게 알려드려요.',
  },
  {
    code: 'ENERGETIC',
    label: '힘차게',
    description: '밝고 에너지 넘치게 운동을 함께해요.',
  },
] as const;
