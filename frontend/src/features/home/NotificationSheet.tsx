import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type {
  NotificationListResponse,
  NotificationResponse,
} from '../../api/types';
import { useScale } from '../../components/scale';
import { colors, shadows, spacing } from '../../components/theme';

export type NotificationLoadStatus = 'idle' | 'loading' | 'ready' | 'error';

export function notificationTitle(notification: NotificationResponse): string {
  if (notification.type !== 'WEEKLY_GOAL_REMINDER') {
    return notification.title;
  }

  const remaining = notification.payload.remaining_workout_count;
  if (!Number.isInteger(remaining) || (remaining ?? 0) < 1) {
    return notification.title;
  }
  if (remaining === 1) {
    return '이번 주 목표까지 운동 한 번 남았어요!';
  }
  return `이번 주 목표까지 운동 ${remaining}회 남았어요!`;
}

function createdAtLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function NotificationSheet({
  errorMessage,
  onRetry,
  onSelect,
  pendingNotificationId,
  response,
  status,
  visible,
}: {
  errorMessage?: string | null;
  onRetry: () => void;
  onSelect: (notification: NotificationResponse) => void;
  pendingNotificationId: string | null;
  response: NotificationListResponse | null;
  status: NotificationLoadStatus;
  visible: boolean;
}) {
  const items = response?.items ?? [];
  const { height, s, width } = useScale();
  const insets = useSafeAreaInsets();
  const popoverWidth = Math.min(s(360), Math.max(0, width - s(44)));
  const popoverMaxHeight = Math.max(
    0,
    Math.min(
      s(400),
      height -
        Math.max(insets.top, s(58)) -
        s(60) -
        Math.max(insets.bottom, s(16)),
    ),
  );

  if (!visible) {
    return null;
  }

  return (
    <Pressable
      onPress={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
      style={[
        styles.popover,
        {
          maxHeight: popoverMaxHeight,
          minHeight: Math.min(s(180), popoverMaxHeight),
          top: s(56),
          width: popoverWidth,
        },
      ]}
      testID="notification-popover"
    >
      <View
        pointerEvents="none"
        style={[
          styles.pointer,
          { height: s(14), right: s(73), top: -s(7), width: s(14) },
        ]}
        testID="notification-popover-pointer"
      />
      <View style={styles.header}>
        <View>
          <Text accessibilityRole="header" style={styles.title}>
            알림
          </Text>
          {response && response.unread_count > 0 ? (
            <Text style={styles.unreadSummary}>
              읽지 않은 소식 {response.unread_count}개
            </Text>
          ) : null}
        </View>
      </View>

      {status === 'loading' && response === null ? (
        <View style={styles.state}>
          <ActivityIndicator color={colors.primaryBusy} />
          <Text style={styles.stateText}>알림을 불러오고 있어요.</Text>
        </View>
      ) : status === 'error' && response === null ? (
        <View style={styles.state}>
          <Text style={styles.stateTitle}>알림을 불러오지 못했어요.</Text>
          <Text style={styles.stateText}>{errorMessage}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={onRetry}
            style={styles.retryButton}
          >
            <Text style={styles.retryText}>다시 시도</Text>
          </Pressable>
        </View>
      ) : items.length === 0 ? (
        <View style={styles.state}>
          <Text style={styles.stateTitle}>아직 새로운 소식이 없어요.</Text>
          <Text style={styles.stateText}>
            끼끼가 소식을 가져오면 여기에 알려드릴게요.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          style={styles.scroll}
        >
          {status === 'error' ? (
            <View style={styles.inlineError}>
              <Text style={styles.inlineErrorText}>{errorMessage}</Text>
              <Pressable accessibilityRole="button" onPress={onRetry}>
                <Text style={styles.inlineRetryText}>다시 불러오기</Text>
              </Pressable>
            </View>
          ) : null}
          {items.map((notification) => {
            const pending =
              pendingNotificationId === notification.notification_id;
            const title = notificationTitle(notification);
            return (
              <Pressable
                key={notification.notification_id}
                accessibilityLabel={`${title} 알림 확인`}
                accessibilityRole="button"
                accessibilityState={{
                  busy: pending,
                  disabled: pendingNotificationId !== null,
                }}
                disabled={pendingNotificationId !== null}
                onPress={() => onSelect(notification)}
                style={[
                  styles.item,
                  !notification.is_read && styles.unreadItem,
                  pending && styles.pendingItem,
                ]}
              >
                <View style={styles.itemHeading}>
                  {!notification.is_read ? (
                    <View
                      accessibilityLabel="읽지 않은 알림"
                      style={styles.unreadDot}
                    />
                  ) : null}
                  <Text style={styles.itemTitle}>{title}</Text>
                </View>
                <Text style={styles.itemMessage}>{notification.message}</Text>
                <View style={styles.itemFooter}>
                  <Text style={styles.itemTime}>
                    {createdAtLabel(notification.created_at)}
                  </Text>
                  {pending ? (
                    <ActivityIndicator
                      color={colors.primaryBusy}
                      size="small"
                    />
                  ) : notification.action_type === 'OPEN_KIKKI_HOME' ? (
                    <Text style={styles.actionText}>끼끼의 집 보기 ›</Text>
                  ) : null}
                </View>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  popover: {
    position: 'absolute',
    right: 0,
    zIndex: 50,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: 20,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
    ...shadows.card,
  },
  pointer: {
    position: 'absolute',
    transform: [{ rotate: '45deg' }],
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surface,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  title: { color: colors.text, fontSize: 18, fontWeight: '800' },
  unreadSummary: {
    marginTop: 3,
    color: colors.primaryBusy,
    fontSize: 12,
    fontWeight: '700',
  },
  state: {
    minHeight: 136,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  stateTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  stateText: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  retryButton: {
    minHeight: 44,
    justifyContent: 'center',
    marginTop: spacing.sm,
    borderRadius: 14,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
  },
  retryText: { color: colors.text, fontSize: 14, fontWeight: '800' },
  scroll: { flexShrink: 1, overflow: 'hidden' },
  list: { gap: spacing.sm, paddingTop: spacing.xs },
  inlineError: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    borderRadius: 12,
    backgroundColor: colors.warningSurface,
    padding: spacing.md,
  },
  inlineErrorText: { flex: 1, color: colors.warningText, fontSize: 12 },
  inlineRetryText: {
    color: colors.warningText,
    fontSize: 12,
    fontWeight: '800',
  },
  item: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    backgroundColor: colors.surface,
    padding: spacing.md,
  },
  unreadItem: {
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerBg,
  },
  pendingItem: { opacity: 0.64 },
  itemHeading: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#D94545',
  },
  itemTitle: {
    flex: 1,
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 21,
  },
  itemMessage: {
    marginTop: 6,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  itemFooter: {
    minHeight: 22,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  itemTime: { color: colors.textFaint, fontSize: 11 },
  actionText: {
    color: colors.primaryBusy,
    fontSize: 12,
    fontWeight: '800',
  },
});
