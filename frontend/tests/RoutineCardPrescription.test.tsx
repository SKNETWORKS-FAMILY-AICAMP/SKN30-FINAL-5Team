/**
 * Editing a duration-based block.
 *
 * The card offered one numeric field beside the set count for every item, so a
 * block measured in time had no field of its own. Its placeholder said 시간 and
 * its unit said 회, and whatever the user typed there was sent as `reps` -- which
 * the server refuses for an item with no repetitions. The plan edit failed with
 * "시간으로 수행하는 운동에는 반복 횟수를 지정할 수 없습니다." and the workout
 * could not be started.
 */

import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { RoutineCard } from '../src/features/home/HomeRoutineCard';
import type { HomeRoutineItem } from '../src/features/home/homeModel';

const REPETITION_ITEM: HomeRoutineItem = {
  id: 'item-1',
  name: '푸시업',
  sets: '3',
  reps: '10',
};

const DURATION_ITEM: HomeRoutineItem = {
  id: 'item-2',
  name: '플랭크',
  sets: '2',
  workSeconds: '30',
};

function renderCard(
  items: readonly HomeRoutineItem[],
  onChangePrescription = jest.fn(),
) {
  render(
    <RoutineCard
      completedItemIds={[]}
      currentPlanItemId={null}
      editDisabled={false}
      editing
      editLabel="저장하기"
      focus="전신"
      items={items}
      minutes="30"
      onChangePrescription={onChangePrescription}
      onOpenExerciseVariants={jest.fn()}
      painPart={null}
      pending={false}
      phase="READY"
      rerolling={false}
      rerolls={0}
    />,
  );
  return onChangePrescription;
}

describe('RoutineCard prescription editing', () => {
  it('gives a duration-based block a seconds field, not a repetition field', () => {
    renderCard([DURATION_ITEM]);

    expect(screen.getByLabelText('플랭크 세트당 시간(초)')).toBeOnTheScreen();
    expect(screen.queryByLabelText('플랭크 반복 횟수')).toBeNull();
    expect(screen.getByText('초')).toBeOnTheScreen();
    expect(screen.queryByText('회')).toBeNull();
  });

  it('reports a time edit as seconds so it is never sent as repetitions', () => {
    const onChangePrescription = renderCard([DURATION_ITEM]);

    fireEvent.changeText(screen.getByLabelText('플랭크 세트당 시간(초)'), '45');

    expect(onChangePrescription).toHaveBeenCalledWith('item-2', {
      workSeconds: '45',
    });
    expect(onChangePrescription).not.toHaveBeenCalledWith(
      'item-2',
      expect.objectContaining({ reps: expect.anything() }),
    );
  });

  it('keeps the repetition field for a repetition-based block', () => {
    const onChangePrescription = renderCard([REPETITION_ITEM]);

    expect(screen.getByLabelText('푸시업 반복 횟수')).toBeOnTheScreen();
    expect(screen.queryByLabelText('푸시업 세트당 시간(초)')).toBeNull();

    fireEvent.changeText(screen.getByLabelText('푸시업 반복 횟수'), '12');

    expect(onChangePrescription).toHaveBeenCalledWith('item-1', {
      reps: '12',
    });
  });

  it('shows the seconds the user typed rather than the item total', () => {
    // `work_seconds` is the total across sets; showing it here read a 2 x 30s
    // plank as "2세트 × 1분".
    renderCard([DURATION_ITEM]);

    expect(screen.getByLabelText('플랭크 세트당 시간(초)').props.value).toBe(
      '30',
    );
  });
});
