import {
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';
import { Text } from 'react-native';

import { CloseButton } from '../src/components/CloseButton';
import { RoutineSections } from '../src/components/RoutineSections';
import { HomeScreen } from '../src/features/home/HomeScreen';
import { homePreviewProps } from '../src/features/preview/homePreview';

describe('routine phase sections', () => {
  it.each(['routine', 'session-resumable', 'session-completed'] as const)(
    'keeps every exercise inside its phase in %s',
    (state) => {
      const props = homePreviewProps(state);
      const decision = props.decision!;
      const plan = decision.final_plan!;
      render(
        <HomeScreen
          {...props}
          decision={{
            ...decision,
            final_plan: {
              ...plan,
              items: plan.items.map((item, index) => ({
                ...item,
                phase_code: (['WARMUP', 'MAIN', 'COOLDOWN'] as const)[index],
              })),
            },
          }}
        />,
      );
      (['WARMUP', 'MAIN', 'COOLDOWN'] as const).forEach((phase, index) => {
        const section = within(screen.getByTestId(`routine-phase-${phase}`));
        expect(
          section.getByTestId(`routine-row-${plan.items[index]!.plan_item_id}`),
        ).toBeOnTheScreen();
      });
      if (state === 'routine') {
        expect(
          screen.getByTestId('routine-drag-plan-item-1'),
        ).toBeOnTheScreen();
        expect(
          screen.getByTestId('routine-drag-plan-item-3'),
        ).toBeOnTheScreen();
      } else if (state === 'session-resumable') {
        expect(screen.queryByTestId('routine-drag-plan-item-1')).toBeNull();
        expect(
          screen.getByTestId('routine-drag-plan-item-3'),
        ).toBeOnTheScreen();
      } else {
        expect(screen.queryByTestId('routine-drag-plan-item-1')).toBeNull();
        expect(screen.queryByTestId('routine-drag-plan-item-3')).toBeNull();
      }
      if (state === 'session-resumable') {
        expect(
          screen.getByText('이어서 운동을 진행할 수 있어요'),
        ).toBeOnTheScreen();
      }
    },
  );

  it('allows same-phase reordering and refuses moves across phase boundaries', () => {
    const onReorderPlan = jest.fn();
    const props = homePreviewProps('routine');
    const decision = props.decision!;
    const plan = decision.final_plan!;
    render(
      <HomeScreen
        {...props}
        onReorderPlan={onReorderPlan}
        decision={{
          ...decision,
          final_plan: {
            ...plan,
            items: (
              [
                'WARMUP',
                'WARMUP',
                'MAIN',
                'MAIN',
                'COOLDOWN',
                'COOLDOWN',
              ] as const
            ).map((phase_code, index) => ({
              ...plan.items[0]!,
              plan_item_id: `phase-item-${index}`,
              sequence: index + 1,
              phase_code,
            })),
          },
        }}
      />,
    );
    fireEvent(
      screen.getByTestId('routine-drag-phase-item-1'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    expect(onReorderPlan).not.toHaveBeenCalled();
    fireEvent(
      screen.getByTestId('routine-drag-phase-item-0'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    fireEvent(
      screen.getByTestId('routine-drag-phase-item-2'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    fireEvent(
      screen.getByTestId('routine-drag-phase-item-4'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    expect(onReorderPlan.mock.calls).toEqual([
      [0, 1],
      [2, 3],
      [4, 5],
    ]);
  });

  it('keeps phase-less legacy items visible and does not create empty phases', () => {
    render(
      <RoutineSections
        items={['legacy']}
        getPhase={() => undefined}
        renderItem={(item, index) => (
          <Text key={item}>
            {index}: {item}
          </Text>
        )}
      />,
    );
    expect(screen.getByText('0: legacy')).toBeOnTheScreen();
    expect(screen.getByText('메인 운동')).toBeOnTheScreen();
    expect(screen.queryByText('웜업')).toBeNull();
    expect(screen.queryByText('쿨다운')).toBeNull();
  });
});

it('uses one accessible unboxed close control and respects pending state', () => {
  const onPress = jest.fn();
  const view = render(
    <CloseButton onPress={onPress} accessibilityLabel="운동 기록 닫기" />,
  );
  expect(screen.getByText('×')).toBeOnTheScreen();
  fireEvent.press(screen.getByRole('button', { name: '운동 기록 닫기' }));
  expect(onPress).toHaveBeenCalledTimes(1);
  view.rerender(<CloseButton onPress={onPress} disabled />);
  expect(screen.getByRole('button', { name: '닫기' })).toBeDisabled();
  fireEvent.press(screen.getByRole('button', { name: '닫기' }));
  expect(onPress).toHaveBeenCalledTimes(1);
});
