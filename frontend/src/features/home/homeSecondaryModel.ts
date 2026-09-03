export type MapHomePreviewState = 'map' | 'routine' | 'condition';
export type CalendarReportPreviewState =
  'calendar' | 'week-detail' | 'month-picker';
export type MyPagePreviewState =
  | 'profile'
  | 'loading'
  | 'empty'
  | 'error'
  | 'permission'
  | 'logout'
  | 'withdraw';
export type CalendarDayStatus =
  'done' | 'partial' | 'miss' | 'rest' | 'today' | 'upcoming';
export type CalendarWeekState =
  'progress' | 'make' | 'unread' | 'read' | 'unavailable' | 'upcoming';

export type CalendarDay = {
  day: string;
  status: CalendarDayStatus;
  inCurrentMonth: boolean;
  /** Today is highlighted independently so it can coexist with a status mark. */
  isToday?: boolean;
  localDate?: string;
  sessionIds?: readonly string[];
};

export type CalendarMonthStat = {
  key: 'done' | 'partial' | 'rest' | 'miss';
  label: string;
  value: number;
  color: string;
};

export type CalendarWeek = {
  id: string;
  weekStart: string;
  label: string;
  range: string;
  state: CalendarWeekState;
  bandColor: string;
  days: readonly CalendarDay[];
  stats: readonly number[];
  note: string;
};

export const MAP_HOME_PREVIEW_OPTIONS = [
  { id: 'map', label: '맵 기본' },
  { id: 'routine', label: '최종 루틴' },
  { id: 'condition', label: '컨디션 정보' },
] as const satisfies readonly {
  id: MapHomePreviewState;
  label: string;
}[];

export const CALENDAR_REPORT_PREVIEW_OPTIONS = [
  { id: 'calendar', label: '캘린더' },
  { id: 'week-detail', label: '주차 상세' },
  { id: 'month-picker', label: '월 선택' },
] as const satisfies readonly {
  id: CalendarReportPreviewState;
  label: string;
}[];

export const MY_PAGE_PREVIEW_OPTIONS = [
  { id: 'profile', label: '마이페이지' },
  { id: 'loading', label: '불러오는 중' },
  { id: 'empty', label: '프로필 없음' },
  { id: 'error', label: '불러오기 실패' },
  { id: 'permission', label: '권한 없음' },
  { id: 'logout', label: '로그아웃 확인' },
  { id: 'withdraw', label: '회원 탈퇴 확인' },
] as const satisfies readonly {
  id: MyPagePreviewState;
  label: string;
}[];

export const CALENDAR_DAY_VISUALS = {
  done: {
    label: '완료',
    glyph: '✓',
    backgroundColor: '#5E8342',
    color: '#FFFFFF',
    borderColor: '#5E8342',
    accentColor: '#4F7238',
  },
  partial: {
    label: '부분 수행',
    glyph: '△',
    backgroundColor: '#F6BA50',
    color: '#6B520C',
    borderColor: '#F6BA50',
    accentColor: '#A45F00',
  },
  miss: {
    label: '미수행',
    glyph: '×',
    backgroundColor: '#FFFFFF',
    color: '#C0BBB1',
    borderColor: '#E2DED4',
    accentColor: '#9A968E',
  },
  rest: {
    label: '휴식',
    glyph: '–',
    backgroundColor: '#EDEAE2',
    color: '#8B8780',
    borderColor: '#EDEAE2',
    accentColor: '#6F6B63',
  },
  today: {
    label: '오늘',
    glyph: '',
    backgroundColor: 'transparent',
    color: 'transparent',
    borderColor: 'transparent',
    accentColor: '#A45F00',
  },
  upcoming: {
    label: '예정',
    glyph: '',
    backgroundColor: 'transparent',
    color: 'transparent',
    borderColor: 'transparent',
    accentColor: '#B7B2A8',
  },
} as const satisfies Record<
  CalendarDayStatus,
  {
    label: string;
    glyph: string;
    backgroundColor: string;
    color: string;
    borderColor: string;
    accentColor: string;
  }
>;

/**
 * One order for the four recorded statuses. The monthly summary, the calendar
 * legend and the expanded week summary all read from this list so labels,
 * icons and colors never drift apart.
 */
export const CALENDAR_STATUS_ORDER = [
  'done',
  'partial',
  'rest',
  'miss',
] as const satisfies readonly CalendarMonthStat['key'][];

export const CALENDAR_WEEK_CHIPS = {
  progress: {
    label: '진행 중',
    backgroundColor: '#FFFFFF',
    color: '#A45F00',
    borderColor: '#F1D39A',
    borderStyle: 'solid',
  },
  make: {
    label: '리포트 생성 가능!',
    backgroundColor: '#E7F3FA',
    color: '#356A85',
    borderColor: '#9CC5DF',
    borderStyle: 'solid',
  },
  unread: {
    label: '리포트 확인하기',
    backgroundColor: '#EDF3DD',
    color: '#5F7048',
    borderColor: '#C8D7AC',
    borderStyle: 'solid',
  },
  read: {
    label: '확인 완료',
    backgroundColor: '#EDF3DD',
    color: '#5F7048',
    borderColor: '#C8D7AC',
    borderStyle: 'solid',
  },
  unavailable: {
    label: '리포트 오류',
    backgroundColor: '#FDECE9',
    color: '#C2402F',
    borderColor: '#F5C9C1',
    borderStyle: 'solid',
  },
  upcoming: {
    label: '예정',
    backgroundColor: 'transparent',
    color: '#B7B2A8',
    borderColor: '#DFDBD2',
    borderStyle: 'dashed',
  },
} as const satisfies Record<
  CalendarWeekState,
  {
    label: string;
    backgroundColor: string;
    color: string;
    borderColor: string;
    borderStyle: 'solid' | 'dashed';
  }
>;

export const CALENDAR_WEEKDAYS = [
  { label: '월', color: '#9A968E' },
  { label: '화', color: '#9A968E' },
  { label: '수', color: '#9A968E' },
  { label: '목', color: '#9A968E' },
  { label: '금', color: '#9A968E' },
  { label: '토', color: '#5B7FB0' },
  { label: '일', color: '#C2402F' },
] as const;

export const CALENDAR_MONTH_STATS = [
  { key: 'done', label: '완료', value: 4, color: '#4F7238' },
  { key: 'partial', label: '부분 수행', value: 3, color: '#A45F00' },
  { key: 'rest', label: '휴식', value: 3, color: '#6F6B63' },
  { key: 'miss', label: '미수행', value: 1, color: '#9A968E' },
] as const satisfies readonly CalendarMonthStat[];

export const CALENDAR_WEEKS = [
  {
    id: 'week-1',
    weekStart: '2026-07-27',
    label: '1주차',
    range: '7.27 – 8.2',
    state: 'read',
    bandColor: '#FFF8E5',
    days: [
      { day: '27', status: 'done', inCurrentMonth: false },
      { day: '28', status: 'done', inCurrentMonth: false },
      { day: '29', status: 'partial', inCurrentMonth: false },
      { day: '30', status: 'done', inCurrentMonth: false },
      { day: '31', status: 'miss', inCurrentMonth: false },
      { day: '1', status: 'partial', inCurrentMonth: true },
      { day: '2', status: 'rest', inCurrentMonth: true },
    ],
    stats: [0, 1, 1, 0],
    note: '리포트를 확인한 주예요. 다시 열어볼 수 있어요.',
  },
  {
    id: 'week-2',
    weekStart: '2026-08-03',
    label: '2주차',
    range: '8.3 – 8.9',
    state: 'make',
    bandColor: '#F3F1EB',
    days: [
      { day: '3', status: 'rest', inCurrentMonth: true },
      { day: '4', status: 'done', inCurrentMonth: true },
      { day: '5', status: 'done', inCurrentMonth: true },
      { day: '6', status: 'partial', inCurrentMonth: true },
      { day: '7', status: 'done', inCurrentMonth: true },
      { day: '8', status: 'miss', inCurrentMonth: true },
      { day: '9', status: 'rest', inCurrentMonth: true },
    ],
    stats: [3, 1, 2, 1],
    note: '한 주가 끝났어요. 리포트를 만들면 이번 주 운동 패턴을 정리해드려요.',
  },
  {
    id: 'week-3',
    weekStart: '2026-08-10',
    label: '3주차',
    range: '8.10 – 8.16',
    state: 'progress',
    bandColor: '#FFEBC2',
    days: [
      { day: '10', status: 'done', inCurrentMonth: true },
      { day: '11', status: 'partial', inCurrentMonth: true },
      { day: '12', status: 'upcoming', inCurrentMonth: true, isToday: true },
      { day: '13', status: 'upcoming', inCurrentMonth: true },
      { day: '14', status: 'upcoming', inCurrentMonth: true },
      { day: '15', status: 'upcoming', inCurrentMonth: true },
      { day: '16', status: 'upcoming', inCurrentMonth: true },
    ],
    stats: [1, 1, 0, 0],
    note: '이번 주 운동을 진행하고 있어요. 남은 일정도 함께 채워봐요.',
  },
  {
    id: 'week-4',
    weekStart: '2026-08-17',
    label: '4주차',
    range: '8.17 – 8.23',
    state: 'upcoming',
    bandColor: '#FCFBF8',
    days: [
      { day: '17', status: 'upcoming', inCurrentMonth: true },
      { day: '18', status: 'upcoming', inCurrentMonth: true },
      { day: '19', status: 'upcoming', inCurrentMonth: true },
      { day: '20', status: 'upcoming', inCurrentMonth: true },
      { day: '21', status: 'upcoming', inCurrentMonth: true },
      { day: '22', status: 'upcoming', inCurrentMonth: true },
      { day: '23', status: 'upcoming', inCurrentMonth: true },
    ],
    stats: [0, 0, 0, 0],
    note: '아직 시작하지 않은 주예요.',
  },
  {
    id: 'week-5',
    weekStart: '2026-08-24',
    label: '5주차',
    range: '8.24 – 8.30',
    state: 'upcoming',
    bandColor: '#FBFCF8',
    days: [
      { day: '24', status: 'upcoming', inCurrentMonth: true },
      { day: '25', status: 'upcoming', inCurrentMonth: true },
      { day: '26', status: 'upcoming', inCurrentMonth: true },
      { day: '27', status: 'upcoming', inCurrentMonth: true },
      { day: '28', status: 'upcoming', inCurrentMonth: true },
      { day: '29', status: 'upcoming', inCurrentMonth: true },
      { day: '30', status: 'upcoming', inCurrentMonth: true },
    ],
    stats: [0, 0, 0, 0],
    note: '아직 시작하지 않은 주예요.',
  },
  {
    id: 'week-6',
    weekStart: '2026-08-31',
    label: '6주차',
    range: '8.31 – 9.6',
    state: 'upcoming',
    bandColor: '#FCFBF8',
    days: [
      { day: '31', status: 'upcoming', inCurrentMonth: true },
      { day: '1', status: 'upcoming', inCurrentMonth: false },
      { day: '2', status: 'upcoming', inCurrentMonth: false },
      { day: '3', status: 'upcoming', inCurrentMonth: false },
      { day: '4', status: 'upcoming', inCurrentMonth: false },
      { day: '5', status: 'upcoming', inCurrentMonth: false },
      { day: '6', status: 'upcoming', inCurrentMonth: false },
    ],
    stats: [0, 0, 0, 0],
    note: '아직 시작하지 않은 주예요.',
  },
] as const satisfies readonly CalendarWeek[];

export const MY_PAGE_PROFILE_ROWS = [
  ['primary_goal_code', '운동 목표', '체력 증진'],
  ['experience_level_code', '운동 경험', '초급'],
  ['available_location_codes', '운동 장소', '헬스장'],
  ['default_requested_duration_minutes', '운동 시간', '40분'],
  ['desired_weekly_workout_count', '주간 운동 횟수', '주 4회'],
  ['persistent_pains', '평소 불편한 부위', '무릎'],
] as const;

export const MY_PAGE_ACCOUNT_ROWS = [
  ['연동 기기', '없음'],
  ['개인정보 및 동의', ''],
  ['문의하기', ''],
  ['이용약관', ''],
  ['앱 버전', '0.1.0'],
] as const;
