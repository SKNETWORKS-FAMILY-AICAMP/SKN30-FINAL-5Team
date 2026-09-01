/**
 * Presentation model for the home screen.
 *
 * The home screen is the app's entry point: it shows today's state, the
 * server's final routine, and the way into the workout. Nothing here decides
 * what today's workout should be — these helpers only turn stored server values
 * and stable machine codes into the strings and rows the design shows.
 */

import {
  bodyFocusLabel,
  formatMinutes,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  DailyContextResponse,
  DiscomfortSeverityCode,
  FatigueLevelCode,
  RoutineDay,
  WorkoutPlan,
} from '../../api/types';
import { orderedWorkoutPlanItems } from '../../api/workoutPlan';

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

/** One row of the routine card. `prescription` is absent for timed blocks. */
export type HomeRoutineItem = {
  id: string;
  name: string;
  prescription?: string;
};

/**
 * The check-in the sheet collects, in the contract's own fields.
 *
 * `sleepMinutes` stays null unless the user typed it: the server does not infer
 * sleep, and neither may the client.
 */
export type HomeCheckinDraft = {
  fatigueLevelCode: FatigueLevelCode;
  requestedDurationMinutes: number;
  sleepHours: string;
  discomforts: Record<string, DiscomfortSeverityCode>;
  adverseReactionCodes: string[];
};

export const HOME_DURATION_CHOICES = [20, 30, 40, 50] as const;

const WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'] as const;

/** Monday-first labels, matching the design's week strip. */
export const HOME_WEEK_DAY_LABELS = [
  '월',
  '화',
  '수',
  '목',
  '금',
  '토',
  '일',
] as const;

/** `YYYY-MM-DD` parsed in the device's own zone, not UTC. */
export function parseLocalDate(localDate: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  if (!match) {
    return null;
  }
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

/** `2026.08.11 (화)`, the header format in the design. */
export function formatHomeDate(localDate: string): string {
  const date = parseLocalDate(localDate);
  if (date === null) {
    return localDate;
  }
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}.${month}.${day} (${WEEKDAY_LABELS[date.getDay()]})`;
}

/** `8.11 ~ 8.17`, the week range on the progress card. */
export function formatWeekRange(weekStart: string): string | null {
  const start = parseLocalDate(weekStart);
  if (start === null) {
    return null;
  }
  const end = new Date(
    start.getFullYear(),
    start.getMonth(),
    start.getDate() + 6,
  );
  return `${start.getMonth() + 1}.${start.getDate()} ~ ${end.getMonth() + 1}.${end.getDate()}`;
}

export function emptyCheckinDraft(
  requestedDurationMinutes: number,
): HomeCheckinDraft {
  return {
    fatigueLevelCode: 'MODERATE',
    requestedDurationMinutes,
    sleepHours: '',
    discomforts: {},
    adverseReactionCodes: [],
  };
}

/** Re-opening the sheet after a check-in shows what was stored, not defaults. */
export function checkinDraftFromContext(
  context: DailyContextResponse,
): HomeCheckinDraft {
  return {
    fatigueLevelCode: context.fatigue_level_code,
    requestedDurationMinutes: context.requested_duration_minutes,
    sleepHours:
      context.sleep_minutes === null || context.sleep_minutes === undefined
        ? ''
        : String(Math.round((context.sleep_minutes / 60) * 10) / 10),
    discomforts: Object.fromEntries(
      context.discomforts.map((entry) => [
        entry.body_area_code,
        entry.severity_code,
      ]),
    ),
    adverseReactionCodes: [...context.adverse_reaction_codes],
  };
}

/**
 * Hours as typed by the user, in whole minutes. Returns `undefined` for input
 * the client will not send, so an unparsable value stays unset rather than
 * being guessed at.
 */
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

function prescriptionFor(
  sets: number,
  reps: number | null,
  workSeconds: number | null,
): string | undefined {
  if (reps !== null) {
    return `${sets}세트 × ${reps}회`;
  }
  if (workSeconds !== null && workSeconds > 0) {
    return `${sets}세트 × ${workSeconds}초`;
  }
  return undefined;
}

export function routineItemsFromPlan(plan: WorkoutPlan): HomeRoutineItem[] {
  return orderedWorkoutPlanItems(plan.items).map((item) => ({
    id: item.plan_item_id,
    name: item.exercise_name,
    prescription: prescriptionFor(item.sets, item.reps, item.work_seconds),
  }));
}

export function routineItemsFromDay(day: RoutineDay): HomeRoutineItem[] {
  return [...day.items]
    .sort((left, right) => left.sequence - right.sequence)
    .map((item) => ({
      id: item.id,
      name: item.exercise_name,
      prescription: prescriptionFor(
        item.sets,
        item.reps,
        item.work_seconds_per_set,
      ),
    }));
}

/** `상체 근력 루틴` style title from the plan's own codes. */
export function planTitle(plan: WorkoutPlan): string {
  const focus = plan.body_focus_code
    ? `${bodyFocusLabel(plan.body_focus_code)} `
    : '';
  return `${focus}${trainingTypeLabel(plan.training_type_code)} 루틴`;
}

export function planSummary(plan: WorkoutPlan): string {
  return `${trainingTypeLabel(plan.training_type_code)} · 희망 운동 시간 ${plan.requested_duration_minutes}분 · 예상 ${formatMinutes(plan.estimated_duration_seconds)}`;
}
