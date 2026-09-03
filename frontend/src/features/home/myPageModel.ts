import type { MeProfile, WorkoutSessionLogSummary } from '../../api/types';
import {
  bodyAreaLabel,
  experienceLevelLabel,
  locationLabel,
  primaryGoalLabel,
} from '../../api/labels';

export type MyPageStats = {
  completedWorkoutCount: number;
  completionStreakDays: number;
  currentWeekCompletedCount: number;
};

export type MyPageProfileField =
  | 'primary_goal_code'
  | 'experience_level_code'
  | 'available_location_codes'
  | 'default_requested_duration_minutes'
  | 'desired_weekly_workout_count'
  | 'persistent_pains';

export type MyPageProfileRow = readonly [
  field: MyPageProfileField,
  label: string,
  value: string,
];

export function buildMyPageProfileRows(
  profile: MeProfile,
): readonly MyPageProfileRow[] {
  return [
    [
      'primary_goal_code',
      '운동 목표',
      primaryGoalLabel(profile.primary_goal_code),
    ],
    [
      'experience_level_code',
      '운동 경험',
      experienceLevelLabel(profile.experience_level_code),
    ],
    [
      'available_location_codes',
      '운동 장소',
      profile.available_location_codes.map(locationLabel).join(' · ') ||
        locationLabel(profile.preferred_location_code),
    ],
    [
      'default_requested_duration_minutes',
      '운동 시간',
      `${profile.default_requested_duration_minutes}분`,
    ],
    [
      'desired_weekly_workout_count',
      '주간 운동 횟수',
      `주 ${profile.desired_weekly_workout_count}회`,
    ],
    [
      'persistent_pains',
      '평소 불편한 부위',
      (
        profile.persistent_pains?.map((pain) => pain.body_area_code) ??
        profile.attention_area_codes
      )
        .map(bodyAreaLabel)
        .join(' · ') || '없음',
    ],
  ] as const;
}

export function buildMyPageStats(
  completedSessions: readonly WorkoutSessionLogSummary[],
  weekStart: string,
  today: string,
): MyPageStats {
  const completedDates = completedSessions.map((session) => session.local_date);
  return {
    completedWorkoutCount: completedSessions.length,
    completionStreakDays: completionStreak(completedDates, today),
    currentWeekCompletedCount: completedSessions.filter(
      (session) =>
        session.local_date >= weekStart && session.local_date <= today,
    ).length,
  };
}

export function completionStreak(
  completedLocalDates: readonly string[],
  today: string,
): number {
  const uniqueDates = [...new Set(completedLocalDates)].sort().reverse();
  const latest = uniqueDates[0];
  if (latest === undefined) return 0;

  const yesterday = shiftLocalDate(today, -1);
  if (latest !== today && latest !== yesterday) return 0;

  let expected = latest;
  let streak = 0;
  const dates = new Set(uniqueDates);
  while (dates.has(expected)) {
    streak += 1;
    expected = shiftLocalDate(expected, -1);
  }
  return streak;
}

export function daysTogether(startLocalDate: string, today: string): number {
  const start = localDateAsUtc(startLocalDate);
  const end = localDateAsUtc(today);
  return Math.max(
    1,
    Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1,
  );
}

function shiftLocalDate(value: string, days: number): string {
  const date = localDateAsUtc(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function localDateAsUtc(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1));
}
