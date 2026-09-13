/**
 * Pure rules for the Kkikki runner prototype.
 *
 * The player stays at a fixed horizontal position while objects move from
 * right to left. Heights and positions are normalized so the same state can
 * render on phones, tablets and the web preview without device branches.
 */

export const KIKKI_RUNNER_DURATION_MS = 60_000;
export const KIKKI_RUNNER_TICK_MS = 50;
export const KIKKI_RUNNER_SPAWN_INTERVAL_MS = 850;
export const KIKKI_RUNNER_PLAYER_X = 0.2;
export const KIKKI_RUNNER_MAX_LIVES = 3;
export const KIKKI_RUNNER_CLIFF_HALF_WIDTH = 0.09;
export const KIKKI_RUNNER_MAX_ROCKS_PER_CLUSTER = 3;
export const KIKKI_RUNNER_CLIFF_SPAWN_X = 1.5;

const BASE_WORLD_SPEED_PER_MS = 1 / 3_000;
const MAX_WORLD_SPEED_PER_MS = 1 / 750;
// Start making the pace noticeable during the first quarter, while still
// reserving the steepest speed for the closing stretch.
const WORLD_SPEED_CURVE_EXPONENT = 1.45;
// Stretch the original jump over 1.6x as much time while preserving its peak.
// Together with the tighter hitboxes, this makes one rock clearable with one
// well-timed jump even at the slowest (widest collision-window) world speed.
const JUMP_VELOCITY_PER_MS = 0.00118 / 1.6;
const GRAVITY_PER_MS_SQUARED = -0.0000034 / (1.6 * 1.6);
const PLAYER_HALF_WIDTH = 0.04;
const PLAYER_CENTER_HEIGHT = 0.065;
const PLAYER_COLLECT_HALF_HEIGHT = 0.085;
const ROCK_HALF_WIDTH = 0.04;
const BANANA_HALF_WIDTH = 0.035;
const ROCK_CLEAR_HEIGHT = 0.105;
const HIT_INVULNERABILITY_MS = 900;
const BANANAS_PER_TRAIL = 5;
const BANANA_SPACING = 0.055;
const ROCK_CLUSTER_SPACING = 0.09;
const CLIFFS_UNLOCK_AT_MS = 3_000;
const CLIFF_FALL_DURATION_MS = 750;
const CLIFF_FALL_GRAVITY_PER_MS_SQUARED = -0.0000014;
const OBJECT_DESPAWN_X = -0.12;
// The cliff's broken-road cap is wider than the collision gap. Keep the
// object alive until that trailing artwork has also cleared a tall phone.
const CLIFF_DESPAWN_X = -0.52;

/** The mini-game reward API rejects a client-reported score above 200. */
export const KIKKI_RUNNER_MAX_SCORE = 200;

export type KikkiRunnerObjectKind = 'banana' | 'rock' | 'cliff';
export type KikkiRunnerFinishReason = 'time_up' | 'lives_empty' | 'cliff';

export type KikkiRunnerObject = {
  id: number;
  kind: KikkiRunnerObjectKind;
  x: number;
  /** Height above the running surface, in normalized arena units. */
  height: number;
  rotationDeg: number;
};

export type KikkiRunnerState = {
  status: 'ready' | 'playing' | 'falling' | 'finished';
  elapsedMs: number;
  spawnElapsedMs: number;
  fallElapsedMs: number;
  /** Total normalized world travel, used to keep parallax motion in sync. */
  worldOffset: number;
  distanceM: number;
  score: number;
  lives: number;
  playerHeight: number;
  playerVelocity: number;
  jumpsUsed: number;
  invulnerabilityMs: number;
  nextObjectId: number;
  lastPatternKind: KikkiRunnerObjectKind | null;
  finishReason: KikkiRunnerFinishReason | null;
  objects: KikkiRunnerObject[];
};

export function createKikkiRunnerState(): KikkiRunnerState {
  return {
    status: 'ready',
    elapsedMs: 0,
    spawnElapsedMs: 0,
    fallElapsedMs: 0,
    worldOffset: 0,
    distanceM: 0,
    score: 0,
    lives: KIKKI_RUNNER_MAX_LIVES,
    playerHeight: 0,
    playerVelocity: 0,
    jumpsUsed: 0,
    invulnerabilityMs: 0,
    nextObjectId: 1,
    lastPatternKind: null,
    finishReason: null,
    objects: [],
  };
}

export function startKikkiRunner(
  random: () => number = Math.random,
): KikkiRunnerState {
  const opening = spawnPattern(1, random, true, false);
  return {
    ...createKikkiRunnerState(),
    status: 'playing',
    nextObjectId: opening.nextObjectId,
    lastPatternKind: opening.kind,
    objects: opening.objects,
  };
}

/** Supports Cookie Run-style single and double jumps. */
export function jumpKikkiRunner(state: KikkiRunnerState): KikkiRunnerState {
  if (state.status !== 'playing' || state.jumpsUsed >= 2) return state;
  return {
    ...state,
    jumpsUsed: state.jumpsUsed + 1,
    playerVelocity: JUMP_VELOCITY_PER_MS,
  };
}

export function advanceKikkiRunner(
  state: KikkiRunnerState,
  deltaMs: number,
  random: () => number = Math.random,
): KikkiRunnerState {
  if (deltaMs <= 0) return state;
  if (state.status === 'falling') return advanceCliffFall(state, deltaMs);
  if (state.status !== 'playing') return state;

  const stepMs = Math.min(deltaMs, KIKKI_RUNNER_DURATION_MS - state.elapsedMs);
  const elapsedMs = state.elapsedMs + stepMs;
  const speed = worldSpeed(elapsedMs);
  const worldOffset = state.worldOffset + speed * stepMs;
  const nextVelocity = state.playerVelocity + GRAVITY_PER_MS_SQUARED * stepMs;
  const airborneHeight =
    state.playerHeight +
    state.playerVelocity * stepMs +
    0.5 * GRAVITY_PER_MS_SQUARED * stepMs * stepMs;
  const landed = airborneHeight <= 0;
  const playerHeight = landed ? 0 : airborneHeight;
  const playerVelocity = landed ? 0 : nextVelocity;
  const jumpsUsed = landed ? 0 : state.jumpsUsed;
  let invulnerabilityMs = Math.max(0, state.invulnerabilityMs - stepMs);
  let score = state.score;
  let lives = state.lives;
  let finishReason = state.finishReason;
  let fellIntoCliff = false;

  const objects = state.objects.flatMap((object) => {
    const nextX = object.x - speed * stepMs;
    const halfWidth =
      object.kind === 'banana'
        ? BANANA_HALF_WIDTH
        : object.kind === 'rock'
          ? ROCK_HALF_WIDTH
          : KIKKI_RUNNER_CLIFF_HALF_WIDTH;
    const crossesPlayer =
      Math.min(object.x, nextX) <=
        KIKKI_RUNNER_PLAYER_X + PLAYER_HALF_WIDTH + halfWidth &&
      Math.max(object.x, nextX) >=
        KIKKI_RUNNER_PLAYER_X - PLAYER_HALF_WIDTH - halfWidth;
    const playerCenterEntersCliff =
      object.kind === 'cliff' &&
      Math.min(object.x, nextX) <=
        KIKKI_RUNNER_PLAYER_X + KIKKI_RUNNER_CLIFF_HALF_WIDTH &&
      Math.max(object.x, nextX) >=
        KIKKI_RUNNER_PLAYER_X - KIKKI_RUNNER_CLIFF_HALF_WIDTH;

    if (crossesPlayer) {
      if (
        object.kind === 'banana' &&
        Math.abs(object.height - (playerHeight + PLAYER_CENTER_HEIGHT)) <=
          PLAYER_COLLECT_HALF_HEIGHT
      ) {
        score = Math.min(KIKKI_RUNNER_MAX_SCORE, score + 1);
        return [];
      }
      if (
        object.kind === 'rock' &&
        playerHeight < ROCK_CLEAR_HEIGHT &&
        invulnerabilityMs === 0
      ) {
        lives = Math.max(0, lives - 1);
        invulnerabilityMs = HIT_INVULNERABILITY_MS;
        return [];
      }
      if (
        object.kind === 'cliff' &&
        playerCenterEntersCliff &&
        playerHeight === 0
      ) {
        lives = 0;
        finishReason = 'cliff';
        fellIntoCliff = true;
      }
    }

    const despawnX =
      object.kind === 'cliff' ? CLIFF_DESPAWN_X : OBJECT_DESPAWN_X;
    if (nextX < despawnX) return [];
    return [
      {
        ...object,
        x: nextX,
        rotationDeg:
          object.kind === 'banana'
            ? object.rotationDeg + stepMs * 0.045
            : object.rotationDeg,
      },
    ];
  });

  let spawnElapsedMs = state.spawnElapsedMs + stepMs;
  let nextObjectId = state.nextObjectId;
  let lastPatternKind = state.lastPatternKind;
  while (
    spawnElapsedMs >= KIKKI_RUNNER_SPAWN_INTERVAL_MS &&
    elapsedMs < KIKKI_RUNNER_DURATION_MS &&
    lives > 0
  ) {
    spawnElapsedMs -= KIKKI_RUNNER_SPAWN_INTERVAL_MS;
    // A banana trail always separates hazards. It prevents an unavoidable
    // rock-to-cliff sequence while keeping most of the screen full of pickups.
    const forceBananas =
      lastPatternKind === 'rock' || lastPatternKind === 'cliff';
    const pattern = spawnPattern(
      nextObjectId,
      random,
      forceBananas,
      elapsedMs >= CLIFFS_UNLOCK_AT_MS,
    );
    objects.push(...pattern.objects);
    nextObjectId = pattern.nextObjectId;
    lastPatternKind = pattern.kind;
  }

  const finished =
    elapsedMs >= KIKKI_RUNNER_DURATION_MS || (lives === 0 && !fellIntoCliff);
  if (finished && finishReason === null) {
    finishReason =
      elapsedMs >= KIKKI_RUNNER_DURATION_MS ? 'time_up' : 'lives_empty';
  }
  return {
    ...state,
    status: fellIntoCliff ? 'falling' : finished ? 'finished' : 'playing',
    elapsedMs,
    spawnElapsedMs,
    worldOffset,
    distanceM: Math.floor(elapsedMs / 100),
    score,
    lives,
    playerHeight,
    playerVelocity,
    jumpsUsed,
    invulnerabilityMs,
    nextObjectId,
    lastPatternKind,
    finishReason,
    objects: finished ? [] : objects,
  };
}

function advanceCliffFall(
  state: KikkiRunnerState,
  deltaMs: number,
): KikkiRunnerState {
  const stepMs = Math.min(
    deltaMs,
    CLIFF_FALL_DURATION_MS - state.fallElapsedMs,
  );
  const fallElapsedMs = state.fallElapsedMs + stepMs;
  const playerHeight =
    state.playerHeight +
    state.playerVelocity * stepMs +
    0.5 * CLIFF_FALL_GRAVITY_PER_MS_SQUARED * stepMs * stepMs;
  const playerVelocity =
    state.playerVelocity + CLIFF_FALL_GRAVITY_PER_MS_SQUARED * stepMs;
  const finished = fallElapsedMs >= CLIFF_FALL_DURATION_MS;

  return {
    ...state,
    status: finished ? 'finished' : 'falling',
    fallElapsedMs,
    playerHeight,
    playerVelocity,
    objects: finished ? [] : state.objects,
  };
}

export function kikkiRunnerSecondsLeft(state: KikkiRunnerState): number {
  return Math.ceil(
    Math.max(0, KIKKI_RUNNER_DURATION_MS - state.elapsedMs) / 1_000,
  );
}

export function kikkiRunnerProgress(state: KikkiRunnerState): number {
  return Math.min(1, Math.max(0, state.elapsedMs / KIKKI_RUNNER_DURATION_MS));
}

function worldSpeed(elapsedMs: number): number {
  const progress = Math.min(1, elapsedMs / KIKKI_RUNNER_DURATION_MS);
  const acceleratedProgress = progress ** WORLD_SPEED_CURVE_EXPONENT;
  return (
    BASE_WORLD_SPEED_PER_MS +
    (MAX_WORLD_SPEED_PER_MS - BASE_WORLD_SPEED_PER_MS) * acceleratedProgress
  );
}

function spawnPattern(
  firstId: number,
  random: () => number,
  forceBananas: boolean,
  allowCliff: boolean,
): {
  kind: KikkiRunnerObjectKind;
  nextObjectId: number;
  objects: KikkiRunnerObject[];
} {
  const patternRoll = random();
  const kind: KikkiRunnerObjectKind = forceBananas
    ? 'banana'
    : patternRoll < 0.68
      ? 'banana'
      : patternRoll < 0.9 || !allowCliff
        ? 'rock'
        : 'cliff';

  if (kind === 'banana') {
    const arc = random() < 0.45;
    const arcHeights = [0.065, 0.13, 0.205, 0.13, 0.065];
    const objects = Array.from({ length: BANANAS_PER_TRAIL }, (_, index) => ({
      id: firstId + index,
      kind: 'banana' as const,
      x: 1.08 + index * BANANA_SPACING,
      height: arc ? (arcHeights[index] ?? 0.065) : 0.065,
      rotationDeg: (random() - 0.5) * 35,
    }));
    return {
      kind,
      nextObjectId: firstId + objects.length,
      objects,
    };
  }

  if (kind === 'rock') {
    const rockCount =
      1 +
      Math.min(
        KIKKI_RUNNER_MAX_ROCKS_PER_CLUSTER - 1,
        Math.floor(random() * KIKKI_RUNNER_MAX_ROCKS_PER_CLUSTER),
      );
    const objects = Array.from({ length: rockCount }, (_, index) => ({
      id: firstId + index,
      kind: 'rock' as const,
      x: 1.08 + index * ROCK_CLUSTER_SPACING,
      height: 0,
      rotationDeg: 0,
    }));
    return {
      kind,
      nextObjectId: firstId + objects.length,
      objects,
    };
  }

  return {
    kind,
    nextObjectId: firstId + 1,
    objects: [
      {
        id: firstId,
        kind,
        x: KIKKI_RUNNER_CLIFF_SPAWN_X,
        height: 0,
        rotationDeg: 0,
      },
    ],
  };
}
