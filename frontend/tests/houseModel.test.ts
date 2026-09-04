import { describe, expect, it } from '@jest/globals';

import type { WeekResponse, WorkoutSessionLogSummary } from '../src/api/types';
import {
  BANANA_REWARD,
  DEFAULT_HOUSE_BACKGROUND_ID,
  DAILY_GIFT_BANANAS,
  HOUSE_ACTION_COST,
  HOUSE_DAILY_QUESTS,
  INTIMACY_DAILY_EARN_LIMIT,
  INTIMACY_POINTS_PER_LEVEL,
  buildHouseView,
  buyItem,
  createHouseState,
  feedMascot,
  grantWorkoutRewards,
  parseHouseState,
  petMascot,
  placeHouseItem,
  recordGamePlay,
  registerVisit,
  restingPose,
  selectBackground,
  settleHouseDay,
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

describe('daily quests and visits', () => {
  it('pays the visit quest once a day, at the amount the old gift paid', () => {
    const visited = registerVisit(createHouseState(), TODAY);

    const first = settleHouseDay(visited, {
      today: TODAY,
      workoutCompletedToday: false,
    });
    expect(first.granted).toBe(DAILY_GIFT_BANANAS);

    const second = settleHouseDay(first.state, {
      today: TODAY,
      workoutCompletedToday: false,
    });
    expect(second.granted).toBe(0);
    expect(second.state.bananas).toBe(DAILY_GIFT_BANANAS);
  });

  it('pays the workout quest only once the server says a session completed', () => {
    const visited = registerVisit(createHouseState(), TODAY);
    const workoutQuest = HOUSE_DAILY_QUESTS.find(
      (quest) => quest.id === 'workout',
    );

    const resting = settleHouseDay(visited, {
      today: TODAY,
      workoutCompletedToday: false,
    });
    expect(resting.state.paidQuestIds).not.toContain('workout');
    expect(resting.state.bananas).toBe(DAILY_GIFT_BANANAS);

    const trained = settleHouseDay(resting.state, {
      today: TODAY,
      workoutCompletedToday: true,
    });
    expect(trained.granted).toBe(workoutQuest?.reward);
    // The workout is the third source of intimacy, and it pays once.
    expect(trained.state.intimacyPoints).toBe(1);
    expect(
      settleHouseDay(trained.state, {
        today: TODAY,
        workoutCompletedToday: true,
      }).granted,
    ).toBe(0);
  });

  it('never takes a quest reward back when a day ends unfinished', () => {
    const yesterday = settleHouseDay(registerVisit(createHouseState(), TODAY), {
      today: TODAY,
      workoutCompletedToday: true,
    });

    const tomorrow = settleHouseDay(yesterday.state, {
      today: '2026-08-23',
      workoutCompletedToday: false,
    });

    expect(tomorrow.state.bananas).toBe(yesterday.state.bananas);
    expect(tomorrow.state.intimacyPoints).toBe(yesterday.state.intimacyPoints);
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

describe('intimacy', () => {
  it('lets the mascot be petted for free, as often as the user likes', () => {
    let state = stateWith({ bananas: 0 });

    for (let index = 0; index < INTIMACY_DAILY_EARN_LIMIT + 3; index += 1) {
      state = petMascot(state, TODAY);
    }

    expect(state.bananas).toBe(0);
    expect(state.pettedCount).toBe(INTIMACY_DAILY_EARN_LIMIT + 3);
    // The touch always lands; only the intimacy it pays is capped.
    expect(state.intimacyPoints).toBe(INTIMACY_DAILY_EARN_LIMIT);
  });

  it('starts the daily allowance over without touching what was earned', () => {
    let state = stateWith({ bananas: 0 });
    for (let index = 0; index < INTIMACY_DAILY_EARN_LIMIT; index += 1) {
      state = petMascot(state, TODAY);
    }

    const next = petMascot(state, '2026-08-23');

    expect(next.intimacyPoints).toBe(INTIMACY_DAILY_EARN_LIMIT + 1);
    expect(next.pettedCount).toBe(1);
  });

  it('reads the level and the remaining allowance onto the view', () => {
    const state = stateWith({
      intimacyPoints: INTIMACY_POINTS_PER_LEVEL * 2 + 3,
      intimacyLocalDate: TODAY,
      intimacyEarnedToday: 2,
    });

    const view = buildHouseView({
      state,
      week: OPEN_WEEK,
      sessions: [],
      weekStart: WEEK_START,
      today: TODAY,
    });

    expect(view.intimacyLevel).toBe(3);
    expect(view.intimacyRemainingToday).toBe(INTIMACY_DAILY_EARN_LIMIT - 2);
  });
});

describe('the banana catch game', () => {
  it('opens once a day and reopens when the day turns', () => {
    const played = recordGamePlay(createHouseState(), TODAY);

    const todayView = buildHouseView({
      state: played,
      week: OPEN_WEEK,
      sessions: [],
      weekStart: WEEK_START,
      today: TODAY,
    });
    expect(todayView.gamePlayedToday).toBe(true);
    expect(todayView.canPlayGame).toBe(false);

    const tomorrowView = buildHouseView({
      state: played,
      week: OPEN_WEEK,
      sessions: [],
      weekStart: WEEK_START,
      today: '2026-08-23',
    });
    expect(tomorrowView.canPlayGame).toBe(true);
  });
});

describe('spending', () => {
  it('refuses feeding and buying without enough bananas', () => {
    const broke = stateWith({ bananas: HOUSE_ACTION_COST.feed - 1 });

    expect(feedMascot(broke, TODAY)).toBeNull();
    expect(buyItem(broke, 'yoga_mat')).toBeNull();
    expect(broke.bananas).toBe(HOUSE_ACTION_COST.feed - 1);
  });

  it('spends on an item once and keeps it', () => {
    const rich = stateWith({ bananas: 50 });

    const bought = buyItem(rich, 'yoga_mat');
    expect(bought?.bananas).toBe(30);
    expect(bought?.ownedItemIds).toEqual(['yoga_mat']);
    expect(bought?.itemPlacements.yoga_mat).toEqual({ x: 0.24, y: 0.46 });
    expect(buyItem(bought ?? rich, 'yoga_mat')).toBeNull();
  });

  it('stores normalized positions only for purchased items', () => {
    const rich = stateWith({ bananas: 50 });
    const bought = buyItem(rich, 'yoga_mat') ?? rich;

    expect(placeHouseItem(rich, 'yoga_mat', { x: 0.4, y: 0.5 })).toBeNull();
    const placed = placeHouseItem(bought, 'yoga_mat', { x: 1.4, y: -0.2 });

    expect(placed?.itemPlacements.yoga_mat).toEqual({ x: 1, y: 0 });
  });
});

describe('background selection', () => {
  it('changes the background without spending bananas', () => {
    const state = stateWith({ bananas: 12 });

    const selected = selectBackground(state, 'dinner_camp');

    expect(selected.selectedBackgroundId).toBe('dinner_camp');
    expect(selected.bananas).toBe(12);
    expect(selectBackground(selected, 'dinner_camp')).toBe(selected);
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

  it('defaults legacy or unknown background values without resetting the house', () => {
    const legacy = { ...createHouseState() } as Record<string, unknown>;
    delete legacy.selectedBackgroundId;

    expect(parseHouseState(legacy)?.selectedBackgroundId).toBe(
      DEFAULT_HOUSE_BACKGROUND_ID,
    );
    expect(
      parseHouseState({
        ...createHouseState(),
        selectedBackgroundId: 'unknown-room',
      })?.selectedBackgroundId,
    ).toBe(DEFAULT_HOUSE_BACKGROUND_ID);
  });

  it('keeps valid stored positions and discards malformed placement data', () => {
    const parsed = parseHouseState({
      ...createHouseState(),
      ownedItemIds: ['yoga_mat', 'plant'],
      itemPlacements: {
        yoga_mat: { x: 0.35, y: 0.65 },
        plant: { x: 'left', y: 0.4 },
        spaceship: { x: 0.1, y: 0.2 },
      },
    });

    expect(parsed?.itemPlacements).toEqual({
      yoga_mat: { x: 0.35, y: 0.65 },
    });
  });
});
