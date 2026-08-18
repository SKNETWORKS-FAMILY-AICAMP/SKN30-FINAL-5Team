export type HomePreviewState =
  'pre-checkin' | 'checkin' | 'generating' | 'routine' | 'adjusted' | 'editing';

export const HOME_PREVIEW_OPTIONS = [
  { id: 'pre-checkin', label: '체크인 전' },
  { id: 'checkin', label: '체크인 sheet' },
  { id: 'generating', label: '루틴 생성 중' },
  { id: 'routine', label: '최종 추천' },
  { id: 'adjusted', label: '부담 조정' },
  { id: 'editing', label: '운동 편집' },
] as const satisfies readonly {
  id: HomePreviewState;
  label: string;
}[];

export const HOME_WEEK_DAYS = [
  { label: '월', completed: true },
  { label: '화', completed: true },
  { label: '수', completed: false },
  { label: '목', completed: false },
  { label: '금', completed: false },
  { label: '토', completed: false },
  { label: '일', completed: false },
] as const;

export type HomeRoutineItem = {
  id: string;
  name: string;
  prescription?: string;
};

export const HOME_ROUTINE_ITEMS: readonly HomeRoutineItem[] = [
  { id: 'warm-up', name: '준비 운동' },
  { id: 'push-up', name: '푸시업', prescription: '3세트 × 10회' },
  { id: 'band-row', name: '밴드 로우', prescription: '3세트 × 12회' },
  {
    id: 'shoulder-press',
    name: '숄더 프레스',
    prescription: '2세트 × 10회',
  },
  { id: 'cool-down', name: '마무리 스트레칭' },
] as const;

export const HOME_CHECKIN_OPTIONS = {
  condition: ['좋아요', '보통이에요', '낮아요'],
  sleep: ['충분해요', '보통이에요', '부족해요'],
  fatigue: ['괜찮아요', '보통이에요', '피곤해요'],
  discomfort: ['없음', '어깨', '허리', '무릎'],
} as const;
