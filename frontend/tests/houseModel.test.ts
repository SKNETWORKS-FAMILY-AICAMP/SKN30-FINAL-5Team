import { describe, expect, it } from '@jest/globals';

import type { WeekResponse, WorkoutSessionLogSummary } from '../src/api/types';
import {
  BANANA_REWARD,
  DAILY_GIFT_BANANAS,
  HOUSE_ACTION_COST,
  buildHouseView,
  buyItem,
  claimDailyGift,
  createHouseState,
  feedMascot,
  grantWorkoutRewards,
  parseHouseState,
  petMascot,
  registerVisit,
  restingPose,
  type HouseState,
} from '../src/features/house/houseModel';

const WEEK_START = '2026-08-17';
const TODAY = '2026-08-22';

const OPEN_WEEK: WeekResponse = {
  week_id: 'week-1',
  week_start: WEEK_START,
  week_end: '2026-08-23',
  timezone: 'Asia/Seoul',
  target_workout_count: 3,
  plan_origin_code: 'COLD_START',
  cold_start_applied: true,
  status_code: 'OPEN',
  closed_at: null,
  report_id: null,
  report_status_code: null,
};

function session(
  sessionId: string,
  localDate: string,
  statusCode: WorkoutSessionLogSummary['status_code'],
): WorkoutSessionLogSummary {
  return {
    session_id: sessionId,
    local_date: localDate,
    status_code: statusCode,
    completed_item_count: 1,
    total_item_count: 3,
    requested_duration_minutes: 30,
    training_type_code: 'STRENGTH',
    not_completed_reason_code: null,
    started_at: null,
    finished_at: null,
  };
}

function stateWith(overrides: Partial<HouseState>): HouseState {
  return { ...createHouseState(), ...overrides };
}

describe('house rewards', () => {
  it('pays for a completed workout once, however often the list is re-read', () => {
    const sessions = [session('s1', '2026-08-18', 'COMPLETED')];

    const first = grantWorkoutRewards(createHouseState(), sessions);
    expect(first.granted).toBe(BANANA_REWARD.completed);
    expect(first.state.bananas).toBe(BANANA_REWARD.completed);

    const second = grantWorkoutRewards(first.state, sessions);
    expect(second.granted).toBe(0);
    expect(second.state).toBe(first.state);
  });

  it('pays a safety stop the same as partial work, so stopping costs nothing', () => {
    const stopped = grantWorkoutRewards(createHouseState(), [
      session('s1', '2026-08-18', 'STOPPED_FOR_SAFETY'),
    ]);
    const partial = grantWorkoutRewards(createHouseState(), [
      session('s2', '2026-08-18', 'PARTIAL'),
    ]);

    expect(stopped.granted).toBe(BANANA_REWARD.partial);
    expect(partial.granted).toBe(BANANA_REWARD.partial);
  });

  it('never takes bananas away for a workout that did not happen', () => {
    const earned = stateWith({ bananas: 40 });

    const after = grantWorkoutRewards(earned, [
      session('s1', '2026-08-18', 'NOT_COMPLETED'),
      session('s2', '2026-08-19', 'PLANNED'),
      session('s3', '2026-08-20', 'IN_PROGRESS'),
    ]);

    expect(after.granted).toBe(0);
    expect(after.state.bananas).toBe(40);
  });
});

describe('daily gift and visits', () => {
  it('gives the gift once a day', () => {
    const claimed = claimDailyGift(createHouseState(), TODAY);
    expect(claimed?.granted).toBe(DAILY_GIFT_BANANAS);
    expect(
      claimDailyGift(claimed?.state ?? createHouseState(), TODAY),
    ).toBeNull();
  });

  it('records one visit per day and counts consecutive ones', () => {
    let state = createHouseState();
    for (const date of ['2026-08-20', '2026-08-21', '2026-08-22']) {
      state = registerVisit(state, date);
      state = registerVisit(state, date);
    }

    expect(state.visitedLocalDates).toEqual([
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
    ]);
    const view = buildHouseView({
      state,
      week: OPEN_WEEK,
      sessions: [],
      weekStart: WEEK_START,
      today: TODAY,
    });
    expect(view.visitStreakDays).toBe(3);
  });
});

describe('spending', () => {
  it('refuses feeding, petting and buying without enough bananas', () => {
    const broke = stateWith({ bananas: HOUSE_ACTION_COST.pet - 1 });

    expect(feedMascot(broke, TODAY)).toBeNull();
    expect(petMascot(broke, TODAY)).toBeNull();
    expect(buyItem(broke, 'yoga_mat')).toBeNull();
    expect(broke.bananas).toBe(HOUSE_ACTION_COST.pet - 1);
  });

  it('spends on an item once and keeps it', () => {
    const rich = stateWith({ bananas: 50 });

    const bought = buyItem(rich, 'yoga_mat');
    expect(bought?.bananas).toBe(30);
    expect(bought?.ownedItemIds).toEqual(['yoga_mat']);
    expect(buyItem(bought ?? rich, 'yoga_mat')).toBeNull();
  });
});

describe('house view', () => {
  it('counts only this week’s completed sessions against the target', () => {
    const view = buildHouseView({
      state: createHouseState(),
      week: OPEN_WEEK,
      sessions: [
        session('s1', '2026-08-10', 'COMPLETED'),
        session('s2', '2026-08-18', 'COMPLETED'),
        session('s3', '2026-08-19', 'PARTIAL'),
      ],
      weekStart: WEEK_START,
      today: TODAY,
    });

    expect(view.weekCompletedCount).toBe(1);
    expect(view.weekProgress).toBeCloseTo(1 / 3);
  });

  it('reports an unknown week instead of guessing a target', () => {
    const view = buildHouseView({
      state: createHouseState(),
      week: null,
      sessions: [],
      weekStart: WEEK_START,
      today: TODAY,
    });

    expect(view.weekTargetCount).toBeNull();
    expect(view.weekProgress).toBeNull();
  });

  it('lifts the pose at the target and never lowers it below greeting', () => {
    const behind = buildHouseView({
      state: createHouseState(),
      week: OPEN_WEEK,
      sessions: [],
      weekStart: WEEK_START,
      today: TODAY,
    });
    const met = buildHouseView({
      state: createHouseState(),
      week: OPEN_WEEK,
      sessions: [
        session('s1', '2026-08-18', 'COMPLETED'),
        session('s2', '2026-08-19', 'COMPLETED'),
        session('s3', '2026-08-20', 'COMPLETED'),
        session('s4', '2026-08-21', 'COMPLETED'),
      ],
      weekStart: WEEK_START,
      today: TODAY,
    });

    expect(restingPose(behind)).toBe('greeting');
    expect(restingPose(met)).toBe('happy');
    expect(met.weekProgress).toBe(1);
  });
});

describe('stored state', () => {
  it('reads back a state it wrote', () => {
    const stored = stateWith({ bananas: 12, ownedItemIds: ['plant'] });
    expect(parseHouseState(JSON.parse(JSON.stringify(stored)))).toEqual(stored);
  });

  it('rejects an unknown version and unknown items rather than trusting them', () => {
    expect(parseHouseState({ version: 99, bananas: 500 })).toBeNull();
    expect(parseHouseState('nonsense')).toBeNull();

    const cleaned = parseHouseState({
      ...createHouseState(),
      bananas: -40,
      ownedItemIds: ['plant', 'spaceship'],
    });
    expect(cleaned?.bananas).toBe(0);
    expect(cleaned?.ownedItemIds).toEqual(['plant']);
  });
});
