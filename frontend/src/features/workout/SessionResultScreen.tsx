/**
 * Outcome of a finished, missed or safety-stopped session, plus feedback.
 *
 * The status shown is always the server-derived one. A safety stop uses serious
 * tone throughout, and a missed session is reported without any disappointed
 * framing.
 */

import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { notCompletedReasonLabel, sessionStatusLabel } from '../../api/labels';
import { useAsyncAction } from '../../api/useAsync';
import { MascotStage } from '../../components/brand/BrandChrome';
import {
  Button,
  Card,
  GradientActionButton,
  InlineFeedback,
} from '../../components/primitives';
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
  { code: 'HARD' as const, label: '어려워요' },
];

const HARD_DIFFICULTY_DETAILS = [
  { code: 'FORM_DIFFICULTY' as const, label: '자세가 어려웠어요' },
  { code: 'INTENSITY_TOO_HIGH' as const, label: '강도가 높았어요' },
];

type HardDifficultyDetailCode =
  (typeof HARD_DIFFICULTY_DETAILS)[number]['code'];

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
  if (outcome.kind === 'safetyStop') {
    return (
      <ScreenShell>
        <ScreenHeading title="운동을 중단했어요" />
        <MascotStage
          serious
          eyebrow="안전 안내"
          title="운동을 중단했어요"
          caption="오늘은 더 이상 운동을 권하지 않아요."
        />
        <SafetyNotice title="안내" message={outcome.event.guidance} />
        <Card style={styles.card}>
          <Text style={styles.status}>
            {sessionStatusLabel(outcome.event.completion_code)}
          </Text>
          <Text style={styles.body}>
            오늘은 더 이상 운동을 권하지 않을게요. 상태가 나아지지 않으면 의료
            전문가의 확인을 받아주세요.
          </Text>
        </Card>
        <FeedbackCard
          api={api}
          legacyPainOccurred
          sessionId={sessionId}
          serious
        />
        <Button label="홈으로" onPress={onDone} />
      </ScreenShell>
    );
  }

  if (outcome.kind === 'notCompleted') {
    return (
      <ScreenShell>
        <ScreenHeading title="오늘 기록을 저장했어요" />
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
        <FeedbackCard api={api} sessionId={sessionId} />
        <Button label="홈으로" onPress={onDone} />
      </ScreenShell>
    );
  }

  const result = outcome.result;

  return (
    <ScreenShell>
      <ScreenHeading
        title={
          result.status_code === 'COMPLETED'
            ? '오늘 운동을 마쳤어요'
            : '오늘 운동을 기록했어요'
        }
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

      <FeedbackCard api={api} sessionId={sessionId} />

      <Button label="홈으로" onPress={onDone} />
    </ScreenShell>
  );
}

function FeedbackCard({
  api,
  legacyPainOccurred = false,
  serious = false,
  sessionId,
}: {
  api: Api;
  legacyPainOccurred?: boolean;
  serious?: boolean;
  sessionId: string;
}) {
  const [difficulty, setDifficulty] = useState<
    'EASY' | 'APPROPRIATE' | 'HARD' | null
  >(null);
  const [hardDifficultyDetails, setHardDifficultyDetails] = useState<
    HardDifficultyDetailCode[]
  >([]);
  const [saved, setSaved] = useState(false);
  const [savedGuidance, setSavedGuidance] = useState<string | null>(null);

  const selectDifficulty = (code: 'EASY' | 'APPROPRIATE' | 'HARD') => {
    setDifficulty(code);
    if (code !== 'HARD') {
      setHardDifficultyDetails([]);
    }
  };

  const toggleHardDifficultyDetail = (code: HardDifficultyDetailCode) => {
    setHardDifficultyDetails((current) =>
      current.includes(code)
        ? current.filter((value) => value !== code)
        : [...current, code],
    );
  };

  const feedback = useAsyncAction(async () => {
    if (difficulty === null) return;
    const response = await api.submitFeedback(sessionId, {
      difficulty_code: difficulty,
      fatigue_code: null,
      satisfaction_code: null,
      pain_occurred: legacyPainOccurred,
      discomforts: [],
      adverse_reaction_codes: [],
    });
    setSaved(true);
    setSavedGuidance(response.guidance);
  });

  if (saved) {
    return (
      <Card style={[styles.card, serious && styles.feedbackSerious]}>
        <InlineFeedback tone="success" message="피드백을 저장했어요." />
        {savedGuidance ? (
          <InlineFeedback tone="warning" message={savedGuidance} />
        ) : null}
      </Card>
    );
  }

  return (
    <Card style={[styles.card, serious && styles.feedbackSerious]}>
      <Text style={styles.cardTitle}>오늘 운동 체감 난이도</Text>
      <FeedbackSection title="체감 난이도 (필수)">
        {DIFFICULTIES.map((option) => (
          <FeedbackChoice
            key={option.code}
            label={option.label}
            onPress={() => selectDifficulty(option.code)}
            selected={difficulty === option.code}
          />
        ))}
      </FeedbackSection>
      {difficulty === 'HARD' ? (
        <FeedbackSection title="어떤 점이 어려웠나요? (복수 선택)">
          <Text style={styles.feedbackHelp}>
            하나 이상 선택해 주세요. 두 항목 모두 선택할 수 있어요.
          </Text>
          {HARD_DIFFICULTY_DETAILS.map((option) => (
            <DifficultyDetailChoice
              key={option.code}
              label={option.label}
              onPress={() => toggleHardDifficultyDetail(option.code)}
              selected={hardDifficultyDetails.includes(option.code)}
            />
          ))}
        </FeedbackSection>
      ) : null}
      {feedback.error ? (
        <InlineFeedback tone="error" message={feedback.error} />
      ) : null}
      <GradientActionButton
        disabled={
          feedback.pending ||
          difficulty === null ||
          (difficulty === 'HARD' && hardDifficultyDetails.length === 0)
        }
        label={feedback.pending ? '저장 중…' : '피드백 저장'}
        onPress={() => void feedback.run()}
        showChevron={false}
        testID="session-feedback-save"
      />
    </Card>
  );
}

function FeedbackSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <View style={styles.feedbackSection}>
      <Text style={styles.feedbackLabel}>{title}</Text>
      <View style={styles.feedbackChoices}>{children}</View>
    </View>
  );
}

function FeedbackChoice({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.feedbackChoice, selected && styles.feedbackChoiceSelected]}
    >
      <Text
        style={[
          styles.feedbackChoiceText,
          selected && styles.feedbackChoiceTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function DifficultyDetailChoice({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[
        styles.difficultyDetailChoice,
        selected && styles.difficultyDetailChoiceSelected,
      ]}
    >
      <View
        style={[
          styles.difficultyDetailCheck,
          selected && styles.difficultyDetailCheckSelected,
        ]}
      >
        <Text style={styles.difficultyDetailCheckText}>
          {selected ? '✓' : ''}
        </Text>
      </View>
      <Text
        style={[
          styles.difficultyDetailText,
          selected && styles.difficultyDetailTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
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
  feedbackSerious: {
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
  },
  feedbackSection: { gap: 8 },
  feedbackLabel: {
    color: colors.textSub,
    fontSize: 12.5,
    fontWeight: '800',
  },
  feedbackHelp: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  feedbackChoices: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  feedbackChoice: {
    minHeight: 40,
    minWidth: 84,
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 10,
  },
  feedbackChoiceSelected: {
    borderColor: colors.green,
    backgroundColor: colors.green,
  },
  feedbackChoiceText: { color: colors.text, fontSize: 12.5, fontWeight: '700' },
  feedbackChoiceTextSelected: { color: colors.surface },
  difficultyDetailChoice: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  difficultyDetailChoiceSelected: {
    borderColor: colors.green,
    backgroundColor: colors.greenTint,
  },
  difficultyDetailCheck: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 6,
    backgroundColor: colors.surface,
  },
  difficultyDetailCheckSelected: {
    borderColor: colors.green,
    backgroundColor: colors.green,
  },
  difficultyDetailCheckText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: '900',
  },
  difficultyDetailText: {
    flex: 1,
    color: colors.text,
    fontSize: 13,
    fontWeight: '700',
  },
  difficultyDetailTextSelected: { color: colors.greenText },
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
