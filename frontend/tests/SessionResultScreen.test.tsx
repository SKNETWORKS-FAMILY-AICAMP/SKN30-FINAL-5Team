import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

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

describe('SessionResultScreen feedback', () => {
  it('uses the Workout canvas treatment for a completed result', () => {
    render(
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
  });

  it('submits every backend feedback field from the result UI', async () => {
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
    fireEvent.press(screen.getByRole('radio', { name: '높아요' }));
    fireEvent.press(screen.getByRole('radio', { name: '만족해요' }));
    fireEvent.press(screen.getByRole('radio', { name: '있어요' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '무릎' }));
    fireEvent.press(screen.getByRole('radio', { name: '무릎 심함' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '심한 어지럼' }));
    fireEvent.press(screen.getByRole('button', { name: '피드백 저장' }));

    await waitFor(() =>
      expect(submitFeedback).toHaveBeenCalledWith('session-result', {
        difficulty_code: 'APPROPRIATE',
        fatigue_code: 'HIGH',
        satisfaction_code: 'SATISFIED',
        pain_occurred: true,
        discomforts: [{ body_area_code: 'KNEE', severity_code: 'SEVERE' }],
        adverse_reaction_codes: ['SEVERE_DIZZINESS'],
      }),
    );
    expect(await screen.findByText('피드백을 저장했어요.')).toBeOnTheScreen();
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

    expect(screen.getByText('오늘 운동은 어땠나요?')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '피드백 저장' })).toBeDisabled();
  });
});
