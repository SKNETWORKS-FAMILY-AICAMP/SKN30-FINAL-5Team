/**
 * Outcome of a finished, missed or safety-stopped session, plus feedback.
 *
 * The status shown is always the server-derived one. A safety stop uses serious
 * tone throughout, and a missed session is reported without any disappointed
 * framing.
 */

import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { notCompletedReasonLabel, sessionStatusLabel } from '../../api/labels';
import { useAsyncAction } from '../../api/useAsync';
import { MascotStage } from '../../components/brand/BrandChrome';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  SafetyNotice,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import type { SessionOutcome } from './SessionScreen';

const DIFFICULTIES = [
  { code: 'EASY' as const, label: '쉬웠어요' },
  { code: 'APPROPRIATE' as const, label: '적당했어요' },
  { code: 'HARD' as const, label: '힘들었어요' },
];

export function SessionResultScreen({
  api,
  sessionId,
  outcome,
  onDone,
}: {
  api: Api;
  sessionId: string;
  outcome: SessionOutcome;
  onDone: () => void;
}) {
  const [saved, setSaved] = useState(false);

  const feedback = useAsyncAction(
    async (difficulty: 'EASY' | 'APPROPRIATE' | 'HARD') => {
      await api.submitFeedback(sessionId, {
        difficulty_code: difficulty,
        pain_occurred: outcome.kind === 'safetyStop',
        discomforts: [],
        adverse_reaction_codes: [],
      });
      setSaved(true);
    },
  );

  if (outcome.kind === 'safetyStop') {
    return (
      <ScreenShell bands>
        <ScreenHeading title="운동을 중단했어요" onBand />
        <MascotStage
          serious
          eyebrow="안전 안내"
          title="운동을 중단했어요"
          caption="오늘은 더 이상 운동을 권하지 않아요."
        />
        <SafetyNotice title="안내" message={outcome.event.guidance} />
        <Card style={styles.card}>
          <Text style={styles.body}>
            오늘은 더 이상 운동을 권하지 않을게요. 상태가 나아지지 않으면 의료
            전문가의 확인을 받아주세요.
          </Text>
        </Card>
        <Button label="홈으로" onPress={onDone} />
      </ScreenShell>
    );
  }

  if (outcome.kind === 'notCompleted') {
    return (
      <ScreenShell bands>
        <ScreenHeading title="오늘 기록을 저장했어요" onBand />
        <MascotStage
          eyebrow="기록 완료"
          title="오늘도 확인했어요"
          caption="못 한 날도 다음 계획을 만드는 데 도움이 돼요."
        />
        <Card style={styles.card}>
          <Text style={styles.status}>
            {sessionStatusLabel(outcome.result.status_code)}
          </Text>
          <Text style={styles.body}>
            이유: {notCompletedReasonLabel(outcome.result.reason_code)}
          </Text>
          <Text style={styles.note}>
            못 한 날도 다음 계획을 만드는 데 도움이 되는 신호예요.
          </Text>
        </Card>
        <Button label="홈으로" onPress={onDone} />
      </ScreenShell>
    );
  }

  const result = outcome.result;

  return (
    <ScreenShell bands>
      <ScreenHeading
        title={
          result.status_code === 'COMPLETED'
            ? '오늘 운동을 마쳤어요'
            : '오늘 운동을 기록했어요'
        }
        onBand
      />
      <MascotStage
        eyebrow="오늘의 결과"
        art={result.status_code === 'COMPLETED' ? 'complete' : 'progress'}
        title={
          result.status_code === 'COMPLETED'
            ? '전부 해냈어요'
            : '여기까지 했어요'
        }
        caption={`블록 ${result.completed_item_count} / ${result.total_item_count} 완료`}
      />

      <Card style={styles.card}>
        <Text style={styles.status}>
          {sessionStatusLabel(result.status_code)}
        </Text>
        <Text style={styles.body}>
          블록 {result.completed_item_count} / {result.total_item_count} 완료
        </Text>
        {result.estimated_calories_burned !== null ? (
          <Text style={styles.note}>
            예상 소모 칼로리 약 {Math.round(result.estimated_calories_burned)}
            kcal (참고용 추정치)
          </Text>
        ) : null}
      </Card>

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>오늘 강도는 어땠나요?</Text>
        {saved ? (
          <InlineFeedback tone="success" message="피드백을 저장했어요." />
        ) : (
          <View style={styles.buttons}>
            {DIFFICULTIES.map((option) => (
              <Button
                key={option.code}
                label={option.label}
                tone="secondary"
                disabled={feedback.pending}
                onPress={() => void feedback.run(option.code)}
              />
            ))}
          </View>
        )}
        {feedback.error ? (
          <InlineFeedback tone="error" message={feedback.error} />
        ) : null}
      </Card>

      <Button label="홈으로" onPress={onDone} />
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  status: {
    color: colors.greenText,
    fontSize: 18,
    fontWeight: '700',
  },
  body: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  note: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  buttons: {
    gap: spacing.sm,
  },
});
