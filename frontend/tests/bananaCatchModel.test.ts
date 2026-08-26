import { describe, expect, it } from '@jest/globals';

import {
  BANANA_CATCH_DURATION_MS,
  BANANA_SPAWN_INTERVAL_MS,
  PLAYER_HALF_WIDTH,
  advanceBananaCatch,
  bananaCatchSecondsLeft,
  createBananaCatchState,
  moveBananaCatcher,
  startBananaCatch,
} from '../src/features/bananaCatch/bananaCatchModel';

describe('banana catch rules', () => {
  it('starts with one reproducibly placed banana', () => {
    const state = startBananaCatch(() => 0.25);

    expect(state.status).toBe('playing');
    expect(state.bananas).toEqual([{ id: 1, x: 0.25, y: -0.08 }]);
  });

  it('keeps the catcher inside the play area', () => {
    const state = createBananaCatchState();

    expect(moveBananaCatcher(state, -1).playerX).toBe(PLAYER_HALF_WIDTH);
    expect(moveBananaCatcher(state, 2).playerX).toBe(1 - PLAYER_HALF_WIDTH);
  });

  it('spawns bananas on a fixed cadence', () => {
    const started = startBananaCatch(() => 0.5);
    const advanced = advanceBananaCatch(
      started,
      BANANA_SPAWN_INTERVAL_MS * 2,
      () => 0.75,
    );

    expect(advanced.bananas.map(({ id, x }) => ({ id, x }))).toEqual([
      { id: 1, x: 0.5 },
      { id: 2, x: 0.75 },
      { id: 3, x: 0.75 },
    ]);
  });

  it('scores a banana that crosses the catcher', () => {
    const state = {
      ...startBananaCatch(() => 0.5),
      bananas: [{ id: 1, x: 0.5, y: 0.81 }],
    };
    const caught = advanceBananaCatch(state, 100, () => 0.1);

    expect(caught.score).toBe(1);
    expect(caught.bananas).toEqual([]);
  });

  it('does not penalize a missed banana', () => {
    const state = {
      ...startBananaCatch(() => 0.1),
      playerX: 0.8,
      bananas: [{ id: 1, x: 0.1, y: 0.99 }],
    };
    const missed = advanceBananaCatch(state, 100, () => 0.1);

    expect(missed.score).toBe(0);
    expect(missed.bananas).toEqual([]);
  });

  it('finishes at thirty seconds and clears falling bananas', () => {
    const finished = advanceBananaCatch(
      startBananaCatch(() => 0.5),
      BANANA_CATCH_DURATION_MS,
      () => 0.5,
    );

    expect(finished.status).toBe('finished');
    expect(finished.bananas).toEqual([]);
    expect(bananaCatchSecondsLeft(finished)).toBe(0);
  });
});
