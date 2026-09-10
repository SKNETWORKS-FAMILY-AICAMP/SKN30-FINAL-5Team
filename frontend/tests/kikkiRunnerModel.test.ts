import { describe, expect, it } from '@jest/globals';

import {
  KIKKI_RUNNER_DURATION_MS,
  KIKKI_RUNNER_MAX_LIVES,
  KIKKI_RUNNER_PLAYER_X,
  advanceKikkiRunner,
  createKikkiRunnerState,
  jumpKikkiRunner,
  kikkiRunnerProgress,
  kikkiRunnerSecondsLeft,
  startKikkiRunner,
  type KikkiRunnerState,
} from '../src/features/kikkiRunner/kikkiRunnerModel';

describe('Kkikki runner rules', () => {
  it('starts with a banana approaching from the right', () => {
    const state = startKikkiRunner(() => 0.5);

    expect(state.status).toBe('playing');
    expect(state.lives).toBe(KIKKI_RUNNER_MAX_LIVES);
    expect(state.objects).toEqual([
      {
        id: 1,
        kind: 'banana',
        x: 1.08,
        height: 0.065,
        rotationDeg: 0,
      },
    ]);
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
      800,
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

  it('finishes after thirty seconds and reports progress', () => {
    const finished = advanceKikkiRunner(
      { ...startKikkiRunner(() => 0.5), spawnElapsedMs: -100_000 },
      KIKKI_RUNNER_DURATION_MS,
      () => 0.5,
    );

    expect(finished.status).toBe('finished');
    expect(finished.distanceM).toBe(300);
    expect(finished.objects).toEqual([]);
    expect(kikkiRunnerSecondsLeft(finished)).toBe(0);
    expect(kikkiRunnerProgress(finished)).toBe(1);
  });
});
