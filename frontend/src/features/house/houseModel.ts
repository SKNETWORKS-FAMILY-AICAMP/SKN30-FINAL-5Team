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

export const HOUSE_STATE_VERSION = 2;

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

/**
 * What coming back pays.
 *
 * This was a standalone `오늘의 선물` chip. It is now the visit quest, paid
 * the moment the house opens, and the amount is unchanged so nobody receives
 * less for the same visit than they did before.
 */
export const DAILY_GIFT_BANANAS = 15;

/**
 * Petting is free.
 *
 * Charging for it made the one interaction the house is built around
 * something the user could run out of, so only feeding still costs.
 */
export const HOUSE_ACTION_COST = {
  feed: 10,
} as const;

/** Hearts on the house chip, and the highest level those hearts can show. */
export const INTIMACY_MAX_LEVEL = 5;

/** Interactions that raise intimacy within one local day. */
export const INTIMACY_DAILY_EARN_LIMIT = 5;

/** Points between one level and the next. */
export const INTIMACY_POINTS_PER_LEVEL = 10;

/** The banana catch game opens this many times a local day. */
export const HOUSE_GAME_DAILY_PLAYS = 1;

export type HouseQuestId = 'visit' | 'pet' | 'workout';

export type HouseQuest = {
  id: HouseQuestId;
  label: string;
  /** Bananas paid once, the first time the target is met on a given day. */
  reward: number;
  target: number;
};

/**
 * The daily quests.
 *
 * Falling short pays nothing and costs nothing. No rule here takes a banana
 * back, and an unmet quest is never described as a loss — a quiet `0 / 1` is
 * the whole of it.
 */
export const HOUSE_DAILY_QUESTS: readonly HouseQuest[] = [
  {
    id: 'visit',
    label: '오늘 접속하기',
    reward: DAILY_GIFT_BANANAS,
    target: 1,
  },
  {
    id: 'pet',
    label: '끼끼 쓰다듬기',
    reward: 5,
    target: INTIMACY_DAILY_EARN_LIMIT,
  },
  { id: 'workout', label: '오늘 운동 완료하기', reward: 10, target: 1 },
] as const;

export type HousePose = 'greeting' | 'happy' | 'eating' | 'petted' | 'resting';

export const HOUSE_BACKGROUND_IDS = [
  'morning_camp',
  'dinner_camp',
  'indoor_treehouse',
  'snowing_onsen',
] as const;

export type HouseBackgroundId = (typeof HOUSE_BACKGROUND_IDS)[number];

export const DEFAULT_HOUSE_BACKGROUND_ID: HouseBackgroundId = 'morning_camp';

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

/**
 * A decoration's top-left position inside the full-screen house canvas.
 * Normalized coordinates keep the layout stable across phone and web sizes
 * and are ready to move behind a future persistence adapter unchanged.
 */
export type HouseItemPlacement = {
  x: number;
  y: number;
};

export type HouseItemPlacements = Partial<
  Record<HouseItemId, HouseItemPlacement>
>;

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

const DEFAULT_ITEM_PLACEMENTS: Record<HouseItemId, HouseItemPlacement> = {
  yoga_mat: { x: 0.24, y: 0.57 },
  dumbbell: { x: 0.62, y: 0.57 },
  plant: { x: 0.1, y: 0.46 },
  cushion: { x: 0.72, y: 0.47 },
  lamp: { x: 0.82, y: 0.34 },
  star_frame: { x: 0.18, y: 0.25 },
  window: { x: 0.66, y: 0.2 },
};

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
  selectedBackgroundId: HouseBackgroundId;
  ownedItemIds: HouseItemId[];
  itemPlacements: HouseItemPlacements;
  /** Sessions already paid for, so a reload cannot grant the same one twice. */
  rewardedSessionIds: string[];
  fedLocalDate: string | null;
  /** The day `pettedCount` belongs to. */
  pettedLocalDate: string | null;
  pettedCount: number;
  /** Earned intimacy. It only ever grows; nothing here takes a point back. */
  intimacyPoints: number;
  /** The day `intimacyEarnedToday` belongs to. */
  intimacyLocalDate: string | null;
  intimacyEarnedToday: number;
  /** The day the banana catch game was last opened. */
  playedGameLocalDate: string | null;
  /** The day `paidQuestIds` belongs to. */
  questLocalDate: string | null;
  paidQuestIds: HouseQuestId[];
  visitedLocalDates: string[];
};

/** Kept short so the stored payload cannot grow without bound. */
const MAX_REMEMBERED_SESSIONS = 60;
const MAX_REMEMBERED_VISITS = 60;

export function createHouseState(): HouseState {
  return {
    version: HOUSE_STATE_VERSION,
    bananas: 0,
    selectedBackgroundId: DEFAULT_HOUSE_BACKGROUND_ID,
    ownedItemIds: [],
    itemPlacements: {},
    rewardedSessionIds: [],
    fedLocalDate: null,
    pettedLocalDate: null,
    pettedCount: 0,
    intimacyPoints: 0,
    intimacyLocalDate: null,
    intimacyEarnedToday: 0,
    playedGameLocalDate: null,
    questLocalDate: null,
    paidQuestIds: [],
    visitedLocalDates: [],
  };
}

/** Stored payloads this build still knows how to read. */
const READABLE_HOUSE_STATE_VERSIONS: readonly number[] = [1, 2];

/**
 * Reads a stored payload back.
 *
 * Anything unrecognised returns `null` rather than a partly-trusted object:
 * the caller then starts fresh, which is the safe direction for a value that
 * only ever grows.
 *
 * A version 1 payload is migrated rather than discarded. Dropping it would
 * reset bananas someone already earned, and no rule here may take an earned
 * reward back. The fields added in version 2 simply start at zero, so the one
 * visible effect is that a user who had already claimed the old `오늘의 선물`
 * today is paid the visit quest once more — over-paying by a day is the safe
 * direction; under-paying is not.
 */
export function parseHouseState(raw: unknown): HouseState | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const value = raw as Record<string, unknown>;
  if (
    typeof value.version !== 'number' ||
    !READABLE_HOUSE_STATE_VERSIONS.includes(value.version)
  ) {
    return null;
  }
  if (typeof value.bananas !== 'number' || !Number.isFinite(value.bananas)) {
    return null;
  }

  const knownItemIds = new Set<string>(HOUSE_ITEMS.map((item) => item.id));
  const selectedBackgroundId = HOUSE_BACKGROUND_IDS.includes(
    value.selectedBackgroundId as HouseBackgroundId,
  )
    ? (value.selectedBackgroundId as HouseBackgroundId)
    : DEFAULT_HOUSE_BACKGROUND_ID;
  const itemPlacements = parseItemPlacements(
    value.itemPlacements,
    knownItemIds,
  );
  return {
    version: HOUSE_STATE_VERSION,
    bananas: Math.max(0, Math.floor(value.bananas)),
    selectedBackgroundId,
    ownedItemIds: stringList(value.ownedItemIds).filter(
      (id): id is HouseItemId => knownItemIds.has(id),
    ),
    itemPlacements,
    rewardedSessionIds: stringList(value.rewardedSessionIds).slice(
      -MAX_REMEMBERED_SESSIONS,
    ),
    fedLocalDate: optionalString(value.fedLocalDate),
    pettedLocalDate: optionalString(value.pettedLocalDate),
    pettedCount: counter(value.pettedCount),
    intimacyPoints: counter(value.intimacyPoints),
    intimacyLocalDate: optionalString(value.intimacyLocalDate),
    intimacyEarnedToday: counter(value.intimacyEarnedToday),
    playedGameLocalDate: optionalString(value.playedGameLocalDate),
    questLocalDate: optionalString(value.questLocalDate),
    paidQuestIds: stringList(value.paidQuestIds).filter(
      (id): id is HouseQuestId =>
        HOUSE_DAILY_QUESTS.some((quest) => quest.id === id),
    ),
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

/** Today's tally of an interaction counter, reset when the local day turns. */
function todaysCount(
  countLocalDate: string | null,
  count: number,
  today: string,
): number {
  return countLocalDate === today ? count : 0;
}

/**
 * Adds one intimacy point, up to the daily limit.
 *
 * Over the limit the interaction still happens — the mascot still reacts and
 * the user is never told to stop — it simply stops paying intimacy. Nothing
 * here can lower `intimacyPoints`.
 */
function grantIntimacy(state: HouseState, today: string): HouseState {
  const earned = todaysCount(
    state.intimacyLocalDate,
    state.intimacyEarnedToday,
    today,
  );
  if (earned >= INTIMACY_DAILY_EARN_LIMIT) {
    return { ...state, intimacyLocalDate: today, intimacyEarnedToday: earned };
  }
  return {
    ...state,
    intimacyPoints: state.intimacyPoints + 1,
    intimacyLocalDate: today,
    intimacyEarnedToday: earned + 1,
  };
}

/** The level those five hearts show, from 1 up to `INTIMACY_MAX_LEVEL`. */
export function intimacyLevel(points: number): number {
  return Math.min(
    INTIMACY_MAX_LEVEL,
    1 + Math.floor(Math.max(0, points) / INTIMACY_POINTS_PER_LEVEL),
  );
}

/** `null` when there are not enough bananas. */
export function feedMascot(
  state: HouseState,
  today: string,
): HouseState | null {
  if (state.bananas < HOUSE_ACTION_COST.feed) return null;
  return grantIntimacy(
    {
      ...state,
      bananas: state.bananas - HOUSE_ACTION_COST.feed,
      fedLocalDate: today,
    },
    today,
  );
}

/**
 * Petting always succeeds.
 *
 * It costs nothing and has no daily cap, so there is no failure case to
 * report. Only the intimacy it pays is limited, and running out of that never
 * blocks the touch itself.
 */
export function petMascot(state: HouseState, today: string): HouseState {
  const petted = todaysCount(state.pettedLocalDate, state.pettedCount, today);
  return grantIntimacy(
    { ...state, pettedLocalDate: today, pettedCount: petted + 1 },
    today,
  );
}

/** Records that the banana catch game was opened today. */
export function recordGamePlay(state: HouseState, today: string): HouseState {
  if (state.playedGameLocalDate === today) return state;
  return { ...state, playedGameLocalDate: today };
}

/** How far each daily quest has come today. */
export function dailyQuestProgress(
  state: HouseState,
  {
    today,
    workoutCompletedToday,
  }: { today: string; workoutCompletedToday: boolean },
): Record<HouseQuestId, number> {
  return {
    visit: state.visitedLocalDates.includes(today) ? 1 : 0,
    pet: todaysCount(state.pettedLocalDate, state.pettedCount, today),
    workout: workoutCompletedToday ? 1 : 0,
  };
}

/**
 * Pays out every daily quest whose target has been met and not yet paid, and
 * pays the workout its one intimacy point for the day.
 *
 * Idempotent within a day: `paidQuestIds` is keyed to `questLocalDate`, so
 * re-running this on every state change never grants twice. A quest left unmet
 * is simply not paid — it is never charged for.
 */
export function settleHouseDay(
  state: HouseState,
  args: { today: string; workoutCompletedToday: boolean },
): { state: HouseState; granted: number } {
  const { today } = args;
  const progress = dailyQuestProgress(state, args);
  const paid = new Set(
    state.questLocalDate === today ? state.paidQuestIds : [],
  );

  let next: HouseState = state;
  let granted = 0;
  const newlyPaid: HouseQuestId[] = [];

  for (const quest of HOUSE_DAILY_QUESTS) {
    if (paid.has(quest.id)) continue;
    if (progress[quest.id] < quest.target) continue;
    granted += quest.reward;
    newlyPaid.push(quest.id);
    // The workout is the third way to raise intimacy, alongside petting and
    // feeding. It pays once, the day the session lands.
    if (quest.id === 'workout') next = grantIntimacy(next, today);
  }

  if (newlyPaid.length === 0) {
    // Still roll the day over so a stale list cannot suppress today's payouts.
    if (state.questLocalDate === today) return { state, granted: 0 };
    return {
      state: { ...state, questLocalDate: today, paidQuestIds: [] },
      granted: 0,
    };
  }

  return {
    state: {
      ...next,
      bananas: next.bananas + granted,
      questLocalDate: today,
      paidQuestIds: [...paid, ...newlyPaid],
    },
    granted,
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
    itemPlacements: {
      ...state.itemPlacements,
      [itemId]: DEFAULT_ITEM_PLACEMENTS[itemId],
    },
  };
}

/** Updates a purchased decoration only; locked catalogue items cannot move. */
export function placeHouseItem(
  state: HouseState,
  itemId: HouseItemId,
  placement: HouseItemPlacement,
): HouseState | null {
  if (!state.ownedItemIds.includes(itemId)) return null;
  const next = normalizePlacement(placement);
  const current = state.itemPlacements[itemId];
  if (current?.x === next.x && current.y === next.y) return state;
  return {
    ...state,
    itemPlacements: { ...state.itemPlacements, [itemId]: next },
  };
}

/** Changes only the room skin; backgrounds are free and never spend rewards. */
export function selectBackground(
  state: HouseState,
  backgroundId: HouseBackgroundId,
): HouseState {
  if (state.selectedBackgroundId === backgroundId) return state;
  return { ...state, selectedBackgroundId: backgroundId };
}

export type HouseView = {
  bananas: number;
  selectedBackgroundId: HouseBackgroundId;
  /** `null` when the week could not be read; the screen says so rather than guessing. */
  weekTargetCount: number | null;
  weekCompletedCount: number;
  /** 0–1, clamped. `null` when there is no target to measure against. */
  weekProgress: number | null;
  weekClosed: boolean;
  reportReady: boolean;
  visitStreakDays: number;
  workoutStreakDays: number;
  fedToday: boolean;
  pettedToday: boolean;
  /** How many times the mascot has been petted today. */
  pettedCountToday: number;
  /** 1–`INTIMACY_MAX_LEVEL`; the filled hearts on the chip. */
  intimacyLevel: number;
  intimacyPoints: number;
  /** Intimacy still available today, out of `INTIMACY_DAILY_EARN_LIMIT`. */
  intimacyRemainingToday: number;
  questProgress: Record<HouseQuestId, number>;
  questsCompletedCount: number;
  questCount: number;
  gamePlayedToday: boolean;
  canPlayGame: boolean;
  ownedItems: readonly HouseItem[];
  itemPlacements: Record<HouseItemId, HouseItemPlacement>;
  lockedItems: readonly HouseItem[];
  canFeed: boolean;
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
  const workoutCompletedToday = completedDates.includes(today);
  const questProgress = dailyQuestProgress(state, {
    today,
    workoutCompletedToday,
  });
  const intimacyEarnedToday = todaysCount(
    state.intimacyLocalDate,
    state.intimacyEarnedToday,
    today,
  );
  const gamePlayedToday = state.playedGameLocalDate === today;

  return {
    bananas: state.bananas,
    selectedBackgroundId: state.selectedBackgroundId,
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
    fedToday: state.fedLocalDate === today,
    pettedToday: questProgress.pet > 0,
    pettedCountToday: questProgress.pet,
    intimacyLevel: intimacyLevel(state.intimacyPoints),
    intimacyPoints: state.intimacyPoints,
    intimacyRemainingToday: Math.max(
      0,
      INTIMACY_DAILY_EARN_LIMIT - intimacyEarnedToday,
    ),
    questProgress,
    questsCompletedCount: HOUSE_DAILY_QUESTS.filter(
      (quest) => questProgress[quest.id] >= quest.target,
    ).length,
    questCount: HOUSE_DAILY_QUESTS.length,
    gamePlayedToday,
    canPlayGame: !gamePlayedToday,
    ownedItems: HOUSE_ITEMS.filter((item) => owned.has(item.id)),
    itemPlacements: HOUSE_ITEMS.reduce<Record<HouseItemId, HouseItemPlacement>>(
      (placements, item) => {
        placements[item.id] =
          state.itemPlacements[item.id] ?? DEFAULT_ITEM_PLACEMENTS[item.id];
        return placements;
      },
      {} as Record<HouseItemId, HouseItemPlacement>,
    ),
    lockedItems,
    canFeed: state.bananas >= HOUSE_ACTION_COST.feed,
    canDecorate: lockedItems.some((item) => state.bananas >= item.cost),
  };
}

function normalizePlacement(placement: HouseItemPlacement): HouseItemPlacement {
  return {
    x: clampUnit(placement.x),
    y: clampUnit(placement.y),
  };
}

function parseItemPlacements(
  raw: unknown,
  knownItemIds: ReadonlySet<string>,
): HouseItemPlacements {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return {};
  const parsed: HouseItemPlacements = {};
  for (const [itemId, placement] of Object.entries(
    raw as Record<string, unknown>,
  )) {
    if (!knownItemIds.has(itemId)) continue;
    if (
      typeof placement !== 'object' ||
      placement === null ||
      Array.isArray(placement)
    ) {
      continue;
    }
    const candidate = placement as Record<string, unknown>;
    if (
      typeof candidate.x !== 'number' ||
      !Number.isFinite(candidate.x) ||
      typeof candidate.y !== 'number' ||
      !Number.isFinite(candidate.y)
    ) {
      continue;
    }
    parsed[itemId as HouseItemId] = normalizePlacement({
      x: candidate.x,
      y: candidate.y,
    });
  }
  return parsed;
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
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

/**
 * House copy, keyed to how the week has gone.
 *
 * The nil case stays an invitation rather than a shortfall: the mascot never
 * expresses disappointment about a week that has not started, so there is
 * deliberately no line here that reads as one.
 */
export function houseCaption(view: HouseView): string {
  if (view.weekTargetCount === null) {
    return '이번 주 정보를 불러오지 못했어요. 집은 그대로 있어요.';
  }
  if (view.weekProgress !== null && view.weekProgress >= 1) {
    return '이번 주 목표 달성! 대단해! 🎉';
  }
  if (view.weekCompletedCount === 1) {
    return '이번 주 첫 운동 완료!\n또 같이 하자!';
  }
  if (view.weekCompletedCount > 1) {
    return `이번 주 ${view.weekCompletedCount}번 함께했어요.\n한 번만 더! 💪`;
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
  if (pose === 'petted') return pettedSpeech(view.pettedCountToday);
  if (!view.fedToday && view.canFeed) return '밥 주세요!!!';
  return houseCaption(view);
}

/**
 * What the mascot says when it is petted.
 *
 * Petting is unlimited now, so a single fixed line would wear out within one
 * visit. The caller passes a number it already has — the pet count for the day
 * — and the pool is indexed by it rather than by a random draw, so the same
 * state always renders the same bubble and tests stay deterministic.
 */
export const PETTED_SPEECH = [
  '헤헤, 기분 좋아요.',
  '해헤 좋아!\n한 번 더!',
  '거기 좋아요…',
  '오늘도 와 줬네요!',
  '히히, 간지러워요.',
] as const;

export function pettedSpeech(pettedCount: number): string {
  const index = Math.max(0, Math.floor(pettedCount) - 1) % PETTED_SPEECH.length;
  return PETTED_SPEECH[index] ?? PETTED_SPEECH[0];
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

/** A stored tally read back as a whole number, missing or corrupt meaning zero. */
function counter(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
}
