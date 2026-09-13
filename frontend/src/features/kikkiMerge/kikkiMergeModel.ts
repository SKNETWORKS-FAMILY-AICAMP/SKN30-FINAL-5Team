/** Pure rules shared by the merge screen and its Matter.js adapter. */

export const KIKKI_MERGE_TICK_MS = 1000 / 30;
export const KIKKI_MERGE_DROP_COOLDOWN_MS = 420;
export const KIKKI_MERGE_DANGER_HOLD_MS = 2_600;
export const KIKKI_MERGE_MAX_SCORE = 200;
export const KIKKI_MERGE_WORLD_WIDTH = 360;
export const KIKKI_MERGE_WORLD_HEIGHT = 560;
export const KIKKI_MERGE_DANGER_Y = 84;
export const KIKKI_MERGE_DANGER_CONTACT_GRACE = 2;
export const KIKKI_MERGE_DROP_Y = 44;
export const KIKKI_MERGE_POINTS_PER_MERGE = 1;

/** Small visual gaps still count as a match, so the art feels like the collider. */
export const KIKKI_MERGE_CONTACT_GRACE = 6;

export const KIKKI_MERGE_TIERS = [
  { name: '아기 끼끼', radius: 18, color: '#FFF1D2' },
  { name: '새싹 끼끼', radius: 22, color: '#FFE6A8' },
  { name: '씩씩한 끼끼', radius: 27, color: '#FFCF78' },
  { name: '건강한 끼끼', radius: 33, color: '#BCE38B' },
  { name: '집중 끼끼', radius: 40, color: '#91D8C3' },
  { name: '활력 끼끼', radius: 48, color: '#7DC9E8' },
  { name: '도전 끼끼', radius: 58, color: '#91AEEB' },
  { name: '프로 끼끼', radius: 69, color: '#BBA2EC' },
  { name: '스타 끼끼', radius: 82, color: '#E8B1D4' },
  { name: '마스터 끼끼', radius: 96, color: '#FFD67A' },
  { name: '챔피언 끼끼', radius: 110, color: '#FFB95D' },
] as const;

export type KikkiMergeTier = number;

export type KikkiMergeRound = {
  status: 'ready' | 'playing' | 'finished';
  score: number;
  mergeCount: number;
  createdTierCounts: number[];
  finishReason: 'overflow' | null;
};

export function createKikkiMergeRound(): KikkiMergeRound {
  return {
    status: 'ready',
    score: 0,
    mergeCount: 0,
    createdTierCounts: KIKKI_MERGE_TIERS.map(() => 0),
    finishReason: null,
  };
}

export function startKikkiMergeRound(): KikkiMergeRound {
  return { ...createKikkiMergeRound(), status: 'playing' };
}

export function finishKikkiMergeFromOverflow(
  round: KikkiMergeRound,
): KikkiMergeRound {
  if (round.status !== 'playing') return round;
  return { ...round, status: 'finished', finishReason: 'overflow' };
}

export function addKikkiMergeScore(
  round: KikkiMergeRound,
  resultTier: KikkiMergeTier,
): KikkiMergeRound {
  const tier = KIKKI_MERGE_TIERS[resultTier];
  if (round.status !== 'playing' || tier === undefined) return round;
  return {
    ...round,
    score: Math.min(
      KIKKI_MERGE_MAX_SCORE,
      round.score + KIKKI_MERGE_POINTS_PER_MERGE,
    ),
    mergeCount: round.mergeCount + 1,
    createdTierCounts: round.createdTierCounts.map((count, index) =>
      index === resultTier ? count + 1 : count,
    ),
  };
}

/** Player-facing stages are one-based while physics tiers are zero-based. */
export function getKikkiMergeCreatedStageCount(
  round: KikkiMergeRound,
  stage: number,
): number {
  if (!Number.isInteger(stage) || stage < 1) return 0;
  return round.createdTierCounts[stage - 1] ?? 0;
}

/** Only the first four tiers enter from the queue; larger faces are earned. */
export function nextKikkiMergeTier(random: () => number = Math.random): number {
  const roll = Math.min(0.999999, Math.max(0, random()));
  if (roll < 0.25) return 0;
  if (roll < 0.55) return 1;
  if (roll < 0.85) return 2;
  return 3;
}

export function clampKikkiDropX(x: number, tier: number): number {
  const radius = KIKKI_MERGE_TIERS[tier]?.radius ?? KIKKI_MERGE_TIERS[0].radius;
  return Math.min(
    KIKKI_MERGE_WORLD_WIDTH - radius - 4,
    Math.max(radius + 4, x),
  );
}

export function isKikkiMergeDangerContact(
  orbTop: number,
  dangerArmed: boolean,
): boolean {
  return (
    dangerArmed &&
    orbTop <= KIKKI_MERGE_DANGER_Y + KIKKI_MERGE_DANGER_CONTACT_GRACE
  );
}
