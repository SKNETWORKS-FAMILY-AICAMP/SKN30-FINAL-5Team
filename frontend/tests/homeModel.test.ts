import {
  applyRoutineItemOverrides,
  availabilitySlotsForRequest,
  deriveTodayRoutineViewState,
  homeCheckinDraftsEqual,
  routineItemOverrides,
  validateAvailabilitySlots,
  weeklyCompletionPercentage,
} from '../src/features/home/homeModel';
import type { WorkoutSessionDetailResponse } from '../src/api/types';

describe('Home check-in availability', () => {
  it('validates complete, ordered, non-overlapping ranges', () => {
    expect(
      validateAvailabilitySlots([
        { startTime: '09:00', endTime: '12:00' },
        { startTime: '13:00', endTime: '15:00' },
      ]),
    ).toBeNull();
    expect(
      validateAvailabilitySlots([
        { startTime: '09:00', endTime: '12:00' },
        { startTime: '12:00', endTime: '15:00' },
      ]),
    ).toBe('가능한 시간대끼리는 겹치거나 맞닿을 수 없어요.');
    expect(
      validateAvailabilitySlots([{ startTime: '15:00', endTime: '13:00' }]),
    ).toBe('종료 시간은 시작 시간보다 뒤여야 해요.');
  });

  it('uses the profile timezone when creating API datetimes', () => {
    expect(
      availabilitySlotsForRequest(
        [
          { startTime: '09:00', endTime: '12:00' },
          { startTime: '13:00', endTime: '15:00' },
        ],
        '2026-08-20',
        'Asia/Seoul',
      ),
    ).toEqual([
      {
        start_at: '2026-08-20T09:00:00+09:00',
        end_at: '2026-08-20T12:00:00+09:00',
      },
      {
        start_at: '2026-08-20T13:00:00+09:00',
        end_at: '2026-08-20T15:00:00+09:00',
      },
    ]);
  });

  it('preserves unanswered and explicitly empty availability values', () => {
    expect(
      availabilitySlotsForRequest(null, '2026-08-20', 'Asia/Seoul'),
    ).toBeNull();
    expect(availabilitySlotsForRequest([], '2026-08-20', 'Asia/Seoul')).toEqual(
      [],
    );
  });

  it('treats an end time of midnight as the next-day boundary', () => {
    expect(
      availabilitySlotsForRequest(
        [{ startTime: '22:00', endTime: '00:00' }],
        '2026-08-20',
        'Asia/Seoul',
      ),
    ).toEqual([
      {
        start_at: '2026-08-20T22:00:00+09:00',
        end_at: '2026-08-21T00:00:00+09:00',
      },
    ]);
  });
});

describe('Home weekly completion percentage', () => {
  it('rounds the server-backed completion ratio to a whole percent', () => {
    expect(weeklyCompletionPercentage(0, 3)).toBe(0);
    expect(weeklyCompletionPercentage(1, 3)).toBe(33);
    expect(weeklyCompletionPercentage(2, 3)).toBe(67);
    expect(weeklyCompletionPercentage(3, 3)).toBe(100);
  });

  it('returns a safe bounded percentage for invalid or excessive counts', () => {
    expect(weeklyCompletionPercentage(1, 0)).toBe(0);
    expect(weeklyCompletionPercentage(-1, 3)).toBe(0);
    expect(weeklyCompletionPercentage(4, 3)).toBe(100);
  });
});

describe('Home today routine presentation state', () => {
  const session = (
    statusCode: WorkoutSessionDetailResponse['status_code'],
  ): WorkoutSessionDetailResponse => ({
    session_id: 'session-1',
    local_date: '2026-09-03',
    status_code: statusCode,
    completed_item_count: 1,
    total_item_count: 2,
    requested_duration_minutes: 30,
    items: [
      {
        plan_item_id: 'item-1',
        exercise_id: 'exercise-1',
        exercise_name: '의자 스쿼트',
        status_code: 'COMPLETED',
        sets: 2,
        reps: 10,
        work_seconds_per_set: null,
        completed_at: '2026-09-03T10:05:00+09:00',
      },
      {
        plan_item_id: 'item-2',
        exercise_id: 'exercise-2',
        exercise_name: '벽 푸시업',
        status_code: 'PENDING',
        sets: 2,
        reps: 8,
        work_seconds_per_set: null,
        completed_at: null,
      },
    ],
    feedback: null,
    not_completed_reason_code: null,
    started_at: '2026-09-03T10:00:00+09:00',
    finished_at: null,
  });

  it('locks a running session while exposing its completed blocks', () => {
    const state = deriveTodayRoutineViewState({
      alternativeUsedCount: 1,
      contextExists: true,
      decisionError: false,
      decisionHasPlan: true,
      decisionIsBlocked: false,
      generationPending: false,
      session: session('IN_PROGRESS'),
    });

    expect(state.phase).toBe('SESSION_ACTIVE');
    expect(state.progress?.completedPlanItemIds).toEqual(['item-1']);
    expect(state.capabilities).toMatchObject({
      canCheckIn: false,
      canEditRoutine: false,
      canReorderRoutine: true,
      canRequestAlternative: false,
      canResume: true,
    });
  });

  it('keeps a safety-stopped routine visible but non-resumable', () => {
    const state = deriveTodayRoutineViewState({
      alternativeUsedCount: 0,
      contextExists: true,
      decisionError: false,
      decisionHasPlan: true,
      decisionIsBlocked: false,
      generationPending: false,
      session: session('STOPPED_FOR_SAFETY'),
    });

    expect(state.phase).toBe('STOPPED_SAFETY');
    expect(state.capabilities.canResume).toBe(false);
    expect(state.capabilities.canEditRoutine).toBe(false);
  });

  it('keeps check-in available after a blocked or failed decision', () => {
    const blocked = deriveTodayRoutineViewState({
      alternativeUsedCount: 2,
      contextExists: true,
      decisionError: false,
      decisionHasPlan: false,
      decisionIsBlocked: true,
      generationPending: false,
      session: null,
    });
    const failed = deriveTodayRoutineViewState({
      alternativeUsedCount: 2,
      contextExists: true,
      decisionError: true,
      decisionHasPlan: false,
      decisionIsBlocked: false,
      generationPending: false,
      session: null,
    });

    expect(blocked.capabilities.canCheckIn).toBe(true);
    expect(failed.capabilities.canCheckIn).toBe(true);
  });
});

describe('Home frontend-only edit adapters', () => {
  const draft = {
    availableSlots: null,
    fatigueLevelCode: 'MODERATE' as const,
    availableTimeMinutes: 30,
    sleepHours: '7',
    pains: {},
    locationCode: 'HOME',
    redFlagPresent: false,
  };

  it('allows unchanged check-in submission while detecting its request path', () => {
    expect(homeCheckinDraftsEqual(draft, { ...draft })).toBe(true);
    expect(
      homeCheckinDraftsEqual(draft, {
        ...draft,
        availableTimeMinutes: 40,
      }),
    ).toBe(false);
  });

  it('creates and applies only changed set and repetition overrides', () => {
    const original = [
      { id: 'item-1', name: '의자 스쿼트', sets: '2', reps: '10' },
      { id: 'item-2', name: '플랭크', sets: '2', workSeconds: 30 },
    ];
    const edited = [
      { id: 'item-1', name: '의자 스쿼트', sets: '3', reps: '12' },
      { id: 'item-2', name: '플랭크', sets: '2', workSeconds: 30 },
    ];
    const overrides = routineItemOverrides(original, edited);

    expect(overrides).toEqual([{ planItemId: 'item-1', sets: 3, reps: 12 }]);
    expect(applyRoutineItemOverrides(original, overrides)[0]).toMatchObject({
      sets: '3',
      reps: '12',
    });
  });
});
