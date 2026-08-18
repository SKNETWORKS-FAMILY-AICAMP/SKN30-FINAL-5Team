/**
 * The server's final recommendation for today.
 *
 * Invariants this screen renders rather than re-derives:
 *
 * - one final routine, plus an optional REST opt-out; internal candidates and
 *   "lighter/original" alternatives are never shown as plan choices
 * - a safety veto (`BLOCKED`) has no plan and cannot be overridden here; the
 *   only thing the user can do is acknowledge or take the REST option
 * - `STOP_AND_SEEK_HELP` shows a serious screen with no options and no mascot
 * - options the server marked non-selectable stay disabled
 */

import { StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  actionDescription,
  actionLabel,
  agentTypeLabel,
  bodyFocusLabel,
  formatMinutes,
  trainingTypeLabel,
} from '../../api/labels';
import type {
  DecisionResponse,
  DecisionSelectionResponse,
} from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import { MascotStage } from '../../components/brand/BrandChrome';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  SafetyNotice,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';

export function DecisionScreen({
  api,
  decision,
  onSessionStarted,
  onRestChosen,
  onBack,
}: {
  api: Api;
  decision: DecisionResponse;
  onSessionStarted: (
    selection: DecisionSelectionResponse,
    decision: DecisionResponse,
  ) => void;
  onRestChosen: () => void;
  onBack: () => void;
}) {
  const select = useAsyncAction(async (optionId: string) => {
    const selection = await api.selectOption(decision.decision_id, optionId);
    if (selection.workout_session === null) {
      onRestChosen();
      return;
    }
    onSessionStarted(selection, decision);
  });

  const isSerious = decision.action_code === 'STOP_AND_SEEK_HELP';
  const isBlocked = decision.safety_status_code === 'BLOCKED';
  const plan = decision.final_plan;

  return (
    <ScreenShell bands>
      <ScreenHeading
        title={isSerious ? '운동을 중단해주세요' : '오늘의 추천'}
        subtitle={isSerious ? undefined : decision.summary}
        onBand
      />

      {/* A serious action drops the playful mascot entirely. */}
      <MascotStage
        serious={isSerious || isBlocked}
        eyebrow={isSerious ? '안전 안내' : '오늘의 결정'}
        title={
          isSerious
            ? '운동을 멈춰주세요'
            : isBlocked
              ? '오늘은 회복을 권해요'
              : actionLabel(decision.action_code)
        }
        caption={
          isSerious
            ? '안내를 확인하고 도움을 받아주세요.'
            : isBlocked
              ? '안전 기준에 따라 운동 계획을 제공하지 않아요.'
              : actionDescription(decision.action_code)
        }
      />

      {decision.guidance ? (
        decision.guidance.tone_code === 'SERIOUS' ? (
          <SafetyNotice
            title={decision.guidance.title}
            message={decision.guidance.message}
          />
        ) : (
          <InlineFeedback
            tone="warning"
            message={`${decision.guidance.title} ${decision.guidance.message}`}
          />
        )
      ) : null}

      {plan !== null ? (
        <Card style={styles.card}>
          <View style={styles.badgeRow}>
            <Text style={styles.badge}>
              {actionLabel(decision.action_code)}
            </Text>
          </View>
          <Text style={styles.cardTitle}>
            {trainingTypeLabel(plan.training_type_code)}
            {plan.body_focus_code
              ? ` · ${bodyFocusLabel(plan.body_focus_code)}`
              : ''}
          </Text>
          <Text style={styles.cardBody}>
            {actionDescription(decision.action_code)}
          </Text>
          <Text style={styles.meta}>
            요청 {plan.requested_duration_minutes}분 · 예상{' '}
            {formatMinutes(plan.estimated_duration_seconds)} · 블록{' '}
            {plan.items.length}개
          </Text>

          <View style={styles.blockList}>
            {plan.items.map((item) => (
              <View key={item.plan_item_id} style={styles.blockRow}>
                <Text style={styles.blockName}>
                  {item.sequence}. {item.exercise_name}
                </Text>
                <Text style={styles.blockMeta}>
                  {item.sets}세트
                  {item.reps === null
                    ? ` · ${item.work_seconds}초`
                    : ` × ${item.reps}회`}
                </Text>
              </View>
            ))}
          </View>
        </Card>
      ) : null}

      {isBlocked && plan === null && !isSerious ? (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>
            오늘은 운동 계획을 제공하지 않아요
          </Text>
          <Text style={styles.cardBody}>
            안전 기준에 따라 오늘은 운동 대신 회복을 권해요. 이 판단은 앱에서
            해제할 수 없어요.
          </Text>
        </Card>
      ) : null}

      {decision.public_agent_summaries &&
      decision.public_agent_summaries.length > 0 ? (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>이렇게 결정했어요</Text>
          {decision.public_agent_summaries.map((summary) => (
            <View key={summary.agent_type_code} style={styles.agentRow}>
              <Text style={styles.agentName}>
                {agentTypeLabel(summary.agent_type_code)}
              </Text>
              <Text style={styles.agentSummary}>{summary.summary}</Text>
            </View>
          ))}
        </Card>
      ) : null}

      {select.error ? (
        <InlineFeedback tone="error" message={select.error} />
      ) : null}

      {decision.options.length === 0 ? (
        <Button label="확인했어요" tone="secondary" onPress={onBack} />
      ) : (
        <View style={styles.actions}>
          {decision.options.map((option) => (
            <View key={option.option_id} style={styles.optionGroup}>
              <Button
                label={
                  option.option_code === 'REST'
                    ? '오늘은 쉬기'
                    : select.pending
                      ? '준비 중…'
                      : '이 루틴으로 운동 시작'
                }
                tone={option.option_code === 'REST' ? 'secondary' : 'primary'}
                disabled={!option.selectable || select.pending}
                onPress={() => void select.run(option.option_id)}
              />
              {!option.selectable ? (
                <Text style={styles.disabledNote}>
                  지금은 선택할 수 없는 옵션이에요
                  {option.blocked_reason_code
                    ? ` (${option.blocked_reason_code})`
                    : ''}
                  .
                </Text>
              ) : null}
            </View>
          ))}
          <Button label="돌아가기" tone="secondary" onPress={onBack} />
        </View>
      )}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md,
  },
  badgeRow: {
    flexDirection: 'row',
  },
  badge: {
    overflow: 'hidden',
    borderRadius: radii.feedback,
    backgroundColor: colors.greenBand,
    paddingHorizontal: 10,
    paddingVertical: 5,
    color: colors.primary,
    fontSize: 12,
    fontWeight: '700',
  },
  cardTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  cardBody: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  meta: {
    color: colors.textMuted,
    fontSize: 12,
  },
  blockList: {
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: spacing.md,
  },
  blockRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  blockName: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
  },
  blockMeta: {
    color: colors.textMuted,
    fontSize: 12,
  },
  agentRow: {
    gap: 3,
  },
  agentName: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
  },
  agentSummary: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  actions: {
    gap: spacing.sm,
  },
  optionGroup: {
    gap: 5,
  },
  disabledNote: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
});
