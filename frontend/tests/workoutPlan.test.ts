import type { WorkoutPlan } from '../src/api/types';
import {
  moveArrayItem,
  moveWorkoutPlanItem,
  orderedWorkoutPlanItems,
} from '../src/api/workoutPlan';

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
});
