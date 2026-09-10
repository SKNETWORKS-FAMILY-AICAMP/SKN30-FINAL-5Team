import type { PlanPhaseCode, RoutineDay, WorkoutPlan } from '../src/api/types';
import {
  applyPlanItemPrescriptions,
  moveArrayItem,
  moveWorkoutPlanItem,
  orderedWorkoutPlanItems,
  planItemOrderRequest,
  planItemWorkSecondsPerSet,
  routineTitleFromDay,
  routineTitleFromPlan,
  workoutPlanRevision,
} from '../src/api/workoutPlan';

function phasedPlan(phases: readonly PlanPhaseCode[]): WorkoutPlan {
  const base = plan();
  return {
    ...base,
    items: phases.map((phase_code, index) => ({
      ...base.items[0]!,
      plan_item_id: `item-${index + 1}`,
      sequence: index + 1,
      phase_code,
    })),
  };
}

function plan(): WorkoutPlan {
  return {
    plan_id: 'plan-1',
    action_code: 'KEEP',
    training_type_code: 'STRENGTH',
    body_focus_code: null,
    requested_duration_minutes: 30,
    estimated_duration_seconds: 1800,
    estimated_calories_burned: null,
    setup_seconds: 0,
    warmup_seconds: 60,
    cooldown_seconds: 60,
    items: [2, 1, 3].map((sequence) => ({
      plan_item_id: `item-${sequence}`,
      exercise_id: `exercise-${sequence}`,
      exercise_name: `운동 ${sequence}`,
      sequence,
      tier_code: 'CORE',
      sets: 3,
      reps: 10,
      work_seconds: 30,
      rest_seconds: 30,
      transition_seconds: 10,
      estimated_item_seconds: 180,
      instruction_available: false,
      mascot_animation_asset_key: null,
      replacement_of_exercise_id: null,
    })),
  };
}

describe('shared workout plan order', () => {
  it('inserts only the dragged item and shifts the intervening items', () => {
    expect(moveArrayItem([1, 2, 3], 2, 0)).toEqual([3, 1, 2]);
    expect(moveArrayItem([1, 2, 3], 0, 2)).toEqual([2, 3, 1]);
  });

  it('normalizes every consumer by sequence', () => {
    expect(
      orderedWorkoutPlanItems(plan().items).map((item) => item.plan_item_id),
    ).toEqual(['item-1', 'item-2', 'item-3']);
  });

  it('moves an item and rewrites a contiguous sequence without changing IDs', () => {
    const reordered = moveWorkoutPlanItem(plan(), 0, 2);

    expect(
      reordered.items.map((item) => [item.plan_item_id, item.sequence]),
    ).toEqual([
      ['item-2', 1],
      ['item-3', 2],
      ['item-1', 3],
    ]);
  });

  it('moves the last plan item to the front without reversing the others', () => {
    const reordered = moveWorkoutPlanItem(plan(), 2, 0);

    expect(reordered.items.map((item) => item.plan_item_id)).toEqual([
      'item-3',
      'item-1',
      'item-2',
    ]);
  });

  it('refuses a move that crosses a phase boundary', () => {
    const source = phasedPlan(['WARMUP', 'MAIN', 'COOLDOWN']);

    expect(moveWorkoutPlanItem(source, 0, 1)).toBe(source);
    expect(moveWorkoutPlanItem(source, 2, 0)).toBe(source);
  });

  it('moves inside one phase', () => {
    const source = phasedPlan(['WARMUP', 'MAIN', 'MAIN']);

    expect(
      moveWorkoutPlanItem(source, 2, 1).items.map((item) => [
        item.plan_item_id,
        item.sequence,
      ]),
    ).toEqual([
      ['item-1', 1],
      ['item-3', 2],
      ['item-2', 3],
    ]);
  });
});

describe('server-owned routine names', () => {
  it('uses the server name for a compiled plan', () => {
    expect(
      routineTitleFromPlan({
        ...plan(),
        routine_name: '전신 기초 근력',
      }),
    ).toBe('전신 기초 근력');
  });

  it('keeps the legacy title when a plan has no server name', () => {
    expect(routineTitleFromPlan(plan())).toBe('근력 루틴');
  });

  it.each([
    ['MOBILITY', '스트레칭 루틴'],
    ['CARDIO', '유산소 루틴'],
  ])(
    'states a %s plan once when it is both the focus and the training type',
    (code, expected) => {
      expect(
        routineTitleFromPlan({
          ...plan(),
          body_focus_code: code,
          training_type_code: code,
          routine_name: null,
        }),
      ).toBe(expected);
    },
  );

  it('still names the focus when it differs from the training type', () => {
    expect(
      routineTitleFromPlan({
        ...plan(),
        body_focus_code: 'BACK',
        training_type_code: 'STRENGTH',
        routine_name: null,
      }),
    ).toBe('등 근력 루틴');
  });

  it('uses the same rule for a base-routine day', () => {
    const day: RoutineDay = {
      id: 'day-1',
      sequence: 1,
      title: '기존 제목',
      training_type_code: 'STRENGTH',
      body_focus_code: 'FULL_BODY',
      routine_name: '전신 근력 시작하기',
      requested_duration_minutes: 30,
      estimated_duration_seconds: 1800,
      estimated_calories_burned: null,
      items: [],
    };

    expect(routineTitleFromDay(day)).toBe('전신 근력 시작하기');
  });
});

describe('user prescription edits', () => {
  it('applies set and repetition edits and leaves other items alone', () => {
    const edited = applyPlanItemPrescriptions(plan(), [
      { plan_item_id: 'item-1', sets: 5, reps: null },
    ]);

    expect(
      edited.items.map((item) => [item.plan_item_id, item.sets, item.reps]),
    ).toEqual([
      ['item-2', 3, 10],
      ['item-1', 5, null],
      ['item-3', 3, 10],
    ]);
  });

  it('returns the same plan when nothing changes', () => {
    const source = plan();

    expect(applyPlanItemPrescriptions(source, [])).toBe(source);
    expect(
      applyPlanItemPrescriptions(source, [
        { plan_item_id: 'item-1', sets: 3, reps: 10 },
        { plan_item_id: 'unknown-item', sets: 9, reps: 9 },
      ]),
    ).toBe(source);
  });

  it('builds the revision-checked order from incomplete items only', () => {
    const source = { ...plan(), plan_revision: 4 };
    expect(planItemOrderRequest(source, ['item-2'])).toEqual({
      expected_plan_id: 'plan-1',
      expected_plan_revision: 4,
      ordered_plan_item_ids: ['item-1', 'item-3'],
    });
  });

  it('treats a historical plan without a revision as revision zero', () => {
    expect(workoutPlanRevision(plan())).toBe(0);
  });
});

describe('planItemWorkSecondsPerSet', () => {
  const base = plan().items[0]!;

  it('uses the per-set figure the server sends', () => {
    expect(
      planItemWorkSecondsPerSet({
        ...base,
        sets: 2,
        work_seconds: 60,
        work_seconds_per_set: 30,
      }),
    ).toBe(30);
  });

  it('divides the item total for a plan stored before the field existed', () => {
    // `work_seconds` is the total across sets. Reading it directly showed a
    // 2 x 30s block as "2세트 × 1분", and it is the number a duration edit
    // replaces, so it has to be the per-set one.
    const { work_seconds_per_set: _omitted, ...withoutPerSet } = {
      ...base,
      sets: 2,
      work_seconds: 60,
      work_seconds_per_set: null,
    };

    expect(planItemWorkSecondsPerSet(withoutPerSet)).toBe(30);
  });

  it('does not divide by zero sets', () => {
    expect(
      planItemWorkSecondsPerSet({
        ...base,
        sets: 0,
        work_seconds: 60,
        work_seconds_per_set: null,
      }),
    ).toBe(0);
  });
});

describe('applyPlanItemPrescriptions with a duration edit', () => {
  it('rewrites the per-set seconds and keeps the item total consistent', () => {
    const source = plan();
    const durationPlan: WorkoutPlan = {
      ...source,
      items: [
        {
          ...source.items[0]!,
          plan_item_id: 'timed',
          sets: 2,
          reps: null,
          work_seconds: 60,
          work_seconds_per_set: 30,
        },
      ],
    };

    const revised = applyPlanItemPrescriptions(durationPlan, [
      {
        plan_item_id: 'timed',
        sets: 2,
        reps: null,
        workSecondsPerSet: 45,
      },
    ]);

    expect(revised.items[0]!.work_seconds_per_set).toBe(45);
    expect(revised.items[0]!.work_seconds).toBe(90);
  });
});
