import type { SexCode } from '../../api/types';

export const PROFILE_STEPS = [
  {
    key: 'nickname',
    title: '앱에서 어떻게 불러드릴까요?',
    intro: '닉네임은 나중에 바꿀 수 있어요.',
    required: true,
  },
  {
    key: 'birth',
    title: '생년월일을 알려주세요',
    intro: '주민등록번호 앞 6자리(YYMMDD)만 입력해요.',
    required: true,
  },
  {
    key: 'gender',
    title: '성별을 선택해주세요',
    intro: '운동 강도 기준에만 사용해요.',
    required: true,
  },
  {
    key: 'body',
    title: '키와 체중을 입력해주세요',
    intro: '운동 강도 계산에 쓰이는 필수 항목이에요.',
    required: true,
  },
  {
    key: 'goal',
    title: '운동 목표는 무엇인가요?',
    intro: '가장 가까운 하나를 골라주세요.',
    required: true,
  },
  {
    key: 'level',
    title: '운동 경험은 어느 정도예요?',
    intro: '지금 수준에 맞춰 시작할게요.',
    required: true,
  },
  {
    key: 'types',
    title: '어떤 운동을 선호해요?',
    intro: '여러 개 고를 수 있어요.',
    required: true,
  },
  {
    key: 'coach',
    title: '코칭 스타일을 골라주세요',
    intro: '헬끼가 말을 거는 방식이 달라져요.',
    required: true,
  },
  {
    key: 'place',
    title: '주로 어디서 운동해요?',
    intro: '장소에 맞는 동작으로 짜드려요.',
    required: true,
  },
  {
    key: 'duration',
    title: '한 번에 얼마나 운동할까요?',
    intro: '선택 사항이에요. 나중에 정해도 괜찮아요.',
    required: false,
  },
  {
    key: 'frequency',
    title: '주 몇 회를 목표로 할까요?',
    intro: '선택 사항이에요. 건너뛰고 나중에 정해도 돼요.',
    required: false,
  },
  {
    key: 'care',
    title: '주의하거나 불편한 부위가 있나요?',
    intro:
      '해당하는 부위를 모두 골라주세요. 그 부위에 부담이 적은 동작으로 짜드려요.',
    required: false,
  },
  {
    key: 'summary',
    title: '입력 내용을 확인해주세요',
    intro: '마지막이에요. 확인하고 등록을 마쳐주세요.',
    required: false,
  },
] as const;

export type ProfileStepKey = (typeof PROFILE_STEPS)[number]['key'];

export const PROFILE_PREVIEW_OPTIONS = [
  { id: 'editing', label: '입력' },
  { id: 'reason', label: '진입 안내' },
  { id: 'validation-error', label: '검증 오류' },
  { id: 'saving', label: '저장 중' },
  { id: 'save-error', label: '저장 실패' },
  { id: 'exit', label: '이탈 확인' },
  { id: 'done', label: '등록 완료' },
] as const;

export type ProfilePreviewState =
  (typeof PROFILE_PREVIEW_OPTIONS)[number]['id'];

export const PROFILE_SEX_OPTIONS = [
  { code: 'FEMALE', label: '여성' },
  { code: 'MALE', label: '남성' },
  { code: 'PREFER_NOT_TO_SAY', label: '선택 안 함' },
] as const satisfies readonly { code: SexCode; label: string }[];

export const PROFILE_BODY_LIMITS = {
  heightCm: { min: 80, max: 250 },
  weightKg: { min: 25, max: 300 },
} as const;

export type ProfileForm = {
  nickname: string;
  birth: string;
  adult: boolean;
  sexCode: SexCode | null;
  heightCm: string;
  weightKg: string;
  goal: string;
  level: string;
  types: string[];
  coach: string;
  place: string;
  duration: string;
  frequency: string;
  care: string[];
  careEtc: string;
};

export const PROFILE_INITIAL_FORM: ProfileForm = {
  nickname: '헬끼친구',
  birth: '990312',
  adult: true,
  sexCode: 'PREFER_NOT_TO_SAY',
  heightCm: '170',
  weightKg: '65',
  goal: '건강 유지',
  level: '초급',
  types: ['근력', '스트레칭'],
  coach: '든든하게',
  place: '집',
  duration: '30',
  frequency: '주 3회',
  care: ['없음'],
  careEtc: '',
};

export const GOAL_OPTIONS = [
  '체중 감량',
  '근육 증가',
  '체력 향상',
  '자세 교정',
  '건강 유지',
] as const;
export const LEVEL_OPTIONS = [
  { label: '입문', description: '운동을 거의 해본 적 없어요.' },
  { label: '초급', description: '가끔 하지만 루틴은 없어요.' },
  { label: '중급', description: '기본 동작과 루틴에 익숙해요.' },
  { label: '복귀', description: '쉬었다가 다시 시작해요.' },
] as const;
export const TYPE_OPTIONS = ['근력', '유산소', '홈트', '스트레칭'] as const;
export const COACH_OPTIONS = [
  { label: '차분하게', description: '담백한 안내와 기록 중심으로.' },
  { label: '든든하게', description: '적당한 응원과 함께 밀어줄게요.' },
  { label: '강하게', description: '목표를 밀어붙이는 스타일이에요.' },
] as const;
export const PLACE_OPTIONS = ['헬스장', '집'] as const;
export const FREQUENCY_OPTIONS = [
  '주 1회',
  '주 2회',
  '주 3회',
  '주 4회',
  '주 5회+',
] as const;
export const CARE_OPTIONS = [
  '없음',
  '어깨',
  '목',
  '허리',
  '무릎',
  '손목',
  '발목',
  '기타',
] as const;
