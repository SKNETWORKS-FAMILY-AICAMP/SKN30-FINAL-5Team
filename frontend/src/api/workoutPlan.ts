import type {
  DecisionPlanEditRequest,
  PlanItemPrescriptionEdit,
  PlanPhaseCode,
  WorkoutPlan,
  WorkoutPlanItem,
} from './types';

/** Plans written before the phase field existed were all MAIN. */
export function planItemPhaseCode(item: WorkoutPlanItem): PlanPhaseCode {
  return item.phase_code ?? 'MAIN';
}

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

/**
 * Move one exercise and renumber the complete plan as one atomic value.
 *
 * A move that crosses a `WARMUP`/`MAIN`/`COOLDOWN` boundary is refused rather
 * than sent to the server, which rejects it as `PHASE_BOUNDARY_VIOLATION`
 * (ADR-0018 D5).
 */
export function moveWorkoutPlanItem(
  plan: WorkoutPlan,
  from: number,
  to: number,
): WorkoutPlan {
  const items = orderedWorkoutPlanItems(plan.items);
  const source = items[from];
  const target = items[to];
  if (
    source === undefined ||
    target === undefined ||
    from === to ||
    planItemPhaseCode(source) !== planItemPhaseCode(target)
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

/**
 * Apply the user's set and repetition edits to the plan the whole app reads,
 * so the routine card and the running workout cannot disagree about what was
 * prescribed. Edits for unknown items are ignored.
 */
export function applyPlanItemPrescriptions(
  plan: WorkoutPlan,
  edits: readonly PlanItemPrescriptionEdit[],
): WorkoutPlan {
  if (edits.length === 0) {
    return plan;
  }
  const byId = new Map(edits.map((edit) => [edit.plan_item_id, edit]));
  let changed = false;
  const items = plan.items.map((item) => {
    const edit = byId.get(item.plan_item_id);
    if (
      edit === undefined ||
      (edit.sets === item.sets && edit.reps === item.reps)
    ) {
      return item;
    }
    changed = true;
    return { ...item, sets: edit.sets, reps: edit.reps };
  });
  return changed ? { ...plan, items } : plan;
}

/** The full resulting plan, as the user-edit contract expects it. */
export function planEditRequest(plan: WorkoutPlan): DecisionPlanEditRequest {
  const items = orderedWorkoutPlanItems(plan.items);
  return {
    expected_plan_id: plan.plan_id,
    item_order: items.map((item) => item.plan_item_id),
    item_prescriptions: items.map((item) => ({
      plan_item_id: item.plan_item_id,
      sets: item.sets,
      reps: item.reps,
    })),
  };
}
