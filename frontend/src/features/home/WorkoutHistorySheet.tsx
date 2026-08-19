import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { Api } from '../../api/endpoints';
import { notCompletedReasonLabel, sessionStatusLabel } from '../../api/labels';
import type { WorkoutSessionDetailResponse } from '../../api/types';
import { useAsyncData } from '../../api/useAsync';
import { colors, shadows, spacing } from '../../components/theme';

export function WorkoutHistorySheet({
  api,
  localDate,
  onClose,
  sessionIds,
}: {
  api: Pick<Api, 'getWorkoutSession'>;
  localDate: string;
  onClose: () => void;
  sessionIds: readonly string[];
}) {
  const { state, reload } = useAsyncData(
    (signal) =>
      Promise.all(
        sessionIds.map((sessionId) => api.getWorkoutSession(sessionId, signal)),
      ),
    [api, sessionIds.join('|')],
  );

  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible>
      <View style={styles.backdrop}>
        <View accessibilityViewIsModal style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <View>
              <Text accessibilityRole="header" style={styles.title}>
                {localDate} 운동 기록
              </Text>
              <Text style={styles.subtitle}>
                선택한 날의 블록별 수행 기록이에요.
              </Text>
            </View>
            <Pressable
              accessibilityLabel="운동 기록 닫기"
              accessibilityRole="button"
              onPress={onClose}
              style={styles.closeButton}
            >
              <Text style={styles.closeText}>닫기</Text>
            </Pressable>
          </View>

          {state.status === 'loading' ? (
            <Text style={styles.stateText}>운동 기록을 불러오고 있어요.</Text>
          ) : state.status === 'error' ? (
            <View style={styles.stateBox}>
              <Text accessibilityRole="alert" style={styles.errorText}>
                {state.message}
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={reload}
                style={styles.retryButton}
              >
                <Text style={styles.retryText}>다시 시도</Text>
              </Pressable>
            </View>
          ) : state.data.length === 0 ? (
            <Text style={styles.stateText}>저장된 운동 기록이 없어요.</Text>
          ) : (
            <ScrollView
              contentContainerStyle={styles.list}
              showsVerticalScrollIndicator={false}
            >
              {state.data.map((session, index) => (
                <SessionDetailCard
                  key={session.session_id}
                  index={index}
                  session={session}
                />
              ))}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

function SessionDetailCard({
  index,
  session,
}: {
  index: number;
  session: WorkoutSessionDetailResponse;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle}>
          {sessionStatusLabel(session.status_code)} 운동
          {index > 0 ? ` ${index + 1}` : ''}
        </Text>
        <Text style={styles.progress}>
          {session.completed_item_count}/{session.total_item_count} 블록
        </Text>
      </View>
      <Text style={styles.meta}>
        요청 시간 {session.requested_duration_minutes}분 · 시작{' '}
        {formatTime(session.started_at)} · 종료{' '}
        {formatTime(session.finished_at)}
      </Text>
      {session.not_completed_reason_code ? (
        <Text style={styles.note}>
          미완료 사유:{' '}
          {notCompletedReasonLabel(session.not_completed_reason_code)}
        </Text>
      ) : null}
      {session.feedback ? (
        <Text style={styles.note}>
          체감 난이도 {session.feedback.perceived_difficulty_code ?? '미입력'} ·
          운동 후 불편{' '}
          {session.feedback.post_workout_discomfort_reported ? '있음' : '없음'}
        </Text>
      ) : null}
      <View style={styles.items}>
        {session.items.map((item, itemIndex) => (
          <View key={item.plan_item_id} style={styles.item}>
            <View style={styles.itemCopy}>
              <Text style={styles.itemName}>
                {itemIndex + 1}. {item.exercise_name}
              </Text>
              <Text style={styles.itemMeta}>
                {item.sets}세트 ·{' '}
                {item.reps === null
                  ? `세트당 ${item.work_seconds_per_set ?? 0}초`
                  : `${item.reps}회`}
              </Text>
            </View>
            <Text
              style={[
                styles.itemStatus,
                item.status_code === 'COMPLETED' && styles.itemStatusDone,
              ]}
            >
              {item.status_code === 'COMPLETED' ? '완료' : '미완료'}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function formatTime(value: string | null) {
  if (value === null) return '-';
  const match = /T(\d{2}):(\d{2})/.exec(value);
  return match === null ? value : `${match[1]}:${match[2]}`;
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(32, 38, 29, 0.34)',
  },
  sheet: {
    maxHeight: '82%',
    minHeight: 300,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.canvas,
    paddingTop: 10,
    paddingHorizontal: 18,
    paddingBottom: 28,
  },
  handle: {
    width: 46,
    height: 5,
    alignSelf: 'center',
    borderRadius: 999,
    backgroundColor: colors.border,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    paddingTop: 16,
    paddingBottom: 14,
  },
  title: { color: colors.text, fontSize: 20, fontWeight: '800' },
  subtitle: { marginTop: 4, color: colors.textMuted, fontSize: 12.5 },
  closeButton: {
    borderRadius: 12,
    backgroundColor: colors.surface,
    paddingVertical: 9,
    paddingHorizontal: 13,
  },
  closeText: { color: colors.textSub, fontSize: 12.5, fontWeight: '800' },
  stateBox: { gap: spacing.md },
  stateText: { color: colors.textSub, fontSize: 14, paddingVertical: 28 },
  errorText: { color: colors.dangerText, fontSize: 13, lineHeight: 19 },
  retryButton: {
    alignItems: 'center',
    borderRadius: 14,
    backgroundColor: colors.green,
    padding: 13,
  },
  retryText: { color: colors.surface, fontSize: 14, fontWeight: '800' },
  list: { gap: 12, paddingBottom: 8 },
  card: {
    ...shadows.card,
    gap: 10,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 20,
    backgroundColor: colors.surface,
    padding: 15,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  cardTitle: { color: colors.text, fontSize: 15, fontWeight: '800' },
  progress: { color: colors.greenText, fontSize: 12.5, fontWeight: '800' },
  meta: { color: colors.textMuted, fontSize: 11.5, lineHeight: 17 },
  note: {
    borderRadius: 10,
    backgroundColor: colors.surfaceAlt,
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
    padding: 10,
  },
  items: { gap: 8 },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 9,
  },
  itemCopy: { minWidth: 0, flex: 1 },
  itemName: { color: colors.text, fontSize: 13, fontWeight: '700' },
  itemMeta: { marginTop: 2, color: colors.textMuted, fontSize: 11.5 },
  itemStatus: { color: colors.textMuted, fontSize: 12, fontWeight: '800' },
  itemStatusDone: { color: colors.greenText },
});
