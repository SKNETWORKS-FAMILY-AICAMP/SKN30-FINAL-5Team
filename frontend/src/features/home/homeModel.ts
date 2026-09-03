import {
  bodyFocusLabel,
  formatExercisePrescription,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  AvailabilitySlotInput,
  DailyContextResponse,
  FatigueLevelCode,
  PainAreaInput,
  PlanPhaseCode,
  SessionStatusCode,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import {
  orderedWorkoutPlanItems,
  planItemPhaseCode,
} from '../../api/workoutPlan';

export type HomePreviewState =
  | 'routine-lookup-loading'
  | 'routine-lookup-failed'
  | 'pre-checkin'
  | 'checkin'
  | 'generating'
  | 'generating-final'
  | 'routine'
  | 'decision-recovered'
  | 'decision-retry'
  | 'adjusted'
  | 'editing'
  | 'session-active'
  | 'session-resumable'
  | 'session-safety-stopped'
  | 'session-completed'
  | 'rest';

export const HOME_PREVIEW_OPTIONS = [
  { id: 'routine-lookup-loading', label: '기본 루틴 준비 중' },
  { id: 'routine-lookup-failed', label: '기본 루틴 준비 실패' },
  { id: 'pre-checkin', label: '저장된 기본 루틴 조회 완료' },
  { id: 'checkin', label: '체크인 sheet' },
  { id: 'generating', label: '재추천 중' },
  { id: 'generating-final', label: '완료 직전 (95%)' },
  { id: 'routine', label: '최종 추천' },
  { id: 'decision-recovered', label: '홈 재진입 · 오늘 결정 복구' },
  { id: 'decision-retry', label: '결정 응답 유실 · 재시도' },
  { id: 'adjusted', label: '부담 조정' },
  { id: 'editing', label: '운동 편집' },
  { id: 'session-active', label: '운동 진행 중 · 홈' },
  { id: 'session-resumable', label: '일반 중단 · 이어하기' },
  { id: 'session-safety-stopped', label: '안전 중단 · 조회 전용' },
  { id: 'session-completed', label: '오늘 운동 완료' },
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
  /** Reordering stays inside one phase (ADR-0018 D5). */
  phaseCode?: PlanPhaseCode;
  reps?: string;
  sets?: string;
  workSeconds?: number;
};

export type HomeAvailabilitySlot = {
  startTime: string;
  endTime: string;
};

export type HomeCheckin = {
  availableSlots: HomeAvailabilitySlot[] | null;
  pains: Record<string, number>;
  fatigue: string;
  locationCode: string | null;
  redFlagPresent: boolean | null;
  sleepHours: string;
  workoutMinutes: string;
};

export type HomeCheckinDraft = {
  availableSlots: HomeAvailabilitySlot[] | null;
  fatigueLevelCode: FatigueLevelCode;
  availableTimeMinutes: number;
  sleepHours: string;
  pains: Record<string, number>;
  locationCode: string | null;
  redFlagPresent: boolean;
};

/**
 * Presentation-only state for the Home screen. It deliberately lives outside
 * the public API types: today the adapter derives it from the existing
 * decision/session endpoints, and a future backend "today state" response can
 * replace that adapter without changing the screen.
 */
export type TodayRoutinePhase =
  | 'PRE_CHECKIN'
  | 'GENERATING'
  | 'DECISION_ERROR'
  | 'SAFETY_BLOCKED'
  | 'READY'
  | 'SESSION_PLANNED'
  | 'SESSION_ACTIVE'
  | 'STOPPED_RESUMABLE'
  | 'STOPPED_SAFETY'
  | 'COMPLETED';

export type TodayRoutineProgress = {
  sessionId: string;
  completedPlanItemIds: readonly string[];
  currentPlanItemId: string | null;
  completedItemCount: number;
  totalItemCount: number;
};

export type TodayRoutineCapabilities = {
  canCheckIn: boolean;
  canRequestAlternative: boolean;
  canEditRoutine: boolean;
  canReorderRoutine: boolean;
  canStart: boolean;
  canResume: boolean;
};

export type TodayRoutineViewState = {
  phase: TodayRoutinePhase;
  progress: TodayRoutineProgress | null;
  remainingAlternativeCount: number;
  capabilities: TodayRoutineCapabilities;
};

export type RoutineItemDraftOverride = {
  planItemId: string;
  sets: number;
  reps: number | null;
};

export type HomeRoutineEditDraft = {
  locationCode: string;
  itemOverrides: readonly RoutineItemDraftOverride[];
};

export type LocalWorkoutPresentationState = 'ACTIVE' | 'STOPPED_RESUMABLE';

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
  availableSlots: null,
  pains: {},
  fatigue: '보통이에요',
  locationCode: null,
  redFlagPresent: null,
  sleepHours: '',
  workoutMinutes: '',
};

export const HOME_CHECKIN_OPTIONS = {
  fatigue: ['피곤해요', '보통이에요', '가벼워요'],
  discomfort: ['없어요', '있어요'],
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
      { id: 'walk-warm-up', name: '준비 걷기', sets: '1', reps: '10' },
      { id: 'interval-run', name: '인터벌 러닝', sets: '3', reps: '10' },
      { id: 'plank', name: '플랭크', sets: '3', reps: '10' },
      { id: 'core-bridge', name: '코어 브리지', sets: '2', reps: '15' },
      { id: 'walk-cool-down', name: '마무리 걷기', sets: '1', reps: '10' },
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

const CLOCK_TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function isBlankSlot(slot: HomeAvailabilitySlot): boolean {
  return slot.startTime === '' && slot.endTime === '';
}

function clockMinutes(value: string, midnightAsDayEnd = false): number {
  const [hours = 0, minutes = 0] = value.split(':').map(Number);
  return midnightAsDayEnd && hours === 0 && minutes === 0
    ? 24 * 60
    : hours * 60 + minutes;
}

export function validateAvailabilitySlots(
  slots: readonly HomeAvailabilitySlot[] | null,
): string | null {
  if (slots === null) {
    return null;
  }
  const entered = slots.filter((slot) => !isBlankSlot(slot));
  if (
    entered.some(
      (slot) =>
        !CLOCK_TIME_PATTERN.test(slot.startTime) ||
        !CLOCK_TIME_PATTERN.test(slot.endTime),
    )
  ) {
    return '시작 시간과 종료 시간을 시간:분 형식으로 모두 입력해주세요.';
  }
  if (
    entered.some(
      (slot) =>
        clockMinutes(slot.startTime) >= clockMinutes(slot.endTime, true),
    )
  ) {
    return '종료 시간은 시작 시간보다 뒤여야 해요.';
  }
  const ordered = [...entered].sort((left, right) =>
    left.startTime.localeCompare(right.startTime),
  );
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1];
    const current = ordered[index];
    if (
      previous &&
      current &&
      clockMinutes(previous.endTime, true) >= clockMinutes(current.startTime)
    ) {
      return '가능한 시간대끼리는 겹치거나 맞닿을 수 없어요.';
    }
  }
  return null;
}

function enteredAvailabilitySlots(
  slots: readonly HomeAvailabilitySlot[] | null,
): HomeAvailabilitySlot[] | null {
  return slots === null
    ? null
    : slots.filter((slot) => !isBlankSlot(slot)).map((slot) => ({ ...slot }));
}

function localTimeFromDateTime(value: string): string {
  const match = /T(\d{2}):(\d{2})/.exec(value);
  return match ? `${match[1]}:${match[2]}` : '';
}

type DateTimeParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function dateTimeParts(date: Date, timeZone: string): DateTimeParts {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value);
  const result = {
    year: value('year'),
    month: value('month'),
    day: value('day'),
    hour: value('hour'),
    minute: value('minute'),
    second: value('second'),
  };
  if (Object.values(result).some((part) => !Number.isFinite(part))) {
    throw new Error('profile timezone could not be formatted');
  }
  return result;
}

function offsetMilliseconds(date: Date, timeZone: string): number {
  const parts = dateTimeParts(date, timeZone);
  return (
    Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    ) - date.getTime()
  );
}

function awareLocalDateTime(
  localDate: string,
  localTime: string,
  timeZone: string,
): string {
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  const timeMatch = /^(\d{2}):(\d{2})$/.exec(localTime);
  if (!dateMatch || !timeMatch) {
    throw new Error('invalid local availability date or time');
  }
  const desired: DateTimeParts = {
    year: Number(dateMatch[1]),
    month: Number(dateMatch[2]),
    day: Number(dateMatch[3]),
    hour: Number(timeMatch[1]),
    minute: Number(timeMatch[2]),
    second: 0,
  };
  const wallTimeMilliseconds = Date.UTC(
    desired.year,
    desired.month - 1,
    desired.day,
    desired.hour,
    desired.minute,
  );
  let offset = offsetMilliseconds(new Date(wallTimeMilliseconds), timeZone);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const next = offsetMilliseconds(
      new Date(wallTimeMilliseconds - offset),
      timeZone,
    );
    if (next === offset) {
      break;
    }
    offset = next;
  }
  const resolved = new Date(wallTimeMilliseconds - offset);
  const resolvedParts = dateTimeParts(resolved, timeZone);
  if (
    resolvedParts.year !== desired.year ||
    resolvedParts.month !== desired.month ||
    resolvedParts.day !== desired.day ||
    resolvedParts.hour !== desired.hour ||
    resolvedParts.minute !== desired.minute
  ) {
    throw new Error('availability time does not exist in profile timezone');
  }
  const offsetMinutes = Math.round(offset / 60_000);
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absolute = Math.abs(offsetMinutes);
  const offsetHours = String(Math.floor(absolute / 60)).padStart(2, '0');
  const offsetRemainder = String(absolute % 60).padStart(2, '0');
  return `${localDate}T${localTime}:00${sign}${offsetHours}:${offsetRemainder}`;
}

function nextLocalDate(localDate: string): string {
  const [year, month, day] = localDate.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    throw new Error('invalid local availability date');
  }
  const value = new Date(Date.UTC(year, month - 1, day + 1));
  return value.toISOString().slice(0, 10);
}

export function availabilitySlotsForRequest(
  slots: readonly HomeAvailabilitySlot[] | null,
  localDate: string,
  timeZone: string,
): AvailabilitySlotInput[] | null {
  const entered = enteredAvailabilitySlots(slots);
  return entered === null
    ? null
    : entered.map((slot) => ({
        start_at: awareLocalDateTime(localDate, slot.startTime, timeZone),
        end_at: awareLocalDateTime(
          slot.endTime === '00:00' ? nextLocalDate(localDate) : localDate,
          slot.endTime,
          timeZone,
        ),
      }));
}

export function apiCheckinDraft(checkin: HomeCheckin): HomeCheckinDraft {
  return {
    availableSlots: enteredAvailabilitySlots(checkin.availableSlots),
    fatigueLevelCode: FATIGUE_CODE_BY_LABEL[checkin.fatigue] ?? 'MODERATE',
    availableTimeMinutes: Number(checkin.workoutMinutes),
    sleepHours: checkin.sleepHours,
    pains: { ...checkin.pains },
    locationCode: checkin.locationCode,
    redFlagPresent: checkin.redFlagPresent ?? false,
  };
}

function normalizedCheckinDraft(draft: HomeCheckinDraft) {
  return {
    ...draft,
    sleepHours: draft.sleepHours.trim(),
    pains: Object.fromEntries(
      Object.entries(draft.pains).sort(([left], [right]) =>
        left.localeCompare(right),
      ),
    ),
    availableSlots:
      draft.availableSlots === null
        ? null
        : draft.availableSlots.map((slot) => ({ ...slot })),
  };
}

/** Equality only selects the request path; unchanged input remains submitable. */
export function homeCheckinDraftsEqual(
  left: HomeCheckinDraft,
  right: HomeCheckinDraft,
): boolean {
  return (
    JSON.stringify(normalizedCheckinDraft(left)) ===
    JSON.stringify(normalizedCheckinDraft(right))
  );
}

export function routineItemOverrides(
  original: readonly HomeRoutineItem[],
  edited: readonly HomeRoutineItem[],
): RoutineItemDraftOverride[] {
  const originalById = new Map(original.map((item) => [item.id, item]));
  return edited.flatMap((item) => {
    const before = originalById.get(item.id);
    const sets = Number(item.sets);
    const reps = item.reps === undefined ? null : Number(item.reps);
    if (
      before === undefined ||
      !Number.isInteger(sets) ||
      sets < 1 ||
      (reps !== null && (!Number.isInteger(reps) || reps < 1))
    ) {
      return [];
    }
    if (before.sets === item.sets && before.reps === item.reps) {
      return [];
    }
    return [{ planItemId: item.id, sets, reps }];
  });
}

export function applyRoutineItemOverrides(
  items: readonly HomeRoutineItem[],
  overrides: readonly RoutineItemDraftOverride[],
): HomeRoutineItem[] {
  const byId = new Map(
    overrides.map((override) => [override.planItemId, override]),
  );
  return items.map((item) => {
    const override = byId.get(item.id);
    return override === undefined
      ? { ...item }
      : {
          ...item,
          sets: String(override.sets),
          reps: override.reps === null ? undefined : String(override.reps),
        };
  });
}

export function deriveTodayRoutineViewState({
  alternativeUsedCount,
  contextExists,
  decisionError,
  decisionHasPlan,
  decisionIsBlocked,
  generationPending,
  localSessionState = 'ACTIVE',
  session,
}: {
  alternativeUsedCount: number;
  contextExists: boolean;
  decisionError: boolean;
  decisionHasPlan: boolean;
  decisionIsBlocked: boolean;
  generationPending: boolean;
  localSessionState?: LocalWorkoutPresentationState;
  session: WorkoutSessionDetailResponse | null;
}): TodayRoutineViewState {
  const remainingAlternativeCount = Math.max(
    0,
    2 - Math.max(0, Math.min(2, alternativeUsedCount)),
  );
  let phase: TodayRoutinePhase;
  let progress: TodayRoutineProgress | null = null;

  if (session !== null) {
    const completedPlanItemIds = session.items
      .filter((item) => item.status_code === 'COMPLETED')
      .map((item) => item.plan_item_id);
    progress = {
      sessionId: session.session_id,
      completedPlanItemIds,
      currentPlanItemId:
        session.items.find((item) => item.status_code !== 'COMPLETED')
          ?.plan_item_id ?? null,
      completedItemCount: session.completed_item_count,
      totalItemCount: session.total_item_count,
    };
    if (session.status_code === 'STOPPED_FOR_SAFETY') {
      phase = 'STOPPED_SAFETY';
    } else if (
      session.status_code === 'COMPLETED' ||
      session.status_code === 'PARTIAL' ||
      session.status_code === 'NOT_COMPLETED'
    ) {
      phase = 'COMPLETED';
    } else if (session.status_code === 'PLANNED') {
      phase = 'SESSION_PLANNED';
    } else if (localSessionState === 'STOPPED_RESUMABLE') {
      phase = 'STOPPED_RESUMABLE';
    } else {
      phase = 'SESSION_ACTIVE';
    }
  } else if (generationPending) {
    phase = 'GENERATING';
  } else if (decisionIsBlocked) {
    phase = 'SAFETY_BLOCKED';
  } else if (decisionError) {
    phase = 'DECISION_ERROR';
  } else if (decisionHasPlan) {
    phase = 'READY';
  } else {
    phase = 'PRE_CHECKIN';
  }

  const unlocked = phase === 'READY';
  return {
    phase,
    progress,
    remainingAlternativeCount,
    capabilities: {
      canCheckIn:
        phase === 'PRE_CHECKIN' ||
        phase === 'DECISION_ERROR' ||
        phase === 'SAFETY_BLOCKED',
      canRequestAlternative: unlocked && remainingAlternativeCount > 0,
      canEditRoutine: unlocked,
      canReorderRoutine:
        unlocked || phase === 'SESSION_ACTIVE' || phase === 'STOPPED_RESUMABLE',
      canStart: phase === 'READY',
      canResume:
        phase === 'SESSION_PLANNED' ||
        phase === 'SESSION_ACTIVE' ||
        phase === 'STOPPED_RESUMABLE',
    },
  };
}

export function checkinFromContext(
  context: DailyContextResponse | null,
  persistentPains: readonly PainAreaInput[] = [],
  fallbackLocationCode: string | null = null,
): HomeCheckin {
  if (context === null) {
    return {
      ...HOME_DEFAULT_CHECKIN,
      pains: Object.fromEntries(
        persistentPains.map(({ body_area_code, intensity_score }) => [
          body_area_code,
          intensity_score,
        ]),
      ),
      locationCode: fallbackLocationCode,
    };
  }
  const sleepHours =
    context.sleep_minutes === null || context.sleep_minutes === undefined
      ? ''
      : String(Math.round((context.sleep_minutes / 60) * 10) / 10);
  return {
    ...HOME_DEFAULT_CHECKIN,
    availableSlots:
      context.available_slots?.map((slot) => ({
        startTime: localTimeFromDateTime(slot.start_at),
        endTime: localTimeFromDateTime(slot.end_at),
      })) ?? null,
    pains: Object.fromEntries(
      context.pains.map(({ body_area_code, intensity_score }) => [
        body_area_code,
        intensity_score,
      ]),
    ),
    fatigue: FATIGUE_LABEL_BY_CODE[context.fatigue_level_code],
    locationCode: context.location_code,
    sleepHours,
    workoutMinutes: String(context.available_time_minutes),
    redFlagPresent: context.red_flag_present,
  };
}

export function routineItemsFromPlan(plan: WorkoutPlan): HomeRoutineItem[] {
  return orderedWorkoutPlanItems(plan.items).map((item) => ({
    exerciseId: item.exercise_id,
    id: item.plan_item_id,
    instructionAvailable: item.instruction_available,
    name: item.exercise_name,
    phaseCode: planItemPhaseCode(item),
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

export function weeklyCompletionPercentage(
  completedCount: number,
  targetCount: number,
): number {
  const target = Math.max(0, Math.floor(targetCount));
  if (target === 0) {
    return 0;
  }

  const completed = Math.max(0, Math.floor(completedCount));
  return Math.min(100, Math.round((completed / target) * 100));
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
