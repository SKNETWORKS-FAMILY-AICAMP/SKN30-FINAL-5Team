import { describe, expect, it } from '@jest/globals';

import {
  BANANA_CATCH_DURATION_MS,
  BANANA_SPAWN_INTERVAL_MS,
  PLAYER_HALF_WIDTH,
  advanceBananaCatch,
  bananaBasketStage,
  bananaCatchSecondsLeft,
  createBananaCatchState,
  moveBananaCatcher,
  startBananaCatch,
} from '../src/features/bananaCatch/bananaCatchModel';

describe('banana catch rules', () => {
  it('starts with one reproducibly placed banana', () => {
    const state = startBananaCatch(() => 0.25);

    expect(state.status).toBe('playing');
    expect(state.bananas).toEqual([
      {
        id: 1,
        x: 0.25,
        y: -0.08,
        rotationDeg: -17.5,
        rotationSpeedDegPerSecond: -17.5,
      },
    ]);
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

  it('gives falling bananas a varied angle and a gentle rotation', () => {
    const started = startBananaCatch(() => 0.75);
    const advanced = advanceBananaCatch(started, 1_000, () => 0.5);

    expect(started.bananas[0]).toMatchObject({
      rotationDeg: 17.5,
      rotationSpeedDegPerSecond: 17.5,
    });
    expect(advanced.bananas[0]?.rotationDeg).toBe(35);
  });

  it('changes the collecting basket stage every ten bananas', () => {
    expect(bananaBasketStage(0)).toBe('empty');
    expect(bananaBasketStage(9)).toBe('empty');
    expect(bananaBasketStage(10)).toBe('medium');
    expect(bananaBasketStage(19)).toBe('medium');
    expect(bananaBasketStage(20)).toBe('full');
    expect(bananaBasketStage(42)).toBe('full');
  });

  it('scores a banana that crosses the catcher', () => {
    const state = {
      ...startBananaCatch(() => 0.5),
      bananas: [
        {
          id: 1,
          x: 0.5,
          y: 0.74,
          rotationDeg: 0,
          rotationSpeedDegPerSecond: 20,
        },
      ],
    };
    const caught = advanceBananaCatch(state, 100, () => 0.1);

    expect(caught.score).toBe(1);
    expect(caught.bananas).toEqual([]);
  });

  it('scores exactly when the banana reaches the supplied basket line', () => {
    const state = {
      ...startBananaCatch(() => 0.5),
      bananas: [
        {
          id: 1,
          x: 0.5,
          y: 0.58,
          rotationDeg: 0,
          rotationSpeedDegPerSecond: 0,
        },
      ],
    };
    const aboveBasket = advanceBananaCatch(state, 50, () => 0.5, 0.6);
    const touchingBasket = advanceBananaCatch(aboveBasket, 50, () => 0.5, 0.6);

    expect(aboveBasket.score).toBe(0);
    expect(touchingBasket.score).toBe(1);
    expect(touchingBasket.bananas).toEqual([]);
  });

  it('uses the supplied basket width for horizontal contact', () => {
    const state = {
      ...startBananaCatch(() => 0.5),
      bananas: [
        {
          id: 1,
          x: 0.61,
          y: 0.74,
          rotationDeg: 0,
          rotationSpeedDegPerSecond: 0,
        },
      ],
    };
    const missedBasket = advanceBananaCatch(state, 100, () => 0.5, 0.75, 0.1);

    expect(missedBasket.score).toBe(0);
  });

  it('does not penalize a missed banana', () => {
    const state = {
      ...startBananaCatch(() => 0.1),
      playerX: 0.8,
      bananas: [
        {
          id: 1,
          x: 0.1,
          y: 0.99,
          rotationDeg: 0,
          rotationSpeedDegPerSecond: -20,
        },
      ],
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
