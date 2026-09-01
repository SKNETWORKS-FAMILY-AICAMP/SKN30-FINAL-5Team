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

/**
 * Insert one item at a new index while preserving the relative order of every
 * other item. For example, moving index 2 to 0 turns [1, 2, 3] into [3, 1, 2].
 */
export function moveArrayItem<T>(
  source: readonly T[],
  from: number,
  to: number,
): T[] {
  const items = Array.from(source);
  if (
    from < 0 ||
    from >= items.length ||
    to < 0 ||
    to >= items.length ||
    from === to
  ) {
    return items;
  }

  const moved = items[from]!;
  items.splice(from, 1);
  items.splice(to, 0, moved);
  return items;
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

  const reorderedItems = moveArrayItem(items, from, to);

  return {
    ...plan,
    items: reorderedItems.map((item, index) => ({
      ...item,
      sequence: index + 1,
    })),
  };
}
