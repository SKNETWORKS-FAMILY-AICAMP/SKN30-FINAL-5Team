import type { WorkoutPlan, WorkoutPlanItem } from './types';

/**
 * Keep every plan consumer on the same stable exercise order. The API's
 * sequence is authoritative even when a transport or fixture returns a
 * differently ordered array.
 */
export function orderedWorkoutPlanItems(
  items: readonly WorkoutPlanItem[],
): WorkoutPlanItem[] {
  return items
    .map((item, originalIndex) => ({ item, originalIndex }))
    .sort(
      (left, right) =>
        left.item.sequence - right.item.sequence ||
        left.originalIndex - right.originalIndex,
    )
    .map(({ item }) => item);
}

/** Move one exercise and renumber the complete plan as one atomic value. */
export function moveWorkoutPlanItem(
  plan: WorkoutPlan,
  from: number,
  to: number,
): WorkoutPlan {
  const items = orderedWorkoutPlanItems(plan.items);
  if (
    from < 0 ||
    from >= items.length ||
    to < 0 ||
    to >= items.length ||
    from === to
  ) {
    return plan;
  }

  const [moved] = items.splice(from, 1);
  if (moved === undefined) {
    return plan;
  }
  items.splice(to, 0, moved);

  return {
    ...plan,
    items: items.map((item, index) => ({ ...item, sequence: index + 1 })),
  };
}
