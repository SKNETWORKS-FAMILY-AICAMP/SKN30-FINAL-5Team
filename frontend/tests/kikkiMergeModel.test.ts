import { describe, expect, it, jest } from '@jest/globals';

import {
  KIKKI_MERGE_DANGER_CONTACT_GRACE,
  KIKKI_MERGE_DANGER_Y,
  KIKKI_MERGE_MAX_SCORE,
  KIKKI_MERGE_POINTS_PER_MERGE,
  addKikkiMergeScore,
  clampKikkiDropX,
  createKikkiMergeRound,
  finishKikkiMergeFromOverflow,
  getKikkiMergeCreatedStageCount,
  isKikkiMergeDangerContact,
  nextKikkiMergeTier,
  startKikkiMergeRound,
} from '../src/features/kikkiMerge/kikkiMergeModel';
import {
  getKikkiMergeVelocity,
  KikkiMergePhysics,
} from '../src/features/kikkiMerge/kikkiMergePhysics';

describe('Kkikki merge rules', () => {
  it('starts without a time-based finish', () => {
    const started = startKikkiMergeRound();

    expect(started.status).toBe('playing');
    expect(started.finishReason).toBeNull();
  });

  it('adds exactly one point for every merge regardless of its result tier', () => {
    const round = startKikkiMergeRound();
    const afterSmallMerge = addKikkiMergeScore(round, 1);
    const afterLargestMerge = addKikkiMergeScore(afterSmallMerge, 10);

    expect(afterSmallMerge.score).toBe(KIKKI_MERGE_POINTS_PER_MERGE);
    expect(afterLargestMerge.score).toBe(KIKKI_MERGE_POINTS_PER_MERGE * 2);
    expect(afterLargestMerge.mergeCount).toBe(2);
  });

  it('tracks stage 9 through 11 creations independently and cumulatively', () => {
    let round = startKikkiMergeRound();
    round = addKikkiMergeScore(round, 8);
    round = addKikkiMergeScore(round, 9);
    round = addKikkiMergeScore(round, 9);
    round = addKikkiMergeScore(round, 10);

    expect(getKikkiMergeCreatedStageCount(round, 9)).toBe(1);
    expect(getKikkiMergeCreatedStageCount(round, 10)).toBe(2);
    expect(getKikkiMergeCreatedStageCount(round, 11)).toBe(1);
    expect(round.score).toBe(4);
    expect(round.mergeCount).toBe(4);
  });

  it('caps the count to the backend contract maximum', () => {
    let round = startKikkiMergeRound();
    for (let index = 0; index < KIKKI_MERGE_MAX_SCORE + 10; index += 1) {
      round = addKikkiMergeScore(round, 10);
    }

    expect(round.score).toBe(KIKKI_MERGE_MAX_SCORE);
    expect(round.mergeCount).toBe(KIKKI_MERGE_MAX_SCORE + 10);
  });

  it('selects only drop-queue tiers and clamps each face inside the walls', () => {
    expect(nextKikkiMergeTier(() => 0)).toBe(0);
    expect(nextKikkiMergeTier(() => 0.25)).toBe(1);
    expect(nextKikkiMergeTier(() => 0.55)).toBe(2);
    expect(nextKikkiMergeTier(() => 0.85)).toBe(3);
    expect(clampKikkiDropX(-100, 0)).toBeGreaterThan(0);
    expect(clampKikkiDropX(999, 3)).toBeLessThan(360);
  });

  it('finishes only an active round when the stack overflows', () => {
    const ready = createKikkiMergeRound();
    expect(finishKikkiMergeFromOverflow(ready)).toBe(ready);
    expect(finishKikkiMergeFromOverflow(startKikkiMergeRound())).toMatchObject({
      status: 'finished',
      finishReason: 'overflow',
    });
  });

  it('counts an armed orb touching the danger line as overflow contact', () => {
    const contactY = KIKKI_MERGE_DANGER_Y + KIKKI_MERGE_DANGER_CONTACT_GRACE;
    expect(isKikkiMergeDangerContact(contactY, true)).toBe(true);
    expect(isKikkiMergeDangerContact(contactY + 0.01, true)).toBe(false);
    expect(isKikkiMergeDangerContact(KIKKI_MERGE_DANGER_Y, false)).toBe(false);
  });

  it('merges two matching physics bodies into the next tier', () => {
    const onMerge = jest.fn();
    const physics = new KikkiMergePhysics(onMerge, jest.fn());

    expect(physics.drop(0, 180)).toBe(true);
    expect(physics.drop(0, 180)).toBe(true);
    physics.step(16.67);

    expect(onMerge).toHaveBeenCalledWith(1);
    expect(physics.snapshot()).toHaveLength(1);
    expect(physics.snapshot()[0]?.tier).toBe(1);
    expect(physics.snapshot()[0]?.dangerArmed).toBe(true);
    physics.stop();
  });

  it('arms a fresh drop for danger checks as soon as it hits the stack or floor', () => {
    const physics = new KikkiMergePhysics(jest.fn(), jest.fn());

    expect(physics.drop(0, 180)).toBe(true);
    expect(physics.snapshot()[0]?.dangerArmed).toBe(false);

    for (let frame = 0; frame < 240; frame += 1) physics.step(16.67);

    expect(physics.snapshot()[0]?.dangerArmed).toBe(true);
    physics.stop();
  });

  it('merges matching bodies across a small visual contact gap', () => {
    const onMerge = jest.fn();
    const physics = new KikkiMergePhysics(onMerge, jest.fn());

    expect(physics.drop(0, 160)).toBe(true);
    expect(physics.drop(0, 201)).toBe(true);
    physics.step(16.67);

    expect(onMerge).toHaveBeenCalledWith(1);
    expect(physics.snapshot()).toHaveLength(1);
    physics.stop();
  });

  it('removes upward launch velocity and caps sideways merge momentum', () => {
    expect(getKikkiMergeVelocity({ x: -5, y: -8 }, { x: -3, y: -4 })).toEqual({
      x: -1.25,
      y: 0,
    });
    expect(getKikkiMergeVelocity({ x: 0, y: 8 }, { x: 1, y: 4 })).toEqual({
      x: 0.5,
      y: 2.5,
    });
  });
});
