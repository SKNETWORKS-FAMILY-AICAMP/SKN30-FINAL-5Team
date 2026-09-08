import {
  Image,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { useState, type ReactNode } from 'react';
import Svg, { Circle, Path } from 'react-native-svg';

import {
  adjustmentDirectionLabel,
  notCompletedReasonLabel,
  trainingTypeLabel,
  weekdayLabel,
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

const HIGHLIGHT_COPY: Record<string, string> = {
  COMPLETED_SESSION_RECORDED: '완료한 운동 기록을 남겼어요.',
  PARTIAL_SESSION_PROGRESS_RECORDED: '가능한 만큼 진행한 기록을 남겼어요.',
  ADJUSTED_PLAN_PROGRESS_RECORDED: '조정된 계획에서도 운동을 이어갔어요.',
};

const IMPROVEMENT_COPY: Record<string, string> = {
  SAFETY_STOPPED_SESSION_RECORDED: '안전 중단으로 마친 세션이 있어요.',
  MISSED_SESSION_PATTERN_RECORDED: '휴식 이유를 다음 주 계획에 반영해요.',
  PARTIAL_SESSION_PATTERN_RECORDED:
    '부분 수행 기록을 바탕으로 부담을 조정해요.',
};

export function WeeklyReportSummary({
  report,
  targetWorkoutCount,
}: WeeklyReportSummaryProps) {
  const safetyStoppedCount =
    report.counts.safety_stopped_session_count ??
    report.counts.stopped_for_safety;
  const { fontScale } = useWindowDimensions();
  const [width, setWidth] = useState(0);
  const roomy = width >= 600 && fontScale <= 1.2;
  const highlights = copyForCodes(report.highlight_codes, HIGHLIGHT_COPY);
  const improvements = copyForCodes(
    report.improvement_codes,
    IMPROVEMENT_COPY,
    {
      MISSED_SESSION_PATTERN_RECORDED:
        report.primary_miss_reason_code !== null
          ? `가장 잦은 이유: ${notCompletedReasonLabel(report.primary_miss_reason_code)}`
          : undefined,
    },
  );
  const weekdayFocus = mostFrequentFailureWeekday(
    report.weekday_failure_summary,
  );
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
    <View
      onLayout={({ nativeEvent }) => setWidth(nativeEvent.layout.width)}
      style={styles.container}
      testID="weekly-report-summary"
    >
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
            {report.counts.partial > 0 ? (
              <Text style={styles.noteText} testID="weekly-report-persistence">
                부분 수행까지 포함하면{' '}
                {percentFormatter.format(report.persistence_rate)}
              </Text>
            ) : null}
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
          {report.total_estimated_calories_burned != null ? (
            <Metric
              icon="calories"
              label="예상 소모 칼로리"
              testID="weekly-report-calories"
              value={`${formatNumber(report.total_estimated_calories_burned)} kcal`}
            />
          ) : null}
          {report.most_performed_training_type_code != null ? (
            <Metric
              icon="exercise"
              label="가장 많이 한 운동"
              value={trainingTypeLabel(
                report.most_performed_training_type_code,
              )}
            />
          ) : null}
        </View>
        {weekdayFocus !== null ? (
          <Text style={styles.noteText} testID="weekly-report-weekday-focus">
            미완료 기록이 가장 많은 요일은 {weekdayLabel(weekdayFocus)}이에요.
          </Text>
        ) : null}
      </ReportBlock>

      <View
        style={[styles.reflectionRow, roomy && styles.reflectionRowWide]}
        testID="weekly-report-reflections"
      >
        <ReportBlock tone="positive" title="이런 점이 좋았어요">
          <CopyList
            fallback="이번 주 기록에서 이어갈 점을 확인했어요."
            items={highlights}
          />
        </ReportBlock>

        <ReportBlock tone="improvement" title="다음 주에 살펴볼 점">
          <CopyList
            fallback="다음 주에도 실행 가능한 조건을 함께 찾아요."
            items={improvements}
          />
        </ReportBlock>
      </View>

      <ReportBlock title="이번 주 컨디션과 조정">
        <Text style={styles.bodyText}>{report.decision_summary}</Text>
        <View style={styles.directionCard}>
          <Text style={styles.directionLabel}>다음 주 방향</Text>
          <Text style={styles.directionTitle}>
            {adjustmentDirectionLabel(report.adjustment_direction_code)}
          </Text>
        </View>
      </ReportBlock>

      <View style={styles.coachCard} testID="weekly-report-coach">
        <Text accessibilityRole="header" style={styles.coachTitle}>
          헬끼의 한 줄 코치
        </Text>
        <View style={styles.coachBody}>
          <Text style={styles.coachText}>{report.next_action}</Text>
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
  children,
  tone,
  title,
}: {
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
        <Text accessibilityRole="header" style={styles.blockTitle}>
          {title}
        </Text>
      </View>
      {children}
    </View>
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

type CopyItem = { text: string; note?: string };

function CopyList({
  fallback,
  items,
}: {
  fallback: string;
  items: CopyItem[];
}) {
  const visible = items.length > 0 ? items : [{ text: fallback }];
  return (
    <View style={styles.copyList}>
      {visible.map((item) => (
        <View key={item.text} style={styles.copyRow}>
          <View style={styles.copyDot} />
          <View style={styles.copyContent}>
            <Text style={styles.bodyText}>{item.text}</Text>
            {item.note ? (
              <Text style={styles.noteText} testID="weekly-report-miss-reason">
                {item.note}
              </Text>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

function copyForCodes(
  codes: string[] | null | undefined,
  copy: Record<string, string>,
  notes: Record<string, string | undefined> = {},
): CopyItem[] {
  return (codes ?? []).flatMap((code) =>
    copy[code] ? [{ text: copy[code], note: notes[code] }] : [],
  );
}

function mostFrequentFailureWeekday(
  summary: WeeklyReportResponse['weekday_failure_summary'],
): string | null {
  let selected: string | null = null;
  let highestCount = 0;
  // Compare the supplied weekday aggregates; Monday wins equal totals.
  for (const weekday of [
    'MONDAY',
    'TUESDAY',
    'WEDNESDAY',
    'THURSDAY',
    'FRIDAY',
    'SATURDAY',
    'SUNDAY',
  ]) {
    const counts = summary[weekday];
    if (!counts) continue;
    const total =
      counts.partial + counts.not_completed + counts.stopped_for_safety;
    if (total > highestCount) {
      selected = weekday;
      highestCount = total;
    }
  }
  return selected;
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

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 }).format(
    value,
  );
}

type ReportIconName =
  'complete' | 'partial' | 'rest' | 'safety' | 'time' | 'calories' | 'exercise';

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
    calories:
      'M12 3c1 5 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 3 2 3 2 3s2-4 1-9Z',
    exercise: 'M3 9v6m3-9v12m0-6h12m0-6v12m3-9v6',
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
      {name !== 'calories' && name !== 'exercise' ? (
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
  blockHeading: { flexDirection: 'row', alignItems: 'center' },
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
  reflectionRow: { gap: 12, flexDirection: 'column' },
  reflectionRowWide: { flexDirection: 'row', alignItems: 'stretch' },
  positiveCard: { backgroundColor: '#FFF5DA', borderColor: '#F4E5BD' },
  improvementCard: { backgroundColor: '#FFF0E9', borderColor: '#F1DDD2' },
  copyList: { gap: 10 },
  copyRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 9 },
  copyContent: { flex: 1, minWidth: 0, gap: 3 },
  noteText: { color: colors.textSub, fontSize: 12, lineHeight: 19 },
  copyDot: {
    backgroundColor: colors.textSub,
    borderRadius: 3,
    height: 5,
    marginTop: 9,
    width: 5,
  },
  bodyText: { color: colors.text, flexShrink: 1, fontSize: 14, lineHeight: 23 },
  directionCard: {
    backgroundColor: colors.canvas,
    borderRadius: 16,
    gap: 6,
    padding: 15,
  },
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
