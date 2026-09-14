import { describe, expect, it } from '@jest/globals';

import {
  KIKKI_RUNNER_CLIFF_SPAWN_X,
  KIKKI_RUNNER_CLIFF_HALF_WIDTH,
  KIKKI_RUNNER_DURATION_MS,
  KIKKI_RUNNER_MAX_LIVES,
  KIKKI_RUNNER_MAX_ROCKS_PER_CLUSTER,
  KIKKI_RUNNER_MAX_SCORE,
  KIKKI_RUNNER_PLAYER_X,
  KIKKI_RUNNER_SPAWN_INTERVAL_MS,
  advanceKikkiRunner,
  createKikkiRunnerState,
  jumpKikkiRunner,
  kikkiRunnerProgress,
  kikkiRunnerSecondsLeft,
  startKikkiRunner,
  type KikkiRunnerState,
} from '../src/features/kikkiRunner/kikkiRunnerModel';

describe('Kkikki runner rules', () => {
  it('starts with a dense five-banana trail approaching from the right', () => {
    const state = startKikkiRunner(() => 0.5);

    expect(state.status).toBe('playing');
    expect(state.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
    expect(state.objects).toHaveLength(5);
    expect(state.objects.map((object) => object.kind)).toEqual(
      Array(5).fill('banana'),
    );
    expect(state.objects.map((object) => object.height)).toEqual(
      Array(5).fill(0.065),
    );
    expect(state.nextObjectId).toBe(6);
  });

  it('allows two jumps and resets them after landing', () => {
    const started = startKikkiRunner(() => 0.5);
    const firstJump = jumpKikkiRunner(started);
    const secondJump = jumpKikkiRunner(firstJump);

    expect(firstJump.jumpsUsed).toBe(1);
    expect(secondJump.jumpsUsed).toBe(2);
    expect(jumpKikkiRunner(secondJump)).toBe(secondJump);

    const landed = advanceKikkiRunner(
      { ...secondJump, objects: [], spawnElapsedMs: -1_000 },
      1_200,
      () => 0.5,
    );
    expect(landed.playerHeight).toBe(0);
    expect(landed.jumpsUsed).toBe(0);
  });

  it('collects a low banana without changing the wallet or life count', () => {
    const state: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      objects: [
        {
          id: 1,
          kind: 'banana',
          x: KIKKI_RUNNER_PLAYER_X,
          height: 0.065,
          rotationDeg: 0,
        },
      ],
    };

    const collected = advanceKikkiRunner(state, 50, () => 0.5);

    expect(collected.score).toBe(1);
    expect(collected.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
    expect(collected.objects).toEqual([]);
  });

  it('loses one chance on a rock and ignores another hit during recovery', () => {
    const rock = {
      id: 1,
      kind: 'rock' as const,
      x: KIKKI_RUNNER_PLAYER_X,
      height: 0,
      rotationDeg: 0,
    };
    const state: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      nextObjectId: 2,
      objects: [rock],
    };

    const hit = advanceKikkiRunner(state, 50, () => 0.5);
    const protectedHit = advanceKikkiRunner(
      { ...hit, objects: [{ ...rock, id: 2 }] },
      50,
      () => 0.5,
    );

    expect(hit.lives).toBe(KIKKI_RUNNER_MAX_LIVES - 1);
    expect(hit.invulnerabilityMs).toBeGreaterThan(0);
    expect(protectedHit.lives).toBe(hit.lives);
  });

  it('makes one rock clearable with one well-timed single jump', () => {
    let state: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      spawnElapsedMs: -100_000,
      objects: [
        {
          id: 1,
          kind: 'rock',
          x: 0.4,
          height: 0,
          rotationDeg: 0,
        },
      ],
    };

    state = jumpKikkiRunner(state);
    while (state.objects.length > 0) {
      state = advanceKikkiRunner(state, 50, () => 0.5);
    }

    expect(state.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
    expect(state.jumpsUsed).toBeLessThanOrEqual(1);
  });

  it('spawns at most three rocks together with unique ids', () => {
    const state = advanceKikkiRunner(
      {
        ...createKikkiRunnerState(),
        status: 'playing',
        spawnElapsedMs: KIKKI_RUNNER_SPAWN_INTERVAL_MS - 50,
        lastPatternKind: 'banana',
      },
      50,
      () => 0.89,
    );

    expect(state.objects).toHaveLength(KIKKI_RUNNER_MAX_ROCKS_PER_CLUSTER);
    expect(state.objects.map((object) => object.kind)).toEqual([
      'rock',
      'rock',
      'rock',
    ]);
    expect(new Set(state.objects.map((object) => object.id)).size).toBe(3);
    expect(state.nextObjectId).toBe(4);
  });

  it('spawns a cliff far enough beyond the right edge to preload its artwork', () => {
    const state = advanceKikkiRunner(
      {
        ...createKikkiRunnerState(),
        status: 'playing',
        elapsedMs: 3_000,
        spawnElapsedMs: KIKKI_RUNNER_SPAWN_INTERVAL_MS - 50,
        lastPatternKind: 'banana',
      },
      50,
      () => 0.95,
    );

    expect(state.objects).toHaveLength(1);
    expect(state.objects[0]).toMatchObject({
      kind: 'cliff',
      x: KIKKI_RUNNER_CLIFF_SPAWN_X,
    });
    expect(KIKKI_RUNNER_CLIFF_SPAWN_X).toBeGreaterThan(1.4);
  });

  it('makes a three-rock cluster clearable with a timed double jump', () => {
    let state = advanceKikkiRunner(
      {
        ...createKikkiRunnerState(),
        status: 'playing' as const,
        spawnElapsedMs: KIKKI_RUNNER_SPAWN_INTERVAL_MS - 50,
        lastPatternKind: 'banana' as const,
      },
      50,
      () => 0.89,
    );
    state = {
      ...state,
      spawnElapsedMs: -100_000,
      objects: state.objects.map((object) => ({
        ...object,
        x: object.x - 0.68,
      })),
    };

    state = jumpKikkiRunner(state);
    state = advanceKikkiRunner(state, 450, () => 0.5);
    state = jumpKikkiRunner(state);
    while (state.objects.length > 0) {
      state = advanceKikkiRunner(state, 50, () => 0.5);
    }

    expect(state.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
    expect(state.jumpsUsed).toBeLessThanOrEqual(2);
  });

  it('falls below the ground before ending when the runner reaches a cliff', () => {
    const state: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      objects: [
        {
          id: 1,
          kind: 'cliff',
          x: KIKKI_RUNNER_PLAYER_X,
          height: 0,
          rotationDeg: 0,
        },
      ],
    };

    const fallen = advanceKikkiRunner(state, 50, () => 0.5);

    expect(fallen.status).toBe('falling');
    expect(fallen.finishReason).toBe('cliff');
    expect(fallen.lives).toBe(0);
    expect(fallen.objects).toHaveLength(1);

    const halfwayDown = advanceKikkiRunner(fallen, 400, () => 0.5);
    expect(halfwayDown.status).toBe('falling');
    expect(halfwayDown.playerHeight).toBeLessThan(0);
    expect(halfwayDown.objects).toHaveLength(1);

    const gameOver = advanceKikkiRunner(halfwayDown, 350, () => 0.5);
    expect(gameOver.status).toBe('finished');
    expect(gameOver.playerHeight).toBeLessThan(-0.3);
    expect(gameOver.objects).toEqual([]);
  });

  it('waits until the runner body enters the cliff instead of falling on edge contact', () => {
    const touchingEdge: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      spawnElapsedMs: -100_000,
      objects: [
        {
          id: 1,
          kind: 'cliff',
          x: KIKKI_RUNNER_PLAYER_X + KIKKI_RUNNER_CLIFF_HALF_WIDTH + 0.04,
          height: 0,
          rotationDeg: 0,
        },
      ],
    };

    const partlyOverGap = advanceKikkiRunner(touchingEdge, 50, () => 0.5);
    expect(partlyOverGap.status).toBe('playing');

    let bodyInsideGap = partlyOverGap;
    while (bodyInsideGap.status === 'playing') {
      bodyInsideGap = advanceKikkiRunner(bodyInsideGap, 50, () => 0.5);
    }
    expect(bodyInsideGap.status).toBe('falling');
    expect(bodyInsideGap.finishReason).toBe('cliff');
  });

  it('keeps an offscreen cliff alive until its trailing broken-road cap clears', () => {
    const cliff: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      spawnElapsedMs: -100_000,
      playerHeight: 0.2,
      objects: [
        {
          id: 1,
          kind: 'cliff',
          x: -0.1,
          height: 0,
          rotationDeg: 0,
        },
      ],
    };

    const capStillVisible = advanceKikkiRunner(cliff, 50, () => 0.5);
    expect(capStillVisible.objects).toHaveLength(1);

    const capCleared = advanceKikkiRunner(
      {
        ...capStillVisible,
        objects: [{ ...capStillVisible.objects[0]!, x: -0.51 }],
      },
      50,
      () => 0.5,
    );
    expect(capCleared.objects).toEqual([]);
  });

  it('can clear a cliff with one jump', () => {
    let state: KikkiRunnerState = {
      ...createKikkiRunnerState(),
      status: 'playing',
      spawnElapsedMs: -100_000,
      objects: [
        {
          id: 1,
          kind: 'cliff',
          x: 0.4,
          height: 0,
          rotationDeg: 0,
        },
      ],
    };

    state = jumpKikkiRunner(state);
    while (state.objects.length > 0) {
      state = advanceKikkiRunner(state, 50, () => 0.5);
    }

    expect(state.status).toBe('playing');
    expect(state.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
  });

  it('caps even an all-banana minute at the server score limit', () => {
    let state = startKikkiRunner(() => 0.5);

    while (state.status === 'playing') {
      state = advanceKikkiRunner(state, 50, () => 0.5);
    }

    expect(KIKKI_RUNNER_MAX_SCORE).toBe(200);
    expect(state.score).toBe(KIKKI_RUNNER_MAX_SCORE);
  });

  it('accelerates sharply near the end of the minute', () => {
    const base = {
      ...createKikkiRunnerState(),
      status: 'playing' as const,
      spawnElapsedMs: -100_000,
    };
    const early = advanceKikkiRunner(base, 50, () => 0.5);
    const late = advanceKikkiRunner(
      { ...base, elapsedMs: KIKKI_RUNNER_DURATION_MS - 100 },
      50,
      () => 0.5,
    );

    expect(late.worldOffset).toBeGreaterThan(early.worldOffset * 3.5);
  });

  it('makes the speed increase noticeable within the first quarter', () => {
    const base = {
      ...createKikkiRunnerState(),
      status: 'playing' as const,
      spawnElapsedMs: -100_000,
    };
    const opening = advanceKikkiRunner(base, 50, () => 0.5);
    const firstQuarter = advanceKikkiRunner(
      { ...base, elapsedMs: 15_000 },
      50,
      () => 0.5,
    );

    expect(firstQuarter.worldOffset).toBeGreaterThan(
      opening.worldOffset * 1.35,
    );
  });

  it('finishes after sixty seconds and reports progress', () => {
    const finished = advanceKikkiRunner(
      { ...startKikkiRunner(() => 0.5), spawnElapsedMs: -100_000 },
      KIKKI_RUNNER_DURATION_MS,
      () => 0.5,
    );

    expect(finished.status).toBe('finished');
    expect(finished.finishReason).toBe('time_up');
    expect(finished.distanceM).toBe(600);
    expect(finished.objects).toEqual([]);
    expect(kikkiRunnerSecondsLeft(finished)).toBe(0);
    expect(kikkiRunnerProgress(finished)).toBe(1);
  });
});
