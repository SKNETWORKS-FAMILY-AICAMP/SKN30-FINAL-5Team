import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import type { NotificationResponse } from '../src/api/types';
import { ScaleViewportProvider } from '../src/components/scale';
import { colors } from '../src/components/theme';
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
      expect.arrayContaining(['최신 알림 알림 확인', '이전 알림 알림 확인']),
    );
    const [unreadItem, readItem] = screen.getAllByRole('button');
    expect(StyleSheet.flatten(unreadItem.props.style)).toEqual(
      expect.objectContaining({
        borderColor: colors.dangerBorder,
        backgroundColor: colors.dangerBg,
      }),
    );
    expect(StyleSheet.flatten(readItem.props.style)).toEqual(
      expect.objectContaining({ backgroundColor: colors.surface }),
    );
    fireEvent.press(
      screen.getByRole('button', { name: '최신 알림 알림 확인' }),
    );
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ notification_id: 'newest' }),
    );
  });

  it('opens as a compact popover below the notification button', () => {
    const viewports = [
      { width: 320, height: 568 },
      { width: 390, height: 844 },
      { width: 768, height: 1024 },
    ];

    for (const viewport of viewports) {
      const view = render(
        <ScaleViewportProvider viewport={viewport}>
          <NotificationSheet
            onRetry={jest.fn()}
            onSelect={jest.fn()}
            pendingNotificationId={null}
            response={{ items: [notification()], unread_count: 1 }}
            status="ready"
            visible
          />
        </ScaleViewportProvider>,
      );
      const scale = Math.min(viewport.width / 390, 1.2);
      const popover = StyleSheet.flatten(
        screen.getByTestId('notification-popover').props.style,
      );
      const pointer = StyleSheet.flatten(
        screen.getByTestId('notification-popover-pointer').props.style,
      );

      expect(popover).toEqual(
        expect.objectContaining({
          position: 'absolute',
          right: 0,
          top: 56 * scale,
          width: Math.min(360 * scale, viewport.width - 44 * scale),
          backgroundColor: colors.surface,
        }),
      );
      expect(pointer).toEqual(
        expect.objectContaining({
          right: 73 * scale,
          width: 14 * scale,
          backgroundColor: colors.surface,
        }),
      );
      expect(popover.width).toBeLessThanOrEqual(viewport.width - 44 * scale);
      expect(screen.queryByLabelText('알림함 닫기')).not.toBeOnTheScreen();
      const stopPropagation = jest.fn();
      fireEvent(screen.getByTestId('notification-popover'), 'pointerDown', {
        stopPropagation,
      });
      expect(stopPropagation).toHaveBeenCalledTimes(1);
      view.unmount();
    }
  });

  it('shows loading, empty and retryable error states', () => {
    const onRetry = jest.fn();
    const view = render(
      <NotificationSheet
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
