import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { HomeScreen } from '../src/features/home/HomeScreen';

describe('HomeScreen visual prototype', () => {
  it('moves from pre-checkin to the sheet and generation fixture locally', async () => {
    const onOpenCheckin = jest.fn();
    const onSaveCheckin = jest.fn();
    await render(
      <HomeScreen
        onOpenCheckin={onOpenCheckin}
        onSaveCheckin={onSaveCheckin}
      />,
    );

    expect(screen.getByText('아직 오늘의 운동이 없어요')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));

    expect(
      screen.getByRole('header', { name: '오늘 컨디션 체크' }),
    ).toBeOnTheScreen();
    expect(onOpenCheckin).toHaveBeenCalledTimes(1);

    fireEvent.press(screen.getByRole('button', { name: '좋아요' }));
    expect(
      screen.getByRole('button', { name: '좋아요' }).props.accessibilityState
        .selected,
    ).toBe(true);
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(screen.getByText('새로운 루틴을 받고 있어요')).toBeOnTheScreen();
    expect(onSaveCheckin).toHaveBeenCalledTimes(1);
  });

  it('shows one final routine and exposes actions only through callbacks', async () => {
    const onStartWorkout = jest.fn();
    const onRequestAlternative = jest.fn();
    await render(
      <HomeScreen
        onRequestAlternative={onRequestAlternative}
        onStartWorkout={onStartWorkout}
        previewState="routine"
      />,
    );

    expect(screen.getAllByText('오늘의 운동')).toHaveLength(1);
    expect(screen.getByText('상체 근력 루틴')).toBeOnTheScreen();
    expect(screen.queryByText(/lighter|original/i)).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '운동 시작하기  ›' }));
    expect(onStartWorkout).toHaveBeenCalledTimes(1);

    fireEvent.press(
      screen.getByRole('button', { name: '↻  다른 루틴 · 2회 남음' }),
    );
    expect(screen.getByText('새로운 루틴을 받고 있어요')).toBeOnTheScreen();
    expect(onRequestAlternative).toHaveBeenCalledTimes(1);
  });

  it('shows the adjustment note as part of the final routine, not an option', async () => {
    await render(<HomeScreen previewState="adjusted" />);

    expect(screen.getByText('컨디션 맞춤 루틴')).toBeOnTheScreen();
    expect(
      screen.getByText('무릎 부담을 줄이도록 강도를 조정했어요.'),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('opens the edit sheet and returns edited fixture data through a callback', async () => {
    const onSaveEdit = jest.fn();
    await render(<HomeScreen onSaveEdit={onSaveEdit} previewState="editing" />);

    expect(
      screen.getByRole('header', { name: '오늘의 운동 수정' }),
    ).toBeOnTheScreen();
    fireEvent.changeText(
      screen.getByLabelText('푸시업 운동명'),
      '무릎 대고 푸시업',
    );
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));

    expect(onSaveEdit).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ name: '무릎 대고 푸시업' }),
      ]),
    );
    expect(screen.getByText('상체 근력 루틴')).toBeOnTheScreen();
  });
});
