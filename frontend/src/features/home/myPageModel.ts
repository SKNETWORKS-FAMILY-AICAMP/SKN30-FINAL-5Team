import type { MeProfile, WorkoutSessionLogSummary } from '../../api/types';
import {
  bodyAreaLabel,
  equipmentLabel,
  experienceLevelLabel,
  locationLabel,
  primaryGoalLabel,
  trainingTypeLabel,
} from '../../api/labels';

export type MyPageStats = {
  completedWorkoutCount: number;
  completionStreakDays: number;
  currentWeekCompletedCount: number;
};

export type MyPageProfileField =
  | 'date_of_birth'
  | 'timezone'
  | 'primary_goal_code'
  | 'experience_level_code'
  | 'preferred_exercise_type_codes'
  | 'available_location_codes'
  | 'equipment_codes'
  | 'default_requested_duration_minutes'
  | 'desired_weekly_workout_count'
  | 'attention_area_codes';

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
      'date_of_birth',
      '나이',
      profile.age === null ? '미입력' : `만 ${profile.age}세`,
    ],
    ['timezone', '시간대', profile.timezone],
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
      'preferred_exercise_type_codes',
      '선호 운동',
      profile.preferred_exercise_type_codes
        .map(trainingTypeLabel)
        .join(' · ') || '지정 안 함',
    ],
    [
      'available_location_codes',
      '운동 장소',
      profile.available_location_codes.map(locationLabel).join(' · ') ||
        locationLabel(profile.preferred_location_code),
    ],
    [
      'equipment_codes',
      '장비',
      profile.equipment_codes.map(equipmentLabel).join(' · ') || '없음',
    ],
    [
      'default_requested_duration_minutes',
      '희망 시간',
      `${profile.default_requested_duration_minutes}분`,
    ],
    [
      'desired_weekly_workout_count',
      '주간 목표',
      `${profile.desired_weekly_workout_count}회`,
    ],
    [
      'attention_area_codes',
      '주의 부위',
      profile.attention_area_codes.map(bodyAreaLabel).join(' · ') || '없음',
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
