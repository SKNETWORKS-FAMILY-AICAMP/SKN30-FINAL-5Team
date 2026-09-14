import { useCallback, useEffect, useMemo, useState } from 'react';

import type {
  NotificationListResponse,
  NotificationResponse,
} from '../../api/types';
import { HomeScreen, type HomeScreenProps } from '../home/HomeScreen';
import {
  NotificationSheet,
  type NotificationLoadStatus,
} from '../home/NotificationSheet';
import { homePreviewProps } from './homePreview';

export type NotificationPreviewState =
  'unread' | 'toast' | 'empty' | 'loading' | 'error';

export const NOTIFICATION_PREVIEW_OPTIONS = [
  { id: 'unread', label: '읽지 않은 알림' },
  { id: 'toast', label: '새 알림 토스트' },
  { id: 'empty', label: '빈 알림함' },
  { id: 'loading', label: '불러오는 중' },
  { id: 'error', label: '불러오기 실패' },
] as const satisfies readonly {
  id: NotificationPreviewState;
  label: string;
}[];

const PREVIEW_NOTIFICATIONS: NotificationResponse[] = [
  {
    notification_id: 'preview-kikki-return-1',
    type: 'KIKKI_RETURN',
    title: '끼끼가 기다리고 있어요',
    message: '오랜만이에요! 끼끼의 집에 들러 인사해주세요.',
    created_at: '2026-09-04T09:00:00+09:00',
    read_at: null,
    is_read: false,
    action_type: 'OPEN_KIKKI_HOME',
    payload: {},
  },
  {
    notification_id: 'preview-weekly-one',
    type: 'WEEKLY_GOAL_REMINDER',
    title: '이번 주 목표를 확인해보세요',
    message: '목표 달성까지 조금만 더 힘내봐요.',
    created_at: '2026-09-04T08:00:00+09:00',
    read_at: null,
    is_read: false,
    action_type: null,
    payload: { remaining_workout_count: 1 },
  },
  {
    notification_id: 'preview-weekly-many',
    type: 'WEEKLY_GOAL_REMINDER',
    title: '이번 주 목표를 확인해보세요',
    message: '이번 주 운동 목표가 남아 있어요.',
    created_at: '2026-09-03T18:00:00+09:00',
    read_at: null,
    is_read: false,
    action_type: null,
    payload: { remaining_workout_count: 3 },
  },
  {
    notification_id: 'preview-daily-reward',
    type: 'DAILY_REWARD',
    title: '오늘의 보상을 받았어요',
    message: '운동을 마치고 바나나를 획득했어요.',
    created_at: '2026-09-02T20:00:00+09:00',
    read_at: '2026-09-02T20:05:00+09:00',
    is_read: true,
    action_type: null,
    payload: {},
  },
];

function unreadResponse(): NotificationListResponse {
  return {
    items: PREVIEW_NOTIFICATIONS.map((notification) => ({ ...notification })),
    unread_count: PREVIEW_NOTIFICATIONS.filter(
      (notification) => !notification.is_read,
    ).length,
  };
}

function initialSheetStatus(
  state: NotificationPreviewState,
): NotificationLoadStatus {
  if (state === 'loading') {
    return 'loading';
  }
  if (state === 'error') {
    return 'error';
  }
  return 'ready';
}

function initialResponse(
  state: NotificationPreviewState,
): NotificationListResponse | null {
  if (state === 'loading' || state === 'error') {
    return null;
  }
  if (state === 'empty') {
    return { items: [], unread_count: 0 };
  }
  return unreadResponse();
}

export function NotificationPreview({
  homeProps,
  initiallyOpen = true,
  onNavigateHomeTab,
  onOpenKikkiHome,
  state,
}: {
  homeProps?: HomeScreenProps;
  initiallyOpen?: boolean;
  onNavigateHomeTab?: Parameters<typeof HomeScreen>[0]['onNavigateTab'];
  onOpenKikkiHome: () => void;
  state: NotificationPreviewState;
}) {
  const [response, setResponse] = useState<NotificationListResponse | null>(
    () => initialResponse(state),
  );
  const [status, setStatus] = useState<NotificationLoadStatus>(() =>
    initialSheetStatus(state),
  );
  const [sheetOpen, setSheetOpen] = useState(
    initiallyOpen && state !== 'toast',
  );
  const [toastVisible, setToastVisible] = useState(state === 'toast');

  useEffect(() => {
    if (!toastVisible) {
      return;
    }
    const timer = setTimeout(() => setToastVisible(false), 2500);
    return () => clearTimeout(timer);
  }, [toastVisible]);

  const hasUnread = (response?.unread_count ?? 0) > 0;
  const fallbackHomeProps = useMemo(() => homePreviewProps('pre-checkin'), []);
  const previewHomeProps = homeProps ?? fallbackHomeProps;

  const retry = useCallback(() => {
    setResponse(unreadResponse());
    setStatus('ready');
  }, []);

  const selectNotification = useCallback(
    (selected: NotificationResponse) => {
      setResponse((current) => {
        if (current === null || selected.is_read) {
          return current;
        }
        const items = current.items.map((notification) =>
          notification.notification_id === selected.notification_id
            ? {
                ...notification,
                is_read: true,
                read_at: '2026-09-04T10:00:00+09:00',
              }
            : notification,
        );
        return {
          items,
          unread_count: items.filter((notification) => !notification.is_read)
            .length,
        };
      });

      if (selected.action_type === 'OPEN_KIKKI_HOME') {
        setSheetOpen(false);
        onOpenKikkiHome();
      }
    },
    [onOpenKikkiHome],
  );

  return (
    <>
      <HomeScreen
        {...previewHomeProps}
        hasUnreadNotification={hasUnread}
        notificationPanel={
          <NotificationSheet
            errorMessage="네트워크 연결을 확인한 뒤 다시 시도해주세요."
            onRetry={retry}
            onSelect={selectNotification}
            pendingNotificationId={null}
            response={response}
            status={status}
            visible={sheetOpen}
          />
        }
        onDismissNotificationPanel={
          sheetOpen ? () => setSheetOpen(false) : undefined
        }
        notificationToastVisible={toastVisible}
        onNavigateTab={onNavigateHomeTab ?? previewHomeProps.onNavigateTab}
        onNotifications={() => setSheetOpen((current) => !current)}
      />
    </>
  );
}
