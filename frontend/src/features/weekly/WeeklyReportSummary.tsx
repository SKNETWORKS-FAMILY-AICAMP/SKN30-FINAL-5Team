import { Image, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';
import Svg, { Circle, Path } from 'react-native-svg';

import {
  adjustmentDirectionLabel,
  notCompletedReasonLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type { WeeklyReportResponse } from '../../api/types';
import { imageAssets } from '../../assets';
import { colors } from '../../components/theme';
import { CALENDAR_DAY_VISUALS } from '../home/homeSecondaryModel';
import { RestIcon } from '../home/HomeSupport';

type WeeklyReportSummaryProps = {
  report: WeeklyReportResponse;
  targetWorkoutCount: number;
};

export function WeeklyReportSummary({
  report,
  targetWorkoutCount,
}: WeeklyReportSummaryProps) {
  const safetyStoppedCount =
    report.counts.safety_stopped_session_count ??
    report.counts.stopped_for_safety;
  // Only format the server's rate; never derive it from the displayed counts.
  const progress = report.completion_rate;
  const percentFormatter = new Intl.NumberFormat('ko-KR', {
    style: 'percent',
    maximumFractionDigits: 0,
  });
  const completionLabel = percentFormatter.format(progress);
  const progressRadius = 38;
  const progressCircumference = 2 * Math.PI * progressRadius;

  return (
    <View style={styles.container} testID="weekly-report-summary">
      <ReportBlock title="목표 달성 현황">
        <View style={styles.progressRow}>
          <View
            accessibilityLabel={`목표 완료율 ${completionLabel}`}
            style={styles.progressBadge}
          >
            <Svg height={92} style={styles.progressSvg} width={92}>
              <Circle
                cx={46}
                cy={46}
                fill="none"
                r={progressRadius}
                stroke={colors.border}
                strokeWidth={7}
              />
              <Circle
                cx={46}
                cy={46}
                fill="none"
                origin="46, 46"
                r={progressRadius}
                rotation={-90}
                stroke={colors.primaryBusy}
                strokeDasharray={`${progressCircumference} ${progressCircumference}`}
                strokeDashoffset={progressCircumference * (1 - progress)}
                strokeLinecap="round"
                strokeWidth={7}
              />
            </Svg>
            <Text style={styles.progressValue}>{completionLabel}</Text>
            <Text style={styles.progressLabel}>완료율</Text>
          </View>
          <View style={styles.progressCopy}>
            <Text style={styles.metricHeadline}>
              목표 {targetWorkoutCount}회 중 완료 {report.counts.completed}회
            </Text>
            {report.completed_count_change != null ? (
              <Text style={styles.secondaryText} testID="weekly-report-delta">
                지난주보다 {formatSignedCount(report.completed_count_change)}회
              </Text>
            ) : null}
            <Text style={styles.noteText} testID="weekly-report-persistence">
              부분 수행 {report.counts.partial}회 · 부분 수행까지 포함하면{' '}
              {percentFormatter.format(report.persistence_rate)}
            </Text>
          </View>
        </View>
      </ReportBlock>

      <ReportBlock title="운동 기록 요약">
        <View style={styles.countRow}>
          <Count icon="complete" label="완료" value={report.counts.completed} />
          <Count
            icon="partial"
            label="부분 수행"
            value={report.counts.partial}
          />
          <Count
            icon="rest"
            label="휴식"
            testID="weekly-report-not-completed-count"
            value={report.counts.not_completed}
          />
          <Count
            icon="safety"
            label="안전 중단"
            testID="weekly-report-safety-stopped-count"
            value={safetyStoppedCount}
          />
        </View>
        <View style={styles.metricList} testID="weekly-report-metrics">
          {report.total_workout_seconds != null ? (
            <Metric
              icon="time"
              label="총 운동 시간"
              value={formatDuration(report.total_workout_seconds)}
            />
          ) : null}
          {report.most_performed_exercise_name != null ||
          report.most_performed_training_type_code != null ? (
            <Metric
              icon="exercise"
              label="가장 많이 한 운동"
              value={
                report.most_performed_exercise_name ??
                trainingTypeLabel(report.most_performed_training_type_code!)
              }
            />
          ) : null}
          {report.routine_difficulty_code != null ? (
            <Metric
              icon="difficulty"
              label="루틴 난이도"
              value={difficultyLabel(report.routine_difficulty_code)}
            />
          ) : null}
        </View>
      </ReportBlock>

      <ReportBlock badge="condition" title="헬끼가 확인한 점">
        <View style={styles.detailList} testID="weekly-report-observations">
          <DetailRow
            label="컨디션 변화"
            value={conditionChangeLabel(report.condition_summary)}
          />
          <DetailRow
            label="통증"
            value={painSummaryLabel(report.condition_summary)}
          />
          <DetailRow
            label="휴식·부분 수행·중단 이유"
            value={reasonSummaryLabel(report.outcome_reason_summary)}
          />
        </View>
      </ReportBlock>

      <ReportBlock badge="condition" title="이번 주 헬끼가 이렇게 조정했어요">
        <View style={styles.decisionQuote}>
          <Text style={styles.bodyText}>
            {report.adjustment_summary ?? report.decision_summary}
          </Text>
        </View>
        <View style={styles.directionCard}>
          <View style={styles.directionIcon}>
            <DirectionIcon code={report.adjustment_direction_code} />
          </View>
          <View style={styles.directionCopy}>
            <Text style={styles.directionLabel}>실제 추천 조정 방향</Text>
            <Text style={styles.directionTitle}>
              {adjustmentDirectionLabel(report.adjustment_direction_code)}
            </Text>
          </View>
        </View>
      </ReportBlock>

      <ReportBlock title="다음 주에는 이렇게 추천할게요">
        {report.next_week_recommendation ? (
          <View style={styles.detailList} testID="weekly-report-next-week">
            <DetailRow
              label="강도"
              value={report.next_week_recommendation.intensity}
            />
            <DetailRow
              label="운동량"
              value={report.next_week_recommendation.volume}
            />
            <DetailRow
              label="시간"
              value={report.next_week_recommendation.duration}
            />
            <DetailRow
              label="통증 대응"
              value={report.next_week_recommendation.pain_response}
            />
          </View>
        ) : (
          <Text style={styles.bodyText}>{report.next_action}</Text>
        )}
      </ReportBlock>

      <View style={styles.coachCard} testID="weekly-report-coach">
        <Text accessibilityRole="header" style={styles.coachTitle}>
          헬끼의 한 줄 코치
        </Text>
        <View style={styles.coachBody}>
          <Text style={styles.coachText}>
            {report.coach_message ?? report.next_action}
          </Text>
        </View>
        <Image
          accessibilityIgnoresInvertColors
          accessible={false}
          resizeMode="contain"
          source={imageAssets.mascotFeedback}
          style={styles.coachMascot}
          testID="weekly-report-coach-mascot"
        />
      </View>
    </View>
  );
}

function ReportBlock({
  badge,
  children,
  tone,
  title,
}: {
  badge?: BlockBadgeName;
  children: ReactNode;
  tone?: 'positive' | 'improvement';
  title: string;
}) {
  return (
    <View
      style={[
        styles.card,
        styles.block,
        tone === 'positive' && styles.positiveCard,
        tone === 'improvement' && styles.improvementCard,
      ]}
    >
      <View style={styles.blockHeading}>
        {badge ? <BlockBadge name={badge} /> : null}
        <Text accessibilityRole="header" style={styles.blockTitle}>
          {title}
        </Text>
      </View>
      {children}
    </View>
  );
}

type BlockBadgeName = 'good' | 'watch' | 'condition';

// Heading badges are decoration; the block title still carries the meaning.
const BLOCK_BADGES: Record<
  BlockBadgeName,
  { background: string; filled: boolean; glyph: string; stroke: string }
> = {
  good: {
    background: colors.primary,
    filled: true,
    glyph: 'M12 4.6l1.9 4.5 4.5 1.9-4.5 1.9L12 17.4l-1.9-4.5L5.6 11l4.5-1.9Z',
    stroke: colors.surface,
  },
  watch: {
    background: '#DE8B62',
    filled: false,
    glyph: 'M10.6 15.2a4.6 4.6 0 1 1 0-9.2 4.6 4.6 0 0 1 0 9.2Zm3.5-1.1L18 18',
    stroke: colors.surface,
  },
  condition: {
    background: colors.greenBand,
    filled: false,
    glyph: 'M4 12h3l2.2-4.4L12.4 16l2-4H20',
    stroke: colors.greenText,
  },
};

function BlockBadge({ name }: { name: BlockBadgeName }) {
  const badge = BLOCK_BADGES[name];
  return (
    <View
      accessible={false}
      style={[styles.blockBadge, { backgroundColor: badge.background }]}
      testID={'weekly-report-badge-' + name}
    >
      <Svg accessible={false} height={20} width={20} viewBox="0 0 24 24">
        <Path
          d={badge.glyph}
          fill={badge.filled ? badge.stroke : 'none'}
          stroke={badge.stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={badge.filled ? 1 : 2}
        />
      </Svg>
    </View>
  );
}

// Presentation-only mapping; the server still decides the direction itself.
const DIRECTION_GLYPHS: Record<string, string> = {
  INCREASE: 'M12 18V6m-5 5 5-5 5 5',
  REDUCE: 'M12 6v12m-5-5 5 5 5-5',
  DECREASE: 'M12 6v12m-5-5 5 5 5-5',
  MAINTAIN: 'M6 10h12M6 14h12',
  MIXED: 'M5 15l4-4 3 3 6-7',
};

function DirectionIcon({ code }: { code: string }) {
  return (
    <Svg
      accessible={false}
      height={22}
      width={22}
      viewBox="0 0 24 24"
      testID="weekly-report-direction-icon"
    >
      <Path
        d={DIRECTION_GLYPHS[code] ?? DIRECTION_GLYPHS.MIXED}
        fill="none"
        stroke={colors.greenText}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
      />
    </Svg>
  );
}

function Count({
  icon,
  label,
  testID,
  value,
}: {
  icon: ReportIconName;
  label: string;
  testID?: string;
  value: number;
}) {
  return (
    <View style={styles.count} testID={testID}>
      <ReportIcon name={icon} />
      <Text style={styles.countValue}>{value}</Text>
      <Text style={styles.countLabel}>{label}</Text>
    </View>
  );
}

function Metric({
  icon,
  label,
  testID,
  value,
}: {
  icon: ReportIconName;
  label: string;
  testID?: string;
  value: string;
}) {
  return (
    <View style={styles.metricRow} testID={testID}>
      <View style={styles.metricIcon}>
        <ReportIcon name={icon} />
      </View>
      <View style={styles.metricCopy}>
        <Text style={styles.metricLabel}>{label}</Text>
        <Text style={styles.metricValue}>{value}</Text>
      </View>
    </View>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.bodyText}>{value}</Text>
    </View>
  );
}

function difficultyLabel(code: 'EASY' | 'APPROPRIATE' | 'HARD'): string {
  return { EASY: '쉬움', APPROPRIATE: '적절함', HARD: '어려움' }[code];
}

function conditionChangeLabel(
  summary: WeeklyReportResponse['condition_summary'],
): string {
  if (!summary || summary.fatigue_change_code === 'INSUFFICIENT_DATA') {
    return '비교할 컨디션 기록이 충분하지 않아요.';
  }
  return {
    IMPROVED: '주 초보다 피로도가 낮아졌어요.',
    STABLE: '주 초와 주 후반의 피로도가 비슷했어요.',
    DECLINED: '주 후반에 피로도가 높아졌어요.',
  }[summary.fatigue_change_code];
}

function painSummaryLabel(
  summary: WeeklyReportResponse['condition_summary'],
): string {
  if (!summary) return '기록된 통증 정보를 확인할 수 없어요.';
  if (
    summary.pain_checkin_count === 0 &&
    summary.workout_pain_or_safety_stop_count === 0
  ) {
    return '체크인이나 운동 중 기록된 통증·이상 반응이 없어요.';
  }
  return `통증 체크인 ${summary.pain_checkin_count}회, 운동 중 통증·안전 중단 ${summary.workout_pain_or_safety_stop_count}회가 기록됐어요.`;
}

function reasonSummaryLabel(
  summary: WeeklyReportResponse['outcome_reason_summary'],
): string {
  if (!summary) return '기록된 이유가 없어요.';
  const labels = Object.values(summary).flatMap((counts) =>
    Object.entries(counts).map(
      ([code, count]) => `${reasonLabel(code)} ${count}회`,
    ),
  );
  return labels.length > 0 ? labels.join(', ') : '기록된 이유가 없어요.';
}

function reasonLabel(code: string): string {
  const stopReasons: Record<string, string> = {
    HIGH_FATIGUE: '피로로 중단',
    RESUME_LATER: '나중에 재개',
    PAIN_OR_ABNORMAL_RESPONSE: '통증·이상 반응',
  };
  return stopReasons[code] ?? notCompletedReasonLabel(code);
}

function formatSignedCount(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours === 0) return `${minutes}분`;
  if (remainingMinutes === 0) return `${hours}시간`;
  return `${hours}시간 ${remainingMinutes}분`;
}

type ReportIconName =
  | 'complete'
  | 'partial'
  | 'rest'
  | 'safety'
  | 'time'
  | 'exercise'
  | 'difficulty';

function ReportIcon({ name }: { name: ReportIconName }) {
  if (name === 'rest') {
    return (
      <RestIcon
        color={CALENDAR_DAY_VISUALS.rest.accentColor}
        size={28}
        testID="weekly-report-icon-rest"
      />
    );
  }
  if (name === 'partial') {
    const visual = CALENDAR_DAY_VISUALS.partial;
    return (
      <View
        accessible={false}
        style={[
          styles.partialIcon,
          {
            backgroundColor: visual.backgroundColor,
            borderColor: visual.borderColor,
          },
        ]}
        testID="weekly-report-partial-icon"
      >
        <Text style={[styles.partialGlyph, { color: visual.color }]}>
          {visual.glyph}
        </Text>
      </View>
    );
  }
  const paths: Record<ReportIconName, string> = {
    complete: 'M7 12l3 3 7-7',
    partial: 'M12 3v9l6 6',
    rest: '',
    safety: 'M12 6v7M12 17h0',
    time: 'M12 6v6l4 2',
    exercise: 'M3 9v6m3-9v12m0-6h12m0-6v12m3-9v6',
    difficulty: 'M5 16l4-4 3 3 7-8',
  };
  const fills: Partial<Record<ReportIconName, string>> = {
    complete: '#6DA952',
    partial: colors.primary,
    rest: '#A9A49E',
    safety: '#FCE3E7',
  };
  const fill = fills[name];
  return (
    <Svg
      accessible={false}
      height={28}
      width={28}
      viewBox="0 0 24 24"
      testID={`weekly-report-icon-${name}`}
    >
      {name !== 'exercise' && name !== 'difficulty' ? (
        <Circle
          cx={12}
          cy={12}
          r={10}
          fill={fill ?? 'none'}
          stroke={fill ?? colors.greenText}
          strokeWidth={1.8}
        />
      ) : null}
      <Path
        d={paths[name]}
        fill="none"
        stroke={
          name === 'safety'
            ? '#C45C70'
            : fill
              ? colors.surface
              : colors.greenText
        }
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

const styles = StyleSheet.create({
  container: { gap: 16 },
  block: { gap: 16, flexGrow: 1, minWidth: 0 },
  blockHeading: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  blockBadge: {
    alignItems: 'center',
    borderRadius: 999,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  blockTitle: {
    color: colors.text,
    flex: 1,
    fontSize: 17,
    fontWeight: '800',
    lineHeight: 25,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.divider,
    borderRadius: 24,
    borderWidth: 1,
    gap: 16,
    padding: 18,
  },
  progressRow: { alignItems: 'center', flexDirection: 'row', gap: 16 },
  progressBadge: {
    alignItems: 'center',
    borderRadius: 999,
    height: 92,
    justifyContent: 'center',
    position: 'relative',
    width: 92,
  },
  progressSvg: { left: 0, position: 'absolute', top: 0 },
  progressValue: { color: colors.text, fontSize: 24, fontWeight: '800' },
  progressLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
  progressCopy: { flex: 1, gap: 10, minWidth: 0 },
  metricHeadline: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 25,
  },
  secondaryText: {
    backgroundColor: colors.canvas,
    borderRadius: 12,
    padding: 10,
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 19,
  },
  countRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  count: {
    alignItems: 'center',
    backgroundColor: colors.canvas,
    borderRadius: 16,
    flex: 1,
    minWidth: 52,
    paddingHorizontal: 3,
    paddingVertical: 12,
    gap: 5,
  },
  countValue: { color: colors.text, fontSize: 22, fontWeight: '800' },
  countLabel: {
    color: colors.textSub,
    fontSize: 11,
    fontWeight: '600',
    textAlign: 'center',
  },
  metricList: {
    flexDirection: 'row',
    borderTopColor: colors.divider,
    borderTopWidth: 1,
    gap: 8,
    paddingTop: 16,
  },
  metricRow: {
    alignItems: 'center',
    flexDirection: 'column',
    gap: 6,
    flex: 1,
    minWidth: 0,
  },
  metricIcon: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: 22,
    padding: 5,
  },
  metricCopy: { gap: 4, alignSelf: 'stretch', minWidth: 0 },
  metricLabel: {
    color: colors.textSub,
    fontSize: 10,
    lineHeight: 15,
    fontWeight: '600',
    textAlign: 'center',
  },
  metricValue: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 21,
    textAlign: 'center',
  },
  detailList: { gap: 10 },
  detailRow: {
    backgroundColor: colors.canvas,
    borderRadius: 16,
    gap: 5,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  detailLabel: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 18,
  },
  reflectionRow: { gap: 12, flexDirection: 'column' },
  reflectionRowWide: { flexDirection: 'row', alignItems: 'stretch' },
  positiveCard: { backgroundColor: '#FFF5DA', borderColor: '#F4E5BD' },
  improvementCard: { backgroundColor: '#FFF0E9', borderColor: '#F1DDD2' },
  copyList: { gap: 8 },
  copyChip: {
    alignItems: 'flex-start',
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  copyMarker: {
    alignItems: 'center',
    borderRadius: 999,
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  copyContent: { flex: 1, minWidth: 0, gap: 3, paddingTop: 1 },
  noteText: { color: colors.textSub, fontSize: 12, lineHeight: 19 },
  bodyText: { color: colors.text, flexShrink: 1, fontSize: 14, lineHeight: 23 },
  decisionQuote: {
    borderLeftColor: colors.primary,
    borderLeftWidth: 3,
    borderRadius: 2,
    paddingLeft: 12,
    paddingVertical: 2,
  },
  directionCard: {
    alignItems: 'center',
    backgroundColor: colors.canvas,
    borderRadius: 16,
    flexDirection: 'row',
    gap: 12,
    padding: 15,
  },
  directionIcon: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.greenBorder,
    borderRadius: 999,
    borderWidth: 1,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  directionCopy: { flex: 1, gap: 4, minWidth: 0 },
  directionLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
  directionTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 24,
  },
  coachCard: {
    backgroundColor: colors.text,
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingVertical: 13,
    paddingRight: 88,
    gap: 5,
  },
  coachTitle: {
    color: colors.greenBand,
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 22,
  },
  coachBody: { minHeight: 40 },
  coachMascot: {
    bottom: 6,
    height: 68,
    position: 'absolute',
    right: 10,
    width: 68,
  },
  coachText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 20,
  },
  partialIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  partialGlyph: {
    fontSize: 16.8,
    lineHeight: 16.8,
    fontWeight: '800',
    textAlign: 'center',
  },
});
