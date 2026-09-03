import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { processColor, StyleSheet, View } from 'react-native';

import type { Api } from '../src/api/endpoints';
import { colors } from '../src/components/theme';
import { SessionResultScreen } from '../src/features/workout/SessionResultScreen';

const finished = {
  kind: 'finished' as const,
  result: {
    session_id: 'session-result',
    status_code: 'COMPLETED' as const,
    completed_item_count: 3,
    total_item_count: 3,
    actual_elapsed_seconds: 900,
    estimated_calories_burned: 80,
    ended_at: '2026-08-19T10:00:00+09:00',
  },
};

function hasBrandBand(view: ReturnType<typeof render>) {
  return view.UNSAFE_getAllByType(View).some((node) => {
    const style = StyleSheet.flatten(node.props.style);
    return (
      style?.backgroundColor === colors.splashBackground && style.height === 245
    );
  });
}

describe('SessionResultScreen feedback', () => {
  it('uses the Workout canvas treatment for a completed result', () => {
    const view = render(
      <SessionResultScreen
        api={{ submitFeedback: jest.fn() } as unknown as Api}
        sessionId="session-result"
        outcome={finished}
        onDone={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toHaveStyle({ color: colors.text });
    expect(hasBrandBand(view)).toBe(false);

    const feedbackButton = screen.getByTestId('session-feedback-save');
    const buttonStyle = StyleSheet.flatten(feedbackButton.props.style);
    const gradient = screen.getByTestId('session-feedback-save-gradient');

    expect(buttonStyle).toMatchObject({
      alignItems: 'center',
      borderColor: 'rgba(244, 166, 42, 0.8)',
      borderWidth: expect.any(Number),
      justifyContent: 'center',
      position: 'relative',
      shadowColor: '#AD741D',
      shadowOpacity: 0.11,
    });
    expect(gradient.props.colors).toEqual(
      ['#FEE8B1', '#FEDA99', '#FFD790'].map(processColor),
    );
    expect(gradient.props.locations).toEqual([0, 0.55, 1]);
    expect(screen.queryByTestId('session-feedback-save-chevron')).toBeNull();
  });

  it.each([
    {
      name: 'completed',
      outcome: finished,
    },
    {
      name: 'partial',
      outcome: {
        kind: 'finished' as const,
        result: {
          ...finished.result,
          status_code: 'PARTIAL' as const,
          completed_item_count: 2,
        },
      },
    },
    {
      name: 'not-completed',
      outcome: {
        kind: 'notCompleted' as const,
        result: {
          session_id: 'session-result',
          status_code: 'NOT_COMPLETED' as const,
          reason_code: 'TIME_SHORTAGE' as const,
          ended_at: '2026-08-19T10:00:00+09:00',
        },
      },
    },
    {
      name: 'safety-stop',
      outcome: {
        kind: 'safetyStop' as const,
        event: {
          event_id: 'safety-event-result',
          instruction_code: 'STOP_AND_SEEK_HELP' as const,
          resulting_action_code: 'STOP_AND_SEEK_HELP' as const,
          session_status_code: 'STOPPED_FOR_SAFETY' as const,
          guidance_code: 'SEEK_HELP',
          guidance: '운동을 중단하고 상태를 확인해 주세요.',
          pressure_notifications_allowed: false,
        },
      },
    },
  ])('uses the same canvas background for a $name result', ({ outcome }) => {
    const view = render(
      <SessionResultScreen
        api={{ submitFeedback: jest.fn() } as unknown as Api}
        sessionId="session-result"
        outcome={outcome}
        onDone={jest.fn()}
      />,
    );

    expect(hasBrandBand(view)).toBe(false);
    expect(
      screen.getByTestId('session-feedback-save-gradient'),
    ).toBeOnTheScreen();
    expect(screen.queryByTestId('session-feedback-save-chevron')).toBeNull();
    expect(screen.getByText('오늘 운동 체감 난이도')).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: '쉬웠어요' })).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: '적당했어요' })).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: '어려워요' })).toBeOnTheScreen();
    expect(screen.queryByText('피로도')).toBeNull();
    expect(screen.queryByText('만족도')).toBeNull();
    expect(screen.queryByText('운동 후 통증')).toBeNull();
    expect(screen.queryByText('불편한 부위')).toBeNull();
    expect(screen.queryByText('이상 반응')).toBeNull();
  });

  it('submits the selected difficulty with hidden legacy compatibility values', async () => {
    const submitFeedback = jest.fn<Api['submitFeedback']>(async () => ({
      session_id: 'session-result',
      session_status_code: 'COMPLETED',
      created_at: '2026-08-19T10:01:00+09:00',
      guidance_code: null,
      guidance: null,
      pressure_notifications_allowed: true,
    }));

    render(
      <SessionResultScreen
        api={{ submitFeedback } as unknown as Api}
        sessionId="session-result"
        outcome={finished}
        onDone={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('radio', { name: '적당했어요' }));
    fireEvent.press(screen.getByRole('button', { name: '피드백 저장' }));

    await waitFor(() =>
      expect(submitFeedback).toHaveBeenCalledWith('session-result', {
        difficulty_code: 'APPROPRIATE',
        fatigue_code: null,
        satisfaction_code: null,
        pain_occurred: false,
        discomforts: [],
        adverse_reaction_codes: [],
      }),
    );
    expect(await screen.findByText('피드백을 저장했어요.')).toBeOnTheScreen();
  });

  it('shows multi-select details only when the workout felt hard', () => {
    render(
      <SessionResultScreen
        api={{ submitFeedback: jest.fn() } as unknown as Api}
        sessionId="session-result"
        outcome={finished}
        onDone={jest.fn()}
      />,
    );

    expect(screen.queryByText(/어떤 점이 어려웠나요/)).toBeNull();

    fireEvent.press(screen.getByRole('radio', { name: '어려워요' }));

    expect(
      screen.getByText('어떤 점이 어려웠나요? (복수 선택)'),
    ).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '피드백 저장' })).toBeDisabled();

    const formDifficulty = screen.getByRole('checkbox', {
      name: '자세가 어려웠어요',
    });
    const highIntensity = screen.getByRole('checkbox', {
      name: '강도가 높았어요',
    });

    fireEvent.press(formDifficulty);
    fireEvent.press(highIntensity);

    expect(formDifficulty.props.accessibilityState).toEqual({ checked: true });
    expect(highIntensity.props.accessibilityState).toEqual({ checked: true });
    expect(screen.getByRole('button', { name: '피드백 저장' })).toBeEnabled();
  });

  it('clears hard-workout details after another difficulty is selected', () => {
    render(
      <SessionResultScreen
        api={{ submitFeedback: jest.fn() } as unknown as Api}
        sessionId="session-result"
        outcome={finished}
        onDone={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('radio', { name: '어려워요' }));
    fireEvent.press(
      screen.getByRole('checkbox', { name: '자세가 어려웠어요' }),
    );
    fireEvent.press(screen.getByRole('radio', { name: '적당했어요' }));
    expect(screen.queryByText(/어떤 점이 어려웠나요/)).toBeNull();

    fireEvent.press(screen.getByRole('radio', { name: '어려워요' }));
    expect(
      screen.getByRole('checkbox', { name: '자세가 어려웠어요' }).props
        .accessibilityState,
    ).toEqual({ checked: false });
    expect(screen.getByRole('button', { name: '피드백 저장' })).toBeDisabled();
  });

  it('also exposes feedback after a not-completed outcome', () => {
    render(
      <SessionResultScreen
        api={{ submitFeedback: jest.fn() } as unknown as Api}
        sessionId="session-result"
        outcome={{
          kind: 'notCompleted',
          result: {
            session_id: 'session-result',
            status_code: 'NOT_COMPLETED',
            reason_code: 'TIME_SHORTAGE',
            ended_at: '2026-08-19T10:00:00+09:00',
          },
        }}
        onDone={jest.fn()}
      />,
    );

    expect(screen.getByText('오늘 운동 체감 난이도')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '피드백 저장' })).toBeDisabled();
  });
});
