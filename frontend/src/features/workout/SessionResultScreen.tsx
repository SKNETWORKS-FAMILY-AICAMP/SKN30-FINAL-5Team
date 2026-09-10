/**
 * Outcome of a finished, missed or safety-stopped session, plus feedback.
 *
 * The status shown is always the server-derived one. A safety stop uses serious
 * tone throughout, and a missed session is reported without any disappointed
 * framing.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { createIdempotencyKey } from '../../api/client';
import type { Api } from '../../api/endpoints';
import { useAsyncAction } from '../../api/useAsync';
import { MascotStage } from '../../components/brand/BrandChrome';
import {
  Card,
  GradientActionButton,
  InlineFeedback,
} from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import type { SessionOutcome } from './SessionScreen';

const DIFFICULTIES = [
  { code: 'EASY' as const, label: '쉬웠어요' },
  { code: 'APPROPRIATE' as const, label: '적당했어요' },
  { code: 'HARD' as const, label: '어려웠어요' },
];

/**
 * The two adjustment axes the next routine can lower, in the wording this app
 * shows for them.
 *
 * The codes are the contract's (`API_CONTRACT.md` 12.6), not screen-local names.
 * They used to be `FORM_DIFFICULTY` / `INTENSITY_TOO_HIGH`, which existed only
 * here and were never sent, so the answer was collected and thrown away and the
 * next routine had no axis to adjust.
 */
const HARD_DIFFICULTY_DETAILS = [
  { code: 'MOVEMENT_DIFFICULT' as const, label: '자세가 어려웠어요' },
  { code: 'VOLUME_HIGH' as const, label: '강도가 높았어요' },
];

type HardDifficultyDetailCode =
  (typeof HARD_DIFFICULTY_DETAILS)[number]['code'];

/**
 * Whether the day is recorded as rest rather than a performed session.
 *
 * A safety stop is never one of these any more. It used to be, which sent a
 * safety stop with no completed block straight home and skipped the only place
 * the user is asked how the session went -- the exact case where the answer
 * matters most. Home is still told the day is rest; the question is asked first.
 */
export function isRestOutcome(outcome: SessionOutcome): boolean {
  if (outcome.kind === 'safetyStop') return false;
  if (outcome.kind === 'stopped') return false;
  return outcome.result.status_code === 'NOT_COMPLETED';
}

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
  const resting = isRestOutcome(outcome);
  useEffect(() => {
    if (resting) onDone();
  }, [resting, onDone]);
  if (resting) return null;
  if (outcome.kind === 'stopped') {
    return (
      <ScreenShell>
        <ScreenHeading title="여기까지 기록했어요" />
        <MascotStage
          eyebrow="오늘의 기록"
          art="feedback"
          title="언제든 이어서 할 수 있어요"
          caption="홈에서 이어하기를 누르면 남은 블록부터 계속돼요."
        />
        <FeedbackCard api={api} sessionId={sessionId} onDone={onDone} />
      </ScreenShell>
    );
  }
  if (outcome.kind === 'safetyStop') {
    return (
      <ScreenShell>
        <ScreenHeading title="운동을 중단했어요" />
        <Card style={[styles.card, styles.feedbackSerious]}>
          <Text style={styles.cardTitle}>
            오늘은 운동을 더 진행하지 않는 것을 권장해요.
          </Text>
          <Text style={styles.body}>{outcome.event.guidance}</Text>
          <Text style={styles.body}>
            몸 상태를 확인하고, 불편함이 계속되면 의료 전문가의 확인을
            받아주세요.
          </Text>
          <Text style={styles.note}>진행한 운동까지 기록했어요.</Text>
        </Card>
        <FeedbackCard
          api={api}
          legacyPainOccurred
          sessionId={sessionId}
          serious
          onDone={onDone}
        />
      </ScreenShell>
    );
  }

  if (outcome.kind === 'notCompleted') return null;

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
        art="feedback"
        title={
          result.status_code === 'COMPLETED'
            ? '전부 해냈어요'
            : '여기까지 했어요'
        }
        caption={`블록 ${result.completed_item_count} / ${result.total_item_count} 완료`}
      />

      {result.estimated_calories_burned !== null ? (
        <Text style={styles.note}>
          예상 소모 칼로리 약 {Math.round(result.estimated_calories_burned)}kcal
        </Text>
      ) : null}

      <FeedbackCard api={api} sessionId={sessionId} onDone={onDone} />
    </ScreenShell>
  );
}

function FeedbackCard({
  api,
  legacyPainOccurred = false,
  onDone,
  serious = false,
  sessionId,
}: {
  api: Api;
  serious?: boolean;
  legacyPainOccurred?: boolean;
  onDone: () => void;
  sessionId: string;
}) {
  const [difficulty, setDifficulty] = useState<
    'EASY' | 'APPROPRIATE' | 'HARD' | null
  >(null);
  const [hardDifficultyDetails, setHardDifficultyDetails] = useState<
    HardDifficultyDetailCode[]
  >([]);
  const feedbackAttempt = useRef<{
    idempotencyKey: string;
    payloadFingerprint: string;
  } | null>(null);
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
    const payload = {
      difficulty_code: difficulty,
      // Only `HARD` may carry reasons; the server rejects them otherwise rather
      // than dropping them, so sending an empty list off `HARD` is deliberate.
      difficulty_reason_codes:
        difficulty === 'HARD' ? hardDifficultyDetails : [],
      fatigue_code: null,
      satisfaction_code: null,
      pain_occurred: legacyPainOccurred,
      discomforts: [],
      adverse_reaction_codes: [],
    };
    const payloadFingerprint = JSON.stringify(payload);
    if (feedbackAttempt.current?.payloadFingerprint !== payloadFingerprint) {
      feedbackAttempt.current = {
        idempotencyKey: createIdempotencyKey(),
        payloadFingerprint,
      };
    }
    const response = await api.submitFeedback(
      sessionId,
      payload,
      feedbackAttempt.current.idempotencyKey,
    );
    setSaved(true);
    setSavedGuidance(response.guidance);
    onDone();
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
      <FeedbackSection title="오늘 운동은 어땠나요?">
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
        label={feedback.pending ? '저장 중…' : '피드백 저장하고 홈으로'}
        labelStyle={styles.feedbackSubmitLabel}
        onPress={() => void feedback.run()}
        showChevron={false}
        style={styles.feedbackSubmit}
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
  feedbackSubmit: {
    height: 42,
    width: 'auto',
    minWidth: 132,
    alignSelf: 'center',
    paddingHorizontal: 24,
  },
  feedbackSubmitLabel: {
    fontSize: 14,
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
