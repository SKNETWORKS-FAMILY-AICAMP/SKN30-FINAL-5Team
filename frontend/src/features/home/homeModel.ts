import {
  bodyFocusLabel,
  formatExercisePrescription,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  DailyContextResponse,
  DiscomfortSeverityCode,
  FatigueLevelCode,
  SessionStatusCode,
  WorkoutPlan,
  WorkoutSessionLogSummary,
} from '../../api/types';
import { orderedWorkoutPlanItems } from '../../api/workoutPlan';

export type HomePreviewState =
  | 'pre-checkin'
  | 'checkin'
  | 'generating'
  | 'routine'
  | 'adjusted'
  | 'editing'
  | 'rest';

export const HOME_PREVIEW_OPTIONS = [
  { id: 'pre-checkin', label: '체크인 전' },
  { id: 'checkin', label: '체크인 sheet' },
  { id: 'generating', label: '재추천 중' },
  { id: 'routine', label: '최종 추천' },
  { id: 'adjusted', label: '부담 조정' },
  { id: 'editing', label: '운동 편집' },
  { id: 'rest', label: '휴식 선택' },
] as const satisfies readonly {
  id: HomePreviewState;
  label: string;
}[];

export const HOME_WEEK_DAYS = [
  { label: '월', completed: true, statusCodes: ['COMPLETED'] },
  { label: '화', completed: true, statusCodes: ['COMPLETED'] },
  { label: '수', completed: false, statusCodes: [] },
  { label: '목', completed: false, statusCodes: [] },
  { label: '금', completed: false, statusCodes: [] },
  { label: '토', completed: false, statusCodes: [] },
  { label: '일', completed: false, statusCodes: [] },
] as const;

export type HomeRoutineItem = {
  exerciseId?: string;
  id: string;
  instructionAvailable?: boolean;
  name: string;
  reps?: string;
  sets?: string;
  workSeconds?: number;
};

export type HomeCheckin = {
  discomforts: Record<string, DiscomfortSeverityCode>;
  fatigue: string;
  locationCode: string | null;
  sleepHours: string;
  workoutMinutes: string;
  adverseReactionCodes: string[];
};

export type HomeCheckinDraft = {
  fatigueLevelCode: FatigueLevelCode;
  requestedDurationMinutes: number;
  sleepHours: string;
  discomforts: Record<string, DiscomfortSeverityCode>;
  locationCode: string | null;
  adverseReactionCodes: string[];
};

export function sleepMinutesFromHours(
  hours: string,
): number | null | undefined {
  const trimmed = hours.trim();
  if (trimmed === '') {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0 || value > 24) {
    return undefined;
  }
  return Math.round(value * 60);
}

export const HOME_DEFAULT_CHECKIN: HomeCheckin = {
  discomforts: {},
  fatigue: '보통이에요',
  locationCode: null,
  sleepHours: '',
  workoutMinutes: '40',
  adverseReactionCodes: [],
};

export const HOME_CHECKIN_OPTIONS = {
  fatigue: ['피곤해요', '보통이에요', '가벼워요'],
  discomfort: ['없음', '어깨', '허리', '무릎'],
} as const;

export type HomeRoutineVariant = {
  focus: string;
  items: readonly HomeRoutineItem[];
  title: string;
};

export const HOME_ROUTINE_VARIANTS: readonly HomeRoutineVariant[] = [
  {
    title: '상체 근력 루틴',
    focus: '상체 근력',
    items: [
      { id: 'warm-up', name: '준비 운동' },
      { id: 'push-up', name: '푸시업', sets: '3', reps: '10' },
      { id: 'band-row', name: '밴드 로우', sets: '3', reps: '12' },
      { id: 'shoulder-press', name: '숄더 프레스', sets: '2', reps: '10' },
      { id: 'cool-down', name: '마무리 스트레칭' },
    ],
  },
  {
    title: '하체 집중 루틴',
    focus: '하체 근력',
    items: [
      { id: 'warm-up', name: '준비 운동' },
      { id: 'dumbbell-squat', name: '덤벨 스쿼트', sets: '3', reps: '12' },
      {
        id: 'romanian-deadlift',
        name: '루마니안 데드리프트',
        sets: '3',
        reps: '10',
      },
      { id: 'lunge', name: '런지', sets: '2', reps: '12' },
      { id: 'cool-down', name: '마무리 스트레칭' },
    ],
  },
  {
    title: '유산소 · 코어 루틴',
    focus: '유산소 · 코어',
    items: [
      { id: 'walk-warm-up', name: '준비 걷기 · 5분' },
      { id: 'interval-run', name: '인터벌 러닝 · 15분' },
      { id: 'plank', name: '플랭크 · 3세트 × 40초' },
      { id: 'core-bridge', name: '코어 브리지', sets: '2', reps: '15' },
      { id: 'walk-cool-down', name: '마무리 걷기 · 5분' },
    ],
  },
] as const;

export function getHomeRoutineVariant(index: number): HomeRoutineVariant {
  const fallback = HOME_ROUTINE_VARIANTS[0];
  if (!fallback) {
    throw new Error('Home routine variants must not be empty.');
  }
  return HOME_ROUTINE_VARIANTS[index] ?? fallback;
}

export const HOME_ROUTINE_ITEMS = getHomeRoutineVariant(0).items;

const FATIGUE_CODE_BY_LABEL: Record<string, FatigueLevelCode> = {
  피곤해요: 'HIGH',
  보통이에요: 'MODERATE',
  가벼워요: 'LOW',
};

const FATIGUE_LABEL_BY_CODE: Record<FatigueLevelCode, string> = {
  HIGH: '피곤해요',
  MODERATE: '보통이에요',
  LOW: '가벼워요',
};

export function apiCheckinDraft(checkin: HomeCheckin): HomeCheckinDraft {
  return {
    fatigueLevelCode: FATIGUE_CODE_BY_LABEL[checkin.fatigue] ?? 'MODERATE',
    requestedDurationMinutes: Number(checkin.workoutMinutes),
    sleepHours: checkin.sleepHours,
    discomforts: { ...checkin.discomforts },
    locationCode: checkin.locationCode,
    adverseReactionCodes: [...checkin.adverseReactionCodes],
  };
}

export function checkinFromContext(
  context: DailyContextResponse | null,
  defaultDurationMinutes: number,
  fallbackLocationCode: string | null = null,
): HomeCheckin {
  if (context === null) {
    return {
      ...HOME_DEFAULT_CHECKIN,
      discomforts: {},
      locationCode: fallbackLocationCode,
      workoutMinutes: String(defaultDurationMinutes),
      adverseReactionCodes: [],
    };
  }
  const sleepHours =
    context.sleep_minutes === null || context.sleep_minutes === undefined
      ? ''
      : String(Math.round((context.sleep_minutes / 60) * 10) / 10);
  return {
    ...HOME_DEFAULT_CHECKIN,
    discomforts: Object.fromEntries(
      context.discomforts.map(({ body_area_code, severity_code }) => [
        body_area_code,
        severity_code,
      ]),
    ),
    fatigue: FATIGUE_LABEL_BY_CODE[context.fatigue_level_code],
    locationCode: context.location_code,
    sleepHours,
    workoutMinutes: String(context.requested_duration_minutes),
    adverseReactionCodes: [...context.adverse_reaction_codes],
  };
}

export function routineItemsFromPlan(plan: WorkoutPlan): HomeRoutineItem[] {
  return orderedWorkoutPlanItems(plan.items).map((item) => ({
    exerciseId: item.exercise_id,
    id: item.plan_item_id,
    instructionAvailable: item.instruction_available,
    name: item.exercise_name,
    reps: item.reps === null ? undefined : String(item.reps),
    sets: String(item.sets),
    workSeconds: item.reps === null ? item.work_seconds : undefined,
  }));
}

export function routineTitleFromPlan(plan: WorkoutPlan): string {
  const focus =
    plan.body_focus_code === null ? '' : bodyFocusLabel(plan.body_focus_code);
  return `${focus ? `${focus} ` : ''}${trainingTypeLabel(plan.training_type_code)} 루틴`;
}

export function routineFocusFromPlan(plan: WorkoutPlan): string {
  const labels = [
    plan.body_focus_code === null ? null : bodyFocusLabel(plan.body_focus_code),
    trainingTypeLabel(plan.training_type_code),
  ];
  return labels.filter(Boolean).join(' · ');
}

const WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'] as const;

export function formatHomeDate(localDate: string): string {
  const date = parseLocalDate(localDate);
  if (date === null) {
    return localDate;
  }
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}.${month}.${day} (${WEEKDAY_LABELS[date.getDay()]})`;
}

export function formatWeekRange(weekStart: string, weekEnd: string): string {
  const start = parseLocalDate(weekStart);
  const end = parseLocalDate(weekEnd);
  if (start === null || end === null) {
    return `${weekStart} ~ ${weekEnd}`;
  }
  return `${start.getMonth() + 1}.${start.getDate()} ~ ${end.getMonth() + 1}.${end.getDate()}`;
}

export function formatWeekRangeForLocalDate(localDate: string): string {
  const weekStart = weekStartForLocalDate(localDate);
  if (weekStart === null) {
    return '이번 주';
  }
  const start = parseLocalDate(weekStart);
  if (start === null) {
    return '이번 주';
  }
  const end = new Date(
    start.getFullYear(),
    start.getMonth(),
    start.getDate() + 6,
  );
  return formatWeekRange(weekStart, localDateValue(end));
}

export function weekStartForLocalDate(localDate: string): string | null {
  const current = parseLocalDate(localDate);
  if (current === null) {
    return null;
  }
  const mondayOffset = (current.getDay() + 6) % 7;
  return localDateValue(
    new Date(
      current.getFullYear(),
      current.getMonth(),
      current.getDate() - mondayOffset,
    ),
  );
}

export function weekDaysFromSessions(
  weekStart: string,
  sessions: readonly WorkoutSessionLogSummary[],
): {
  label: string;
  completed: boolean;
  statusCodes: SessionStatusCode[];
}[] {
  const start = parseLocalDate(weekStart);
  if (start === null) {
    return Array.from(HOME_WEEK_DAYS, (day) => ({
      ...day,
      statusCodes: Array.from(day.statusCodes) as SessionStatusCode[],
    }));
  }
  const statusesByDate = new Map<string, SessionStatusCode[]>();
  for (const session of sessions) {
    const statuses = statusesByDate.get(session.local_date) ?? [];
    if (!statuses.includes(session.status_code)) {
      statuses.push(session.status_code);
    }
    statusesByDate.set(session.local_date, statuses);
  }
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(
      start.getFullYear(),
      start.getMonth(),
      start.getDate() + index,
    );
    const statusCodes = statusesByDate.get(localDateValue(date)) ?? [];
    return {
      label: WEEKDAY_LABELS[date.getDay()] ?? '',
      completed: statusCodes.includes('COMPLETED'),
      statusCodes,
    };
  });
}

function parseLocalDate(localDate: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  if (!match) {
    return null;
  }
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function localDateValue(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

export function copyRoutineItems(
  items: readonly HomeRoutineItem[],
): HomeRoutineItem[] {
  return Array.from(items, (item) => ({ ...item }));
}

export function parseRoutineItem(text: string, id = 'parsed'): HomeRoutineItem {
  const match = String(text).match(
    /^(.*?)\s*·\s*(\d+)\s*세트\s*×\s*(\d+)\s*회$/,
  );
  if (!match) {
    return { id, name: String(text) };
  }
  return {
    id,
    name: match[1] ?? '',
    sets: match[2] ?? '',
    reps: match[3] ?? '',
  };
}

export function formatRoutineItem(item: HomeRoutineItem): string | null {
  const name = String(item.name ?? '').trim();
  if (!name) {
    return null;
  }
  const sets = String(item.sets ?? '').replace(/[^0-9]/g, '');
  const reps = String(item.reps ?? '').replace(/[^0-9]/g, '');
  const hasTimedPrescription =
    item.workSeconds !== undefined && item.workSeconds > 0;
  return sets && (reps || hasTimedPrescription)
    ? `${name} · ${formatExercisePrescription({
        reps: reps ? Number(reps) : null,
        sets: Number(sets),
        workSeconds: item.workSeconds,
      })}`
    : name;
}

export function getHomeRerollLabel(rerolls: number, loading: boolean) {
  if (loading) {
    return '추천 받는 중…';
  }
  return rerolls >= 2 ? '추천 횟수 소진' : `다른 루틴 · ${2 - rerolls}회 남음`;
}
