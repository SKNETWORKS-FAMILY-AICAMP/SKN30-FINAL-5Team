/**
 * Reason capture for a session the user did not perform.
 *
 * A missed workout is a learning signal, not a failure, so the copy stays
 * neutral and the reasons are the server's stable codes.
 */

import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { NOT_COMPLETED_REASON_OPTIONS } from '../../api/labels';
import type { NotCompletedReasonCode } from '../../api/types';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';

export function NotCompletedSheet({
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (reasonCode: NotCompletedReasonCode) => void;
}) {
  const [reason, setReason] = useState<NotCompletedReasonCode | null>(null);

  return (
    <Card style={styles.sheet}>
      <Text style={styles.title}>오늘 운동을 못 한 이유를 알려주세요</Text>
      <Text style={styles.body}>
        다음 주 계획을 조정하는 데 참고할게요. 기록은 평가가 아니에요.
      </Text>

      <View style={styles.list}>
        {NOT_COMPLETED_REASON_OPTIONS.map((option) => (
          <Pressable
            key={option.code}
            accessibilityRole="button"
            accessibilityState={{ selected: reason === option.code }}
            onPress={() => setReason(option.code)}
            style={[styles.row, reason === option.code && styles.rowSelected]}
          >
            <Text
              style={[
                styles.rowLabel,
                reason === option.code && styles.rowLabelSelected,
              ]}
            >
              {option.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {error ? <InlineFeedback tone="error" message={error} /> : null}

      <Button
        label={pending ? '저장 중…' : '기록하기'}
        disabled={pending || reason === null}
        onPress={() => reason && onSubmit(reason)}
      />
      <Button label="닫기" tone="secondary" onPress={onCancel} />
    </Card>
  );
}

const styles = StyleSheet.create({
  sheet: {
    gap: spacing.md,
  },
  title: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  body: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  list: {
    gap: spacing.sm,
  },
  row: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  rowSelected: {
    borderColor: colors.green,
    backgroundColor: colors.greenTint,
  },
  rowLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  rowLabelSelected: {
    color: colors.greenText,
  },
});
