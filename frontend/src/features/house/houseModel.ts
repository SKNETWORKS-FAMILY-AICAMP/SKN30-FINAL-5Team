/**
 * 끼끼의 집 — the mascot home's own state and the rules around it.
 *
 * Nothing here is a safety, planning or completion decision, so it lives
 * entirely on the client: the server has no banana, decoration or visit
 * concept yet. Keeping the rules in one pure module means the screen only
 * renders a value it was handed, and the same rules can move behind an API
 * later without the view changing.
 *
 * Two product invariants shape every rule below.
 *
 *   - A missed or unfinished workout is a learning signal, not a penalty.
 *     No rule here may take bananas away, expire them, break a reward already
 *     earned, or describe a shortfall as a loss.
 *   - The mascot never expresses disappointment, so no pose exists for it.
 *
 * Official completion still comes from the server's session status. Bananas
 * are a house reward read off that status; they never define it.
 */

import type { WeekResponse, WorkoutSessionLogSummary } from '../../api/types';
import { completionStreak } from '../home/myPageModel';

export const HOUSE_STATE_VERSION = 1;

/** Bananas granted per session, by the status the server recorded. */
export const BANANA_REWARD = {
  /** A full workout. */
  completed: 30,
  /**
   * Partial work and a safety stop pay the same. Stopping because something
   * hurt must never cost the user anything, so it is not a lesser outcome
   * here.
   */
  partial: 15,
} as const;

/** The one gift a day the house offers just for coming back. */
export const DAILY_GIFT_BANANAS = 15;

export const HOUSE_ACTION_COST = {
  feed: 10,
  pet: 5,
} as const;

export type HousePose = 'greeting' | 'happy' | 'eating' | 'petted' | 'resting';

export type HouseItemId =
  | 'yoga_mat'
  | 'dumbbell'
  | 'plant'
  | 'lamp'
  | 'cushion'
  | 'star_frame'
  | 'window';

export type HouseItem = {
  id: HouseItemId;
  label: string;
  cost: number;
};

/** Purchasable decorations, cheapest first so the list reads as a ladder. */
export const HOUSE_ITEMS: readonly HouseItem[] = [
  { id: 'yoga_mat', label: '요가 매트', cost: 20 },
  { id: 'dumbbell', label: '아령', cost: 20 },
  { id: 'plant', label: '화분', cost: 25 },
  { id: 'cushion', label: '쿠션', cost: 25 },
  { id: 'lamp', label: '스탠드', cost: 30 },
  { id: 'star_frame', label: '별 액자', cost: 35 },
  { id: 'window', label: '창문 커튼', cost: 40 },
] as const;

/** The cheapest decoration, shown on the 집 꾸미기 action tile. */
export const CHEAPEST_ITEM_COST = HOUSE_ITEMS.reduce(
  (lowest, item) => Math.min(lowest, item.cost),
  Number.POSITIVE_INFINITY,
);

/**
 * The persisted house state.
 *
 * Only counters, item ids and local dates. No identifier, no health record and
 * nothing derived from a check-in ever belongs in here.
 */
export type HouseState = {
  version: number;
  bananas: number;
  ownedItemIds: HouseItemId[];
  /** Sessions already paid for, so a reload cannot grant the same one twice. */
  rewardedSessionIds: string[];
  claimedGiftLocalDate: string | null;
  fedLocalDate: string | null;
  pettedLocalDate: string | null;
  visitedLocalDates: string[];
};

/** Kept short so the stored payload cannot grow without bound. */
const MAX_REMEMBERED_SESSIONS = 60;
const MAX_REMEMBERED_VISITS = 60;

export function createHouseState(): HouseState {
  return {
    version: HOUSE_STATE_VERSION,
    bananas: 0,
    ownedItemIds: [],
    rewardedSessionIds: [],
    claimedGiftLocalDate: null,
    fedLocalDate: null,
    pettedLocalDate: null,
    visitedLocalDates: [],
  };
}

/**
 * Reads a stored payload back.
 *
 * Anything unrecognised returns `null` rather than a partly-trusted object:
 * the caller then starts fresh, which is the safe direction for a value that
 * only ever grows.
 */
export function parseHouseState(raw: unknown): HouseState | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const value = raw as Record<string, unknown>;
  if (value.version !== HOUSE_STATE_VERSION) return null;
  if (typeof value.bananas !== 'number' || !Number.isFinite(value.bananas)) {
    return null;
  }

  const knownItemIds = new Set<string>(HOUSE_ITEMS.map((item) => item.id));
  return {
    version: HOUSE_STATE_VERSION,
    bananas: Math.max(0, Math.floor(value.bananas)),
    ownedItemIds: stringList(value.ownedItemIds).filter(
      (id): id is HouseItemId => knownItemIds.has(id),
    ),
    rewardedSessionIds: stringList(value.rewardedSessionIds).slice(
      -MAX_REMEMBERED_SESSIONS,
    ),
    claimedGiftLocalDate: optionalString(value.claimedGiftLocalDate),
    fedLocalDate: optionalString(value.fedLocalDate),
    pettedLocalDate: optionalString(value.pettedLocalDate),
    visitedLocalDates: stringList(value.visitedLocalDates).slice(
      -MAX_REMEMBERED_VISITS,
    ),
  };
}

/** Records that the user opened the house today. Repeat visits are a no-op. */
export function registerVisit(state: HouseState, today: string): HouseState {
  if (state.visitedLocalDates.includes(today)) return state;
  return {
    ...state,
    visitedLocalDates: [...state.visitedLocalDates, today].slice(
      -MAX_REMEMBERED_VISITS,
    ),
  };
}

/**
 * Pays out bananas for sessions the house has not paid for yet.
 *
 * Idempotent by session id, so re-reading the same list — a reload, a pull to
 * refresh, a second screen — never grants twice.
 */
export function grantWorkoutRewards(
  state: HouseState,
  sessions: readonly WorkoutSessionLogSummary[],
): { state: HouseState; granted: number } {
  const rewarded = new Set(state.rewardedSessionIds);
  let granted = 0;
  const newlyRewarded: string[] = [];

  for (const session of sessions) {
    if (rewarded.has(session.session_id)) continue;
    const amount = sessionReward(session.status_code);
    if (amount === 0) continue;
    granted += amount;
    newlyRewarded.push(session.session_id);
  }

  if (granted === 0) return { state, granted: 0 };

  return {
    state: {
      ...state,
      bananas: state.bananas + granted,
      rewardedSessionIds: [...state.rewardedSessionIds, ...newlyRewarded].slice(
        -MAX_REMEMBERED_SESSIONS,
      ),
    },
    granted,
  };
}

function sessionReward(statusCode: WorkoutSessionLogSummary['status_code']) {
  if (statusCode === 'COMPLETED') return BANANA_REWARD.completed;
  if (statusCode === 'PARTIAL' || statusCode === 'STOPPED_FOR_SAFETY') {
    return BANANA_REWARD.partial;
  }
  // PLANNED, IN_PROGRESS and NOT_COMPLETED simply pay nothing. Not finishing
  // is never charged for.
  return 0;
}

/** `null` when today's gift is already claimed. */
export function claimDailyGift(
  state: HouseState,
  today: string,
): { state: HouseState; granted: number } | null {
  if (state.claimedGiftLocalDate === today) return null;
  return {
    state: {
      ...state,
      bananas: state.bananas + DAILY_GIFT_BANANAS,
      claimedGiftLocalDate: today,
    },
    granted: DAILY_GIFT_BANANAS,
  };
}

/** `null` when there are not enough bananas. */
export function feedMascot(
  state: HouseState,
  today: string,
): HouseState | null {
  if (state.bananas < HOUSE_ACTION_COST.feed) return null;
  return {
    ...state,
    bananas: state.bananas - HOUSE_ACTION_COST.feed,
    fedLocalDate: today,
  };
}

/** `null` when there are not enough bananas. */
export function petMascot(state: HouseState, today: string): HouseState | null {
  if (state.bananas < HOUSE_ACTION_COST.pet) return null;
  return {
    ...state,
    bananas: state.bananas - HOUSE_ACTION_COST.pet,
    pettedLocalDate: today,
  };
}

/** `null` when the item is already owned or unaffordable. */
export function buyItem(
  state: HouseState,
  itemId: HouseItemId,
): HouseState | null {
  if (state.ownedItemIds.includes(itemId)) return null;
  const item = HOUSE_ITEMS.find((candidate) => candidate.id === itemId);
  if (item === undefined) return null;
  if (state.bananas < item.cost) return null;
  return {
    ...state,
    bananas: state.bananas - item.cost,
    ownedItemIds: [...state.ownedItemIds, itemId],
  };
}

export type HouseView = {
  bananas: number;
  /** `null` when the week could not be read; the screen says so rather than guessing. */
  weekTargetCount: number | null;
  weekCompletedCount: number;
  /** 0–1, clamped. `null` when there is no target to measure against. */
  weekProgress: number | null;
  weekClosed: boolean;
  reportReady: boolean;
  visitStreakDays: number;
  workoutStreakDays: number;
  giftAvailable: boolean;
  fedToday: boolean;
  pettedToday: boolean;
  ownedItems: readonly HouseItem[];
  lockedItems: readonly HouseItem[];
  canFeed: boolean;
  canPet: boolean;
  canDecorate: boolean;
};

export function buildHouseView({
  state,
  week,
  sessions,
  weekStart,
  today,
}: {
  state: HouseState;
  week: WeekResponse | null;
  sessions: readonly WorkoutSessionLogSummary[];
  weekStart: string;
  today: string;
}): HouseView {
  const completedDates = sessions
    .filter((session) => session.status_code === 'COMPLETED')
    .map((session) => session.local_date);
  const weekCompletedCount = completedDates.filter(
    (date) => date >= weekStart && date <= today,
  ).length;
  const target = week === null ? null : week.target_workout_count;
  const owned = new Set<string>(state.ownedItemIds);
  const lockedItems = HOUSE_ITEMS.filter((item) => !owned.has(item.id));

  return {
    bananas: state.bananas,
    weekTargetCount: target,
    weekCompletedCount,
    weekProgress:
      target === null || target <= 0
        ? null
        : Math.min(1, weekCompletedCount / target),
    weekClosed: week !== null && week.status_code === 'CLOSED',
    reportReady: week !== null && week.report_id !== null,
    visitStreakDays: completionStreak(state.visitedLocalDates, today),
    workoutStreakDays: completionStreak(completedDates, today),
    giftAvailable: state.claimedGiftLocalDate !== today,
    fedToday: state.fedLocalDate === today,
    pettedToday: state.pettedLocalDate === today,
    ownedItems: HOUSE_ITEMS.filter((item) => owned.has(item.id)),
    lockedItems,
    canFeed: state.bananas >= HOUSE_ACTION_COST.feed,
    canPet: state.bananas >= HOUSE_ACTION_COST.pet,
    canDecorate: lockedItems.some((item) => state.bananas >= item.cost),
  };
}

/**
 * The pose the mascot settles back into.
 *
 * Reaching the weekly target lifts it; falling short does not lower it. There
 * is deliberately no pose below `greeting`.
 */
export function restingPose(view: HouseView): HousePose {
  if (view.weekProgress !== null && view.weekProgress >= 1) return 'happy';
  return 'greeting';
}

/** House copy. Level whatever the week looks like — never a nudge to train. */
export function houseCaption(view: HouseView): string {
  if (view.weekTargetCount === null) {
    return '이번 주 정보를 불러오지 못했어요. 집은 그대로 있어요.';
  }
  if (view.weekProgress !== null && view.weekProgress >= 1) {
    return '이번 주 목표를 채웠어요. 끼끼가 신났어요.';
  }
  if (view.weekCompletedCount > 0) {
    return `이번 주 ${view.weekCompletedCount}번 함께했어요.`;
  }
  return '오늘은 그냥 놀러 와도 좋아요.';
}

/**
 * What the mascot says in its speech bubble.
 *
 * Reactions come first, then hunger, then the week. Nothing here asks the user
 * to train, check in, or come back — the bubble is the mascot talking about
 * itself, never a nudge wearing a costume.
 */
export function houseSpeech(view: HouseView, pose: HousePose): string {
  if (pose === 'eating') return '냠냠… 고마워요!';
  if (pose === 'petted') return '헤헤, 기분 좋아요.';
  if (!view.fedToday && view.canFeed) return '밥 주세요!!!';
  if (view.giftAvailable) return '오늘 선물이 와 있어요.';
  return houseCaption(view);
}

/**
 * The Korean object particle for a noun: 을 after a final consonant, 를 after
 * a vowel. Item names are data, so the sentence around them cannot hard-code
 * one or the other.
 */
export function objectParticle(word: string): '을' | '를' {
  const last = word.trim().slice(-1);
  const code = last.charCodeAt(0);
  if (Number.isNaN(code) || code < 0xac00 || code > 0xd7a3) return '를';
  return (code - 0xac00) % 28 === 0 ? '를' : '을';
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === 'string');
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}
