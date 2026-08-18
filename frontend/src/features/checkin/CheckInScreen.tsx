/**
 * Manual daily check-in.
 *
 * This is the fallback path that must always work: the demo has no wearable
 * integration, and the contract requires a complete manual check-in to be
 * sufficient on its own. Nothing here is inferred — unset optional values stay
 * unset rather than being guessed.
 */

import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import {
  ADVERSE_REACTION_OPTIONS,
  BODY_AREA_OPTIONS,
  FATIGUE_OPTIONS,
  SEVERITY_OPTIONS,
} from '../../api/labels';
import type {
  DailyContextResponse,
  DecisionResponse,
  DiscomfortSeverityCode,
  FatigueLevelCode,
  RoutineResponse,
} from '../../api/types';
import { localDateString, useAsyncAction } from '../../api/useAsync';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';

type DiscomfortDraft = Record<string, DiscomfortSeverityCode>;

const DURATION_CHOICES = [20, 30, 40, 50];
const FALLBACK_DURATION_MINUTES = 30;

export function CheckInScreen({
  api,
  routine,
  locationCode,
  existingContext,
  onDecided,
  onCancel,
}: {
  api: Api;
  routine: RoutineResponse;
  /** Where the user is training today, from their onboarding profile. */
  locationCode: string;
  existingContext: DailyContextResponse | null;
  onDecided: (decision: DecisionResponse) => void;
  onCancel: () => void;
}) {
  const profileDuration =
    routine.days[0]?.requested_duration_minutes ?? FALLBACK_DURATION_MINUTES;

  const [fatigue, setFatigue] = useState<FatigueLevelCode>('MODERATE');
  const [duration, setDuration] = useState(profileDuration);
  const [discomforts, setDiscomforts] = useState<DiscomfortDraft>({});
  const [reactions, setReactions] = useState<string[]>([]);
  const [staleRetry, setStaleRetry] = useState(false);

  const submit = useAsyncAction(async () => {
    const localDate = localDateString();

    // Re-read the version when a previous attempt lost the optimistic-lock race,
    // so the retry carries the current one instead of the stale value.
    let expectedVersion = existingContext?.context_version;
    if (staleRetry) {
      const current = await api
        .getDailyContext(localDate)
        .catch((error: unknown) => {
          if (isApiError(error) && error.kind === 'notFound') {
            return null;
          }
          throw error;
        });
      expectedVersion = current?.context_version;
    }

    const context = await api.replaceDailyContext(
      localDate,
      {
        fatigue_level_code: fatigue,
        requested_duration_minutes: duration,
        duration_adjustment_source_code:
          duration === profileDuration ? 'PROFILE' : 'USER_OVERRIDE',
        location_code: locationCode,
        discomforts: Object.entries(discomforts).map(
          ([body_area_code, severity_code]) => ({
            body_area_code,
            severity_code,
          }),
        ),
        adverse_reaction_codes: reactions,
      },
      expectedVersion,
    );

    const decision = await api.createDecision({
      local_date: localDate,
      daily_context_id: context.id,
      expected_context_version: context.context_version,
    });
    onDecided(decision);
  });

  const onSubmit = useCallback(() => {
    void submit.run();
  }, [submit]);

  const isStale =
    isApiError(submit.lastError) && submit.lastError.kind === 'stale';

  // The server refuses rather than inventing a plan it cannot justify. Naming
  // the reason keeps that from reading as an unexplained outage.
  const rulesetUnavailable =
    isApiError(submit.lastError) &&
    submit.lastError.code === 'DECISION_FAILED' &&
    Object.values(discomforts).some((severity) => severity !== 'SEVERE');

  const toggleDiscomfort = (code: string, severity: DiscomfortSeverityCode) => {
    setDiscomforts((current) => {
      const next = { ...current };
      if (next[code] === severity) {
        delete next[code];
      } else {
        next[code] = severity;
      }
      return next;
    });
  };

  return (
    <ScreenShell>
      <ScreenHeading
        title="오늘 컨디션은 어떤가요?"
        subtitle="입력한 내용으로 오늘의 최종 루틴을 결정해요."
      />

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>피로도</Text>
        <View style={styles.chipRow}>
          {FATIGUE_OPTIONS.map((option) => (
            <Chip
              key={option.code}
              label={option.label}
              selected={fatigue === option.code}
              onPress={() => setFatigue(option.code)}
            />
          ))}
        </View>
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>오늘 가능한 운동 시간</Text>
        <View style={styles.chipRow}>
          {DURATION_CHOICES.map((minutes) => (
            <Chip
              key={minutes}
              label={`${minutes}분`}
              selected={duration === minutes}
              onPress={() => setDuration(minutes)}
            />
          ))}
        </View>
        <Text style={styles.hint}>
          시간은 그대로 두고 부담만 조절해요. 시간을 줄이려면 직접 선택해주세요.
        </Text>
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>불편한 부위 (선택)</Text>
        {/*
          The server's SafetyAgent only has approved rules for SEVERE input.
          MILD and MODERATE need per-body-area contraindication rules that have
          not been domain-reviewed, so it fails closed rather than guessing.
          Saying so here is more honest than letting the request fail silently.
        */}
        <Text style={styles.hint}>
          현재는 &apos;심함&apos;만 처리할 수 있어요. 부위별 &apos;가벼움&apos;·
          &apos;보통&apos; 판단 규칙은 아직 도메인 검수 전이라, 선택하면 추천을
          만들지 않고 중단해요.
        </Text>
        {BODY_AREA_OPTIONS.map((area) => (
          <View key={area.code} style={styles.discomfortRow}>
            <Text style={styles.areaLabel}>{area.label}</Text>
            <View style={styles.chipRow}>
              {SEVERITY_OPTIONS.map((severity) => (
                <Chip
                  key={severity.code}
                  label={severity.label}
                  selected={discomforts[area.code] === severity.code}
                  onPress={() => toggleDiscomfort(area.code, severity.code)}
                />
              ))}
            </View>
          </View>
        ))}
      </Card>

      <Card style={styles.seriousSection}>
        <Text style={styles.seriousTitle}>이런 증상이 있나요?</Text>
        <Text style={styles.seriousBody}>
          해당하는 항목이 있으면 선택해주세요. 안전을 위해 운동을 중단하도록
          안내할 수 있어요.
        </Text>
        <View style={styles.chipRow}>
          {ADVERSE_REACTION_OPTIONS.map((option) => (
            <Chip
              key={option.code}
              label={option.label}
              selected={reactions.includes(option.code)}
              onPress={() =>
                setReactions((current) =>
                  current.includes(option.code)
                    ? current.filter((code) => code !== option.code)
                    : [...current, option.code],
                )
              }
            />
          ))}
        </View>
      </Card>

      {submit.error ? (
        <InlineFeedback
          tone="error"
          message={
            isStale
              ? '체크인 정보가 변경되었습니다. 다시 시도해주세요.'
              : rulesetUnavailable
                ? "'가벼움'·'보통' 불편에 대한 검수된 안전 규칙이 아직 없어 오늘의 추천을 만들지 않았어요. 해당 선택을 해제하거나, 통증이 심하면 '심함'을 선택해주세요."
                : submit.error
          }
          action={
            isStale ? (
              <Button
                label="최신 상태로 다시 시도"
                tone="secondary"
                onPress={() => {
                  setStaleRetry(true);
                  void submit.run();
                }}
              />
            ) : undefined
          }
        />
      ) : null}

      <Button
        label={submit.pending ? '결정하는 중…' : '오늘의 루틴 받기'}
        disabled={submit.pending}
        onPress={onSubmit}
      />
      <Button label="돌아가기" tone="secondary" onPress={onCancel} />
    </ScreenShell>
  );
}

function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: spacing.md,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  seriousSection: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.warningBorder,
    backgroundColor: colors.warningSurface,
  },
  seriousTitle: {
    color: colors.warningText,
    fontSize: 15,
    fontWeight: '700',
  },
  seriousBody: {
    color: colors.warningText,
    fontSize: 13,
    lineHeight: 19,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  chipSelected: {
    borderColor: colors.green,
    backgroundColor: colors.greenTint,
  },
  chipLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  chipLabelSelected: {
    color: colors.greenText,
  },
  discomfortRow: {
    gap: spacing.sm,
  },
  areaLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  hint: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
});
