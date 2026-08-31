/**
 * Pure rules for the banana catch mini-game.
 *
 * Positions are normalized to 0..1 so the same state works on every screen
 * size. Rendering, timers and touch input stay in the screen component.
 */

export const BANANA_CATCH_DURATION_MS = 30_000;
export const BANANA_CATCH_TICK_MS = 50;
export const BANANA_SPAWN_INTERVAL_MS = 650;
export const BANANA_FALL_PER_MS = 1 / 4_200;
export const PLAYER_HALF_WIDTH = 0.11;
export const BANANA_HALF_WIDTH = 0.035;

const DEFAULT_CATCH_LINE_Y = 0.75;

export type FallingBanana = {
  id: number;
  x: number;
  y: number;
  rotationDeg: number;
  rotationSpeedDegPerSecond: number;
};

export type BananaBasketStage = 'empty' | 'medium' | 'full';

export type BananaCatchState = {
  status: 'ready' | 'playing' | 'finished';
  score: number;
  elapsedMs: number;
  spawnElapsedMs: number;
  playerX: number;
  nextBananaId: number;
  bananas: FallingBanana[];
};

export function createBananaCatchState(): BananaCatchState {
  return {
    status: 'ready',
    score: 0,
    elapsedMs: 0,
    spawnElapsedMs: 0,
    playerX: 0.5,
    nextBananaId: 1,
    bananas: [],
  };
}

export function startBananaCatch(
  random: () => number = Math.random,
  bananaHalfWidthX: number = BANANA_HALF_WIDTH,
): BananaCatchState {
  return {
    ...createBananaCatchState(),
    status: 'playing',
    nextBananaId: 2,
    bananas: [spawnBanana(1, random, bananaHalfWidthX)],
  };
}

export function moveBananaCatcher(
  state: BananaCatchState,
  normalizedX: number,
  playerHalfWidthX: number = PLAYER_HALF_WIDTH,
): BananaCatchState {
  const safeHalfWidthX = clamp(playerHalfWidthX, 0, 0.5);
  const playerX = clamp(normalizedX, safeHalfWidthX, 1 - safeHalfWidthX);
  return playerX === state.playerX ? state : { ...state, playerX };
}

export function advanceBananaCatch(
  state: BananaCatchState,
  deltaMs: number,
  random: () => number = Math.random,
  catchLineY: number = DEFAULT_CATCH_LINE_Y,
  catchHalfWidthX: number = PLAYER_HALF_WIDTH + BANANA_HALF_WIDTH,
  bananaHalfWidthX: number = BANANA_HALF_WIDTH,
): BananaCatchState {
  if (state.status !== 'playing' || deltaMs <= 0) return state;

  const stepMs = Math.min(deltaMs, BANANA_CATCH_DURATION_MS - state.elapsedMs);
  const elapsedMs = state.elapsedMs + stepMs;
  let score = state.score;

  const bananas = state.bananas.flatMap((banana) => {
    const nextY = banana.y + BANANA_FALL_PER_MS * stepMs;
    const crossedCatchLine = banana.y < catchLineY && nextY >= catchLineY;
    const overlapsCatcher =
      Math.abs(banana.x - state.playerX) <= catchHalfWidthX;

    if (crossedCatchLine && overlapsCatcher) {
      score += 1;
      return [];
    }
    if (nextY > 1) return [];
    return [
      {
        ...banana,
        y: nextY,
        rotationDeg:
          banana.rotationDeg +
          banana.rotationSpeedDegPerSecond * (stepMs / 1_000),
      },
    ];
  });

  let spawnElapsedMs = state.spawnElapsedMs + stepMs;
  let nextBananaId = state.nextBananaId;
  while (
    spawnElapsedMs >= BANANA_SPAWN_INTERVAL_MS &&
    elapsedMs < BANANA_CATCH_DURATION_MS
  ) {
    spawnElapsedMs -= BANANA_SPAWN_INTERVAL_MS;
    bananas.push(spawnBanana(nextBananaId, random, bananaHalfWidthX));
    nextBananaId += 1;
  }

  const finished = elapsedMs >= BANANA_CATCH_DURATION_MS;
  return {
    ...state,
    status: finished ? 'finished' : 'playing',
    elapsedMs,
    spawnElapsedMs,
    score,
    nextBananaId,
    bananas: finished ? [] : bananas,
  };
}

export function bananaCatchSecondsLeft(state: BananaCatchState): number {
  return Math.ceil(
    Math.max(0, BANANA_CATCH_DURATION_MS - state.elapsedMs) / 1_000,
  );
}

/** The collecting mascot changes for each ten bananas caught. */
export function bananaBasketStage(score: number): BananaBasketStage {
  if (score >= 20) return 'full';
  if (score >= 10) return 'medium';
  return 'empty';
}

function spawnBanana(
  id: number,
  random: () => number,
  bananaHalfWidthX: number,
): FallingBanana {
  const safeHalfWidthX = clamp(bananaHalfWidthX, 0, 0.5);
  return {
    id,
    x: clamp(random(), safeHalfWidthX, 1 - safeHalfWidthX),
    y: -0.08,
    rotationDeg: (random() - 0.5) * 70,
    // At most one turn per roughly ten seconds, with near-zero values making
    // some bananas look almost still while others visibly tumble.
    rotationSpeedDegPerSecond: (random() - 0.5) * 70,
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) return (minimum + maximum) / 2;
  return Math.min(maximum, Math.max(minimum, value));
}
