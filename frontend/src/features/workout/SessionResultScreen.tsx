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
import {
  ADVERSE_REACTION_OPTIONS,
  BODY_AREA_OPTIONS,
  notCompletedReasonLabel,
  sessionStatusLabel,
} from '../../api/labels';
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

const FATIGUES = [
  { code: 'LOW', label: '낮아요' },
  { code: 'MODERATE', label: '보통이에요' },
  { code: 'HIGH', label: '높아요' },
] as const;

const SATISFACTIONS = [
  { code: 'DISSATISFIED', label: '아쉬워요' },
  { code: 'NEUTRAL', label: '보통이에요' },
  { code: 'SATISFIED', label: '만족해요' },
] as const;

const DISCOMFORT_SEVERITIES = [
  { code: 'MILD', label: '가벼움' },
  { code: 'MODERATE', label: '중간' },
  { code: 'SEVERE', label: '심함' },
] as const;

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
        <FeedbackCard api={api} defaultPain sessionId={sessionId} serious />
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
  defaultPain = false,
  serious = false,
  sessionId,
}: {
  api: Api;
  defaultPain?: boolean;
  serious?: boolean;
  sessionId: string;
}) {
  const [difficulty, setDifficulty] = useState<
    'EASY' | 'APPROPRIATE' | 'HARD' | null
  >(null);
  const [fatigue, setFatigue] = useState<string | null>(null);
  const [satisfaction, setSatisfaction] = useState<string | null>(null);
  const [painOccurred, setPainOccurred] = useState(defaultPain);
  const [bodyAreaSeverities, setBodyAreaSeverities] = useState<
    Readonly<Record<string, string>>
  >({});
  const [reactions, setReactions] = useState<readonly string[]>([]);
  const [saved, setSaved] = useState(false);
  const [savedGuidance, setSavedGuidance] = useState<string | null>(null);

  const feedback = useAsyncAction(async () => {
    if (difficulty === null) return;
    const response = await api.submitFeedback(sessionId, {
      difficulty_code: difficulty,
      fatigue_code: fatigue,
      satisfaction_code: satisfaction,
      pain_occurred: painOccurred,
      discomforts: Object.entries(bodyAreaSeverities).map(
        ([bodyAreaCode, severityCode]) => ({
          body_area_code: bodyAreaCode,
          severity_code: severityCode,
        }),
      ),
      adverse_reaction_codes: [...reactions],
    });
    setSaved(true);
    setSavedGuidance(response.guidance);
  });

  const toggleBodyArea = (code: string) => {
    setBodyAreaSeverities((current) => {
      if (current[code] !== undefined) {
        const remaining = { ...current };
        delete remaining[code];
        return remaining;
      }
      return { ...current, [code]: 'MODERATE' };
    });
  };
  const toggleReaction = (code: string) => {
    setReactions((current) =>
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code],
    );
  };

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
      <Text style={styles.cardTitle}>오늘 운동은 어땠나요?</Text>
      <FeedbackSection title="체감 난이도 (필수)">
        {DIFFICULTIES.map((option) => (
          <FeedbackChoice
            key={option.code}
            label={option.label}
            onPress={() => setDifficulty(option.code)}
            selected={difficulty === option.code}
          />
        ))}
      </FeedbackSection>
      <FeedbackSection title="피로도">
        {FATIGUES.map((option) => (
          <FeedbackChoice
            key={option.code}
            label={option.label}
            onPress={() => setFatigue(option.code)}
            selected={fatigue === option.code}
          />
        ))}
      </FeedbackSection>
      <FeedbackSection title="만족도">
        {SATISFACTIONS.map((option) => (
          <FeedbackChoice
            key={option.code}
            label={option.label}
            onPress={() => setSatisfaction(option.code)}
            selected={satisfaction === option.code}
          />
        ))}
      </FeedbackSection>
      <FeedbackSection title="운동 후 통증">
        <FeedbackChoice
          label="없어요"
          onPress={() => {
            setPainOccurred(false);
            setBodyAreaSeverities({});
          }}
          selected={!painOccurred}
        />
        <FeedbackChoice
          label="있어요"
          onPress={() => setPainOccurred(true)}
          selected={painOccurred}
        />
      </FeedbackSection>
      {painOccurred ? (
        <>
          <FeedbackSection multiple title="불편한 부위">
            {BODY_AREA_OPTIONS.map((option) => (
              <FeedbackChoice
                key={option.code}
                label={option.label}
                multiple
                onPress={() => toggleBodyArea(option.code)}
                selected={bodyAreaSeverities[option.code] !== undefined}
              />
            ))}
          </FeedbackSection>
          {Object.keys(bodyAreaSeverities).map((bodyAreaCode) => {
            const bodyArea = BODY_AREA_OPTIONS.find(
              (option) => option.code === bodyAreaCode,
            );
            return (
              <FeedbackSection
                key={bodyAreaCode}
                title={`${bodyArea?.label ?? bodyAreaCode} 불편함 정도`}
              >
                {DISCOMFORT_SEVERITIES.map((option) => (
                  <FeedbackChoice
                    key={option.code}
                    accessibilityLabel={`${bodyArea?.label ?? bodyAreaCode} ${option.label}`}
                    label={option.label}
                    onPress={() =>
                      setBodyAreaSeverities((current) => ({
                        ...current,
                        [bodyAreaCode]: option.code,
                      }))
                    }
                    selected={bodyAreaSeverities[bodyAreaCode] === option.code}
                  />
                ))}
              </FeedbackSection>
            );
          })}
        </>
      ) : null}
      <FeedbackSection multiple title="이상 반응">
        {ADVERSE_REACTION_OPTIONS.map((option) => (
          <FeedbackChoice
            key={option.code}
            label={option.label}
            multiple
            onPress={() => toggleReaction(option.code)}
            selected={reactions.includes(option.code)}
          />
        ))}
      </FeedbackSection>
      {feedback.error ? (
        <InlineFeedback tone="error" message={feedback.error} />
      ) : null}
      <Button
        label={feedback.pending ? '저장 중…' : '피드백 저장'}
        disabled={feedback.pending || difficulty === null}
        onPress={() => void feedback.run()}
      />
    </Card>
  );
}

function FeedbackSection({
  children,
  title,
}: {
  children: ReactNode;
  multiple?: boolean;
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
  accessibilityLabel,
  label,
  multiple = false,
  onPress,
  selected,
}: {
  accessibilityLabel?: string;
  label: string;
  multiple?: boolean;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={multiple ? 'checkbox' : 'radio'}
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
