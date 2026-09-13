import { describe, expect, it } from '@jest/globals';

import {
  BANANA_CATCH_DURATION_MS,
  BANANA_CATCH_TICK_MS,
  BANANA_HALF_WIDTH,
  BANANA_ROUND_PACE_MAX,
  BANANA_ROUND_PACE_MIN,
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
    expect(state.roundPace).toBeCloseTo(1.0625);
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

  it('chooses a bounded pace once when each round starts', () => {
    let randomCalls = 0;
    const slow = startBananaCatch(() => {
      randomCalls += 1;
      return 0;
    });
    const fast = startBananaCatch(() => 1);

    expect(slow.roundPace).toBe(BANANA_ROUND_PACE_MIN);
    expect(fast.roundPace).toBe(BANANA_ROUND_PACE_MAX);
    expect(randomCalls).toBe(4);
  });

  it('keeps the catcher inside the play area', () => {
    const state = createBananaCatchState();

    expect(moveBananaCatcher(state, -1).playerX).toBe(PLAYER_HALF_WIDTH);
    expect(moveBananaCatcher(state, 2).playerX).toBe(1 - PLAYER_HALF_WIDTH);
    expect(moveBananaCatcher(state, -1, 0.15).playerX).toBe(0.15);
    expect(moveBananaCatcher(state, 2, 0.15).playerX).toBe(0.85);
  });

  it('keeps spawned bananas inside the supplied visual edge', () => {
    expect(startBananaCatch(() => 0).bananas[0]?.x).toBe(BANANA_HALF_WIDTH);
    expect(startBananaCatch(() => 0, 0.055).bananas[0]?.x).toBe(0.055);
    expect(startBananaCatch(() => 1, 0.055).bananas[0]?.x).toBe(0.945);
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

  it('varies a flawless score with the pace selected for the round', () => {
    const playRound = (paceRandom: number) => {
      let firstCall = true;
      const random = () => {
        if (firstCall) {
          firstCall = false;
          return paceRandom;
        }
        return 0.5;
      };
      let state = startBananaCatch(random);

      while (state.status === 'playing') {
        state = advanceBananaCatch(state, BANANA_CATCH_TICK_MS, random);
      }
      return state.score;
    };

    const slowScore = playRound(0);
    const fastScore = playRound(1);

    expect(slowScore).toBeLessThan(fastScore);
    expect(fastScore).not.toBe(41);
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

  it('catches a banana at the wall when the catcher is at the same edge', () => {
    const state = {
      ...startBananaCatch(() => 0, 0.055),
      playerX: 0.153,
      bananas: [
        {
          id: 1,
          x: 0.055,
          y: 0.74,
          rotationDeg: 0,
          rotationSpeedDegPerSecond: 0,
        },
      ],
    };
    const caught = advanceBananaCatch(state, 100, () => 0, 0.75, 0.12, 0.055);

    expect(caught.score).toBe(1);
    expect(caught.bananas).toEqual([]);
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
