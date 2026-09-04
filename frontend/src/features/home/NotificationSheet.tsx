import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type {
  NotificationListResponse,
  NotificationResponse,
} from '../../api/types';
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
  onClose,
  onRetry,
  onSelect,
  pendingNotificationId,
  response,
  status,
  visible,
}: {
  errorMessage?: string | null;
  onClose: () => void;
  onRetry: () => void;
  onSelect: (notification: NotificationResponse) => void;
  pendingNotificationId: string | null;
  response: NotificationListResponse | null;
  status: NotificationLoadStatus;
  visible: boolean;
}) {
  const items = response?.items ?? [];

  return (
    <Modal
      animationType="slide"
      onRequestClose={onClose}
      presentationStyle="overFullScreen"
      statusBarTranslucent
      transparent
      visible={visible}
    >
      <Pressable accessible={false} onPress={onClose} style={styles.overlay}>
        <Pressable
          accessibilityViewIsModal
          onPress={(event) => event.stopPropagation()}
          style={styles.sheet}
        >
          <View style={styles.handle} />
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
            <Pressable
              accessibilityLabel="알림함 닫기"
              accessibilityRole="button"
              onPress={onClose}
              style={styles.closeButton}
            >
              <Text style={styles.closeText}>×</Text>
            </Pressable>
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
                    <Text style={styles.itemMessage}>
                      {notification.message}
                    </Text>
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
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(55, 42, 31, 0.36)',
  },
  sheet: {
    maxHeight: '72%',
    minHeight: 300,
    borderTopLeftRadius: 26,
    borderTopRightRadius: 26,
    backgroundColor: colors.canvas,
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.xl,
    paddingBottom: 28,
    ...shadows.card,
  },
  handle: {
    width: 42,
    height: 4,
    alignSelf: 'center',
    borderRadius: 999,
    backgroundColor: colors.borderSoft,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: '800' },
  unreadSummary: {
    marginTop: 3,
    color: colors.primaryBusy,
    fontSize: 12,
    fontWeight: '700',
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: colors.surface,
  },
  closeText: { color: colors.textSub, fontSize: 28, lineHeight: 30 },
  state: {
    minHeight: 210,
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
  list: { gap: spacing.md, paddingBottom: spacing.md },
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
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: spacing.lg,
  },
  unreadItem: {
    borderColor: colors.successBorder,
    backgroundColor: colors.successSurface,
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
