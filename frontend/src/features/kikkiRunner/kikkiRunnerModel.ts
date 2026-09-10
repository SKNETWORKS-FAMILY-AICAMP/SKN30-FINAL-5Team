/**
 * Pure rules for the Kkikki runner prototype.
 *
 * The player stays at a fixed horizontal position while objects move from
 * right to left. Heights and positions are normalized so the same state can
 * render on phones, tablets and the web preview without device branches.
 */

export const KIKKI_RUNNER_DURATION_MS = 30_000;
export const KIKKI_RUNNER_TICK_MS = 50;
export const KIKKI_RUNNER_SPAWN_INTERVAL_MS = 720;
export const KIKKI_RUNNER_PLAYER_X = 0.2;
export const KIKKI_RUNNER_MAX_LIVES = 3;

const BASE_WORLD_SPEED_PER_MS = 1 / 3_600;
const MAX_WORLD_SPEED_PER_MS = 1 / 2_350;
const JUMP_VELOCITY_PER_MS = 0.00118;
const GRAVITY_PER_MS_SQUARED = -0.0000034;
const PLAYER_HALF_WIDTH = 0.055;
const PLAYER_CENTER_HEIGHT = 0.065;
const PLAYER_COLLECT_HALF_HEIGHT = 0.085;
const ROCK_HALF_WIDTH = 0.052;
const BANANA_HALF_WIDTH = 0.035;
const ROCK_CLEAR_HEIGHT = 0.105;
const HIT_INVULNERABILITY_MS = 900;

export type KikkiRunnerObject = {
  id: number;
  kind: 'banana' | 'rock';
  x: number;
  /** Height above the running surface, in normalized arena units. */
  height: number;
  rotationDeg: number;
};

export type KikkiRunnerState = {
  status: 'ready' | 'playing' | 'finished';
  elapsedMs: number;
  spawnElapsedMs: number;
  distanceM: number;
  score: number;
  lives: number;
  playerHeight: number;
  playerVelocity: number;
  jumpsUsed: number;
  invulnerabilityMs: number;
  nextObjectId: number;
  objects: KikkiRunnerObject[];
};

export function createKikkiRunnerState(): KikkiRunnerState {
  return {
    status: 'ready',
    elapsedMs: 0,
    spawnElapsedMs: 0,
    distanceM: 0,
    score: 0,
    lives: KIKKI_RUNNER_MAX_LIVES,
    playerHeight: 0,
    playerVelocity: 0,
    jumpsUsed: 0,
    invulnerabilityMs: 0,
    nextObjectId: 1,
    objects: [],
  };
}

export function startKikkiRunner(
  random: () => number = Math.random,
): KikkiRunnerState {
  return {
    ...createKikkiRunnerState(),
    status: 'playing',
    nextObjectId: 2,
    objects: [spawnObject(1, random, true)],
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
  if (state.status !== 'playing' || deltaMs <= 0) return state;

  const stepMs = Math.min(deltaMs, KIKKI_RUNNER_DURATION_MS - state.elapsedMs);
  const elapsedMs = state.elapsedMs + stepMs;
  const speed = worldSpeed(elapsedMs);
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

  const objects = state.objects.flatMap((object) => {
    const nextX = object.x - speed * stepMs;
    const halfWidth =
      object.kind === 'banana' ? BANANA_HALF_WIDTH : ROCK_HALF_WIDTH;
    const crossesPlayer =
      Math.min(object.x, nextX) <=
        KIKKI_RUNNER_PLAYER_X + PLAYER_HALF_WIDTH + halfWidth &&
      Math.max(object.x, nextX) >=
        KIKKI_RUNNER_PLAYER_X - PLAYER_HALF_WIDTH - halfWidth;

    if (crossesPlayer) {
      if (
        object.kind === 'banana' &&
        Math.abs(object.height - (playerHeight + PLAYER_CENTER_HEIGHT)) <=
          PLAYER_COLLECT_HALF_HEIGHT
      ) {
        score += 1;
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
    }

    if (nextX < -0.12) return [];
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
  while (
    spawnElapsedMs >= KIKKI_RUNNER_SPAWN_INTERVAL_MS &&
    elapsedMs < KIKKI_RUNNER_DURATION_MS &&
    lives > 0
  ) {
    spawnElapsedMs -= KIKKI_RUNNER_SPAWN_INTERVAL_MS;
    objects.push(spawnObject(nextObjectId, random, false));
    nextObjectId += 1;
  }

  const finished = elapsedMs >= KIKKI_RUNNER_DURATION_MS || lives === 0;
  return {
    ...state,
    status: finished ? 'finished' : 'playing',
    elapsedMs,
    spawnElapsedMs,
    distanceM: Math.floor(elapsedMs / 100),
    score,
    lives,
    playerHeight,
    playerVelocity,
    jumpsUsed,
    invulnerabilityMs,
    nextObjectId,
    objects: finished ? [] : objects,
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
  const progress = elapsedMs / KIKKI_RUNNER_DURATION_MS;
  return Math.min(
    MAX_WORLD_SPEED_PER_MS,
    BASE_WORLD_SPEED_PER_MS + progress * 0.00012,
  );
}

function spawnObject(
  id: number,
  random: () => number,
  forceBanana: boolean,
): KikkiRunnerObject {
  const kind = forceBanana || random() < 0.7 ? 'banana' : 'rock';
  const heightRoll = random();
  return {
    id,
    kind,
    x: 1.08,
    height: kind === 'rock' ? 0 : heightRoll < 0.58 ? 0.065 : 0.205,
    rotationDeg: kind === 'banana' ? (random() - 0.5) * 35 : 0,
  };
}
