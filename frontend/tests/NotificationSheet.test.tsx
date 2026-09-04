import { fireEvent, render, screen } from '@testing-library/react-native';

import type { NotificationResponse } from '../src/api/types';
import {
  NotificationSheet,
  notificationTitle,
} from '../src/features/home/NotificationSheet';

function notification(
  overrides: Partial<NotificationResponse> = {},
): NotificationResponse {
  return {
    notification_id: 'notification-1',
    type: 'KIKKI_RETURN',
    title: '끼끼가 기다리고 있어요',
    message: '끼끼의 집에 들러주세요.',
    created_at: '2026-09-04T09:00:00+09:00',
    read_at: null,
    is_read: false,
    action_type: 'OPEN_KIKKI_HOME',
    payload: {},
    ...overrides,
  };
}

describe('NotificationSheet', () => {
  it('uses the remaining count and separates one workout from multiple', () => {
    expect(
      notificationTitle(
        notification({
          type: 'WEEKLY_GOAL_REMINDER',
          payload: { remaining_workout_count: 1 },
        }),
      ),
    ).toBe('이번 주 목표까지 운동 한 번 남았어요!');
    expect(
      notificationTitle(
        notification({
          type: 'WEEKLY_GOAL_REMINDER',
          payload: { remaining_workout_count: 3 },
        }),
      ),
    ).toBe('이번 주 목표까지 운동 3회 남았어요!');
  });

  it('keeps the server order and forwards the selected notification', () => {
    const onSelect = jest.fn();
    render(
      <NotificationSheet
        onClose={jest.fn()}
        onRetry={jest.fn()}
        onSelect={onSelect}
        pendingNotificationId={null}
        response={{
          items: [
            notification({ notification_id: 'newest', title: '최신 알림' }),
            notification({
              notification_id: 'older',
              title: '이전 알림',
              is_read: true,
              read_at: '2026-09-04T09:30:00+09:00',
            }),
          ],
          unread_count: 1,
        }}
        status="ready"
        visible
      />,
    );

    expect(
      screen
        .getAllByRole('button')
        .map((item) => item.props.accessibilityLabel),
    ).toEqual(
      expect.arrayContaining([
        '알림함 닫기',
        '최신 알림 알림 확인',
        '이전 알림 알림 확인',
      ]),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '최신 알림 알림 확인' }),
    );
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ notification_id: 'newest' }),
    );
  });

  it('shows loading, empty and retryable error states', () => {
    const onRetry = jest.fn();
    const view = render(
      <NotificationSheet
        onClose={jest.fn()}
        onRetry={onRetry}
        onSelect={jest.fn()}
        pendingNotificationId={null}
        response={null}
        status="loading"
        visible
      />,
    );
    expect(screen.getByText('알림을 불러오고 있어요.')).toBeOnTheScreen();

    view.rerender(
      <NotificationSheet
        errorMessage="네트워크를 확인해주세요."
        onClose={jest.fn()}
        onRetry={onRetry}
        onSelect={jest.fn()}
        pendingNotificationId={null}
        response={null}
        status="error"
        visible
      />,
    );
    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    view.rerender(
      <NotificationSheet
        onClose={jest.fn()}
        onRetry={onRetry}
        onSelect={jest.fn()}
        pendingNotificationId={null}
        response={{ items: [], unread_count: 0 }}
        status="ready"
        visible
      />,
    );
    expect(screen.getByText('아직 새로운 소식이 없어요.')).toBeOnTheScreen();
  });
});
