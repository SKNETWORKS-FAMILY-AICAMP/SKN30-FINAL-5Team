import {
  Bodies,
  Body,
  Composite,
  Engine,
  Events,
  Sleeping,
  type IEventCollision,
} from 'matter-js';

import {
  KIKKI_MERGE_CONTACT_GRACE,
  KIKKI_MERGE_DANGER_HOLD_MS,
  KIKKI_MERGE_DROP_Y,
  KIKKI_MERGE_TIERS,
  KIKKI_MERGE_WORLD_HEIGHT,
  KIKKI_MERGE_WORLD_WIDTH,
  clampKikkiDropX,
  isKikkiMergeDangerContact,
} from './kikkiMergeModel';

export type KikkiMergeOrb = {
  id: number;
  tier: number;
  x: number;
  y: number;
  angle: number;
  dangerArmed: boolean;
};

type OrbRecord = {
  body: Body;
  tier: number;
  dangerArmed: boolean;
};

export class KikkiMergePhysics {
  private readonly engine = Engine.create({ enableSleeping: true });
  private readonly orbs = new Map<number, OrbRecord>();
  private dangerElapsedMs = 0;
  private stopped = false;

  constructor(
    private readonly onMerge: (resultTier: number) => void,
    private readonly onOverflow: () => void,
  ) {
    this.engine.gravity.y = 1.08;
    const wallOptions = { isStatic: true, friction: 0.08, restitution: 0.02 };
    Composite.add(this.engine.world, [
      Bodies.rectangle(-18, KIKKI_MERGE_WORLD_HEIGHT / 2, 40, 700, wallOptions),
      Bodies.rectangle(
        KIKKI_MERGE_WORLD_WIDTH + 18,
        KIKKI_MERGE_WORLD_HEIGHT / 2,
        40,
        700,
        wallOptions,
      ),
      Bodies.rectangle(
        KIKKI_MERGE_WORLD_WIDTH / 2,
        KIKKI_MERGE_WORLD_HEIGHT + 18,
        440,
        40,
        wallOptions,
      ),
    ]);
    Events.on(this.engine, 'collisionStart', this.armCollidingOrbs);
  }

  drop(tier: number, requestedX: number): boolean {
    if (
      this.stopped ||
      this.orbs.size >= 56 ||
      KIKKI_MERGE_TIERS[tier] === undefined
    )
      return false;
    this.addOrb(tier, clampKikkiDropX(requestedX, tier), KIKKI_MERGE_DROP_Y);
    return true;
  }

  step(deltaMs: number): void {
    if (this.stopped) return;
    let remainingMs = Math.min(50, Math.max(0, deltaMs));
    while (remainingMs > 0) {
      const fixedStepMs = Math.min(1000 / 60, remainingMs);
      Engine.update(this.engine, fixedStepMs);
      this.mergeNearbyPairs();
      this.settleFloorDrift();
      remainingMs -= fixedStepMs;
    }

    let overDangerLine = false;
    for (const orb of this.orbs.values()) {
      const radius = KIKKI_MERGE_TIERS[orb.tier]?.radius ?? 0;
      const orbTop = orb.body.position.y - radius;
      if (isKikkiMergeDangerContact(orbTop, orb.dangerArmed)) {
        overDangerLine = true;
      }
    }

    this.dangerElapsedMs = overDangerLine
      ? this.dangerElapsedMs + deltaMs
      : Math.max(0, this.dangerElapsedMs - deltaMs * 2);
    if (this.dangerElapsedMs >= KIKKI_MERGE_DANGER_HOLD_MS) {
      this.stopped = true;
      this.onOverflow();
    }
  }

  snapshot(): KikkiMergeOrb[] {
    return Array.from(this.orbs.values()).map(
      ({ body, dangerArmed, tier }) => ({
        id: body.id,
        tier,
        x: body.position.x,
        y: body.position.y,
        angle: body.angle,
        dangerArmed,
      }),
    );
  }

  dangerProgress(): number {
    return Math.min(1, this.dangerElapsedMs / KIKKI_MERGE_DANGER_HOLD_MS);
  }

  stop(): void {
    this.stopped = true;
    Events.off(this.engine, 'collisionStart', this.armCollidingOrbs);
    Composite.clear(this.engine.world, false, true);
    Engine.clear(this.engine);
    this.orbs.clear();
  }

  private addOrb(
    tier: number,
    x: number,
    y: number,
    dangerArmed = false,
  ): OrbRecord {
    const radius =
      KIKKI_MERGE_TIERS[tier]?.radius ?? KIKKI_MERGE_TIERS[0].radius;
    const body = Bodies.circle(x, y, radius, {
      label: `kikki-merge-${tier}`,
      restitution: 0.02,
      friction: 0.08,
      frictionStatic: 0.18,
      frictionAir: 0.008,
      density: 0.0012,
      slop: 0.35,
      sleepThreshold: 45,
    });
    const record = { body, tier, dangerArmed };
    this.orbs.set(body.id, record);
    Composite.add(this.engine.world, body);
    return record;
  }

  /** A fresh drop becomes part of the stack at its first physical contact. */
  private readonly armCollidingOrbs = (event: IEventCollision<Engine>) => {
    for (const pair of event.pairs) {
      const first = this.orbs.get(pair.bodyA.id);
      const second = this.orbs.get(pair.bodyB.id);
      if (first !== undefined) first.dangerArmed = true;
      if (second !== undefined) second.dangerArmed = true;
    }
  };

  private mergeNearbyPairs(): void {
    const candidates = Array.from(this.orbs.values()).sort(
      (first, second) => first.body.id - second.body.id,
    );
    const consumed = new Set<number>();
    for (let firstIndex = 0; firstIndex < candidates.length; firstIndex += 1) {
      const first = candidates[firstIndex];
      if (
        first === undefined ||
        consumed.has(first.body.id) ||
        first.tier >= KIKKI_MERGE_TIERS.length - 1
      )
        continue;

      for (
        let secondIndex = firstIndex + 1;
        secondIndex < candidates.length;
        secondIndex += 1
      ) {
        const second = candidates[secondIndex];
        if (
          second === undefined ||
          second.tier !== first.tier ||
          consumed.has(second.body.id) ||
          !areCloseEnoughToMerge(first, second)
        )
          continue;

        consumed.add(first.body.id);
        consumed.add(second.body.id);
        this.mergePair(first, second);
        break;
      }
    }

    if (consumed.size > 0) this.wakeAllOrbs();
  }

  private mergePair(first: OrbRecord, second: OrbRecord): void {
    const resultTier = first.tier + 1;
    const resultRadius = KIKKI_MERGE_TIERS[resultTier]?.radius ?? 0;
    const floorY = KIKKI_MERGE_WORLD_HEIGHT - 2 - resultRadius;
    const x = clampKikkiDropX(
      (first.body.position.x + second.body.position.x) / 2,
      resultTier,
    );
    const y = Math.min(
      floorY,
      (first.body.position.y + second.body.position.y) / 2,
    );
    const velocity = getKikkiMergeVelocity(
      first.body.velocity,
      second.body.velocity,
    );

    Composite.remove(this.engine.world, [first.body, second.body]);
    this.orbs.delete(first.body.id);
    this.orbs.delete(second.body.id);
    // Only freshly dropped bodies need time to enter the board. A merge result
    // is already part of the settled stack and must count at the danger line.
    const merged = this.addOrb(resultTier, x, y, true);
    Body.setVelocity(merged.body, velocity);
    Body.setAngularVelocity(merged.body, 0);
    this.onMerge(merged.tier);
  }

  /** Removing a supporting body does not wake sleeping Matter.js bodies. */
  private wakeAllOrbs(): void {
    for (const orb of this.orbs.values()) Sleeping.set(orb.body, false);
  }

  /** Suppress the tiny one-sided floor drift produced by the collision solver. */
  private settleFloorDrift(): void {
    const floorSurfaceY = KIKKI_MERGE_WORLD_HEIGHT - 2;
    for (const orb of this.orbs.values()) {
      const radius = KIKKI_MERGE_TIERS[orb.tier]?.radius ?? 0;
      const isOnFloor = floorSurfaceY - (orb.body.position.y + radius) < 1.5;
      if (isOnFloor && Math.abs(orb.body.velocity.x) < 0.12) {
        Body.setVelocity(orb.body, { x: 0, y: orb.body.velocity.y });
        Body.setAngularVelocity(orb.body, 0);
      }
    }
  }
}

function areCloseEnoughToMerge(first: OrbRecord, second: OrbRecord): boolean {
  const firstRadius = KIKKI_MERGE_TIERS[first.tier]?.radius ?? 0;
  const secondRadius = KIKKI_MERGE_TIERS[second.tier]?.radius ?? 0;
  const maximumDistance =
    firstRadius + secondRadius + KIKKI_MERGE_CONTACT_GRACE;
  const xDistance = first.body.position.x - second.body.position.x;
  const yDistance = first.body.position.y - second.body.position.y;
  return (
    xDistance * xDistance + yDistance * yDistance <=
    maximumDistance * maximumDistance
  );
}

export function getKikkiMergeVelocity(
  first: { x: number; y: number },
  second: { x: number; y: number },
): { x: number; y: number } {
  const averageX = (first.x + second.x) / 2;
  const averageY = (first.y + second.y) / 2;
  return {
    x: Math.max(-1.25, Math.min(1.25, averageX)),
    // Matter.js uses positive Y for downward motion. Never carry a launch
    // impulse upward into the larger merged body.
    y: Math.max(0, Math.min(2.5, averageY)),
  };
}
