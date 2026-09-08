import { Image, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';
import Svg, { Circle } from 'react-native-svg';

import { adjustmentDirectionLabel, trainingTypeLabel } from '../../api/labels';
import type { WeeklyReportResponse } from '../../api/types';
import { imageAssets } from '../../assets';
import { colors } from '../../components/theme';

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
  SAFETY_STOPPED_SESSION_RECORDED:
    '안전 중단 기록을 다음 계획 전에 다시 확인해요.',
  MISSED_SESSION_PATTERN_RECORDED: '미수행 이유를 다음 주 계획에 반영해요.',
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
  const safetyStopped = safetyStoppedCount > 0;
  const highlights = copyForCodes(report.highlight_codes, HIGHLIGHT_COPY);
  const improvements = copyForCodes(report.improvement_codes, IMPROVEMENT_COPY);
  const progress = Math.max(0, Math.min(1, report.completion_rate));
  const progressRadius = 38;
  const progressCircumference = 2 * Math.PI * progressRadius;

  return (
    <View style={styles.container} testID="weekly-report-summary">
      <View style={[styles.card, styles.heroCard]}>
        <View style={styles.heroCopy}>
          <Text style={styles.eyebrow}>한 주 돌아보기</Text>
          <Text accessibilityRole="header" style={styles.heroTitle}>
            {report.summary}
          </Text>
        </View>
        <View style={styles.heroMascotArea}>
          <View style={styles.speechBubble}>
            <Text style={styles.speechBubbleText}>
              이번 주도{'\n'}수고했어요!
            </Text>
            <View style={styles.speechTail} />
          </View>
          <Image
            accessibilityIgnoresInvertColors
            accessibilityLabel="응원하는 끼끼"
            resizeMode="contain"
            source={imageAssets.weeklyProgressComplete}
            style={styles.heroMascot}
          />
        </View>
      </View>

      <ReportBlock index="1" title="목표 달성 현황">
        <View style={styles.progressRow}>
          <View
            accessibilityLabel={`목표 완료율 ${Math.round(progress * 100)}퍼센트`}
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
            <Text style={styles.progressValue}>
              {Math.round(progress * 100)}%
            </Text>
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
          </View>
        </View>
      </ReportBlock>

      <ReportBlock index="2" title="운동 기록 요약">
        <View style={styles.countRow}>
          <Count label="완료" value={report.counts.completed} />
          <Count label="부분 수행" value={report.counts.partial} />
          <Count
            label="미수행"
            testID="weekly-report-not-completed-count"
            value={report.counts.not_completed}
          />
          <Count
            emphasis={safetyStopped}
            label="운동 중 안전 중단"
            testID="weekly-report-safety-stopped-count"
            value={safetyStoppedCount}
          />
        </View>
        <View style={styles.metricList}>
          {report.total_workout_seconds != null ? (
            <Metric
              label="총 운동 시간"
              value={formatDuration(report.total_workout_seconds)}
            />
          ) : null}
          {report.total_estimated_calories_burned != null ? (
            <Metric
              label="예상 소모 칼로리"
              testID="weekly-report-calories"
              value={`${formatNumber(report.total_estimated_calories_burned)} kcal`}
            />
          ) : null}
          {report.average_intensity_code != null ? (
            <Metric
              label="평균 강도"
              value={intensityLabel(report.average_intensity_code)}
            />
          ) : null}
          {report.most_performed_training_type_code != null ? (
            <Metric
              label="가장 많이 한 운동"
              value={trainingTypeLabel(
                report.most_performed_training_type_code,
              )}
            />
          ) : null}
        </View>
      </ReportBlock>

      <ReportBlock index="3" title="이런 점이 좋았어요">
        <CopyList
          fallback="이번 주 기록에서 이어갈 점을 확인했어요."
          items={highlights}
        />
      </ReportBlock>

      <ReportBlock index="4" title="이런 점은 조금 아쉬웠어요">
        <CopyList
          fallback="다음 주에도 실행 가능한 조건을 함께 찾아요."
          items={improvements}
          serious={safetyStopped}
        />
      </ReportBlock>

      <ReportBlock index="5" title="이번 주 컨디션과 조정">
        <Text style={styles.bodyText}>{report.decision_summary}</Text>
        <View style={styles.directionCard}>
          <Text style={styles.directionLabel}>다음 주 방향</Text>
          <Text style={styles.directionTitle}>
            {adjustmentDirectionLabel(report.adjustment_direction_code)}
          </Text>
          <Text style={styles.bodyText}>{report.next_action}</Text>
        </View>
      </ReportBlock>

      <ReportBlock index="6" title="헬끼의 한 줄 코치">
        <View style={styles.coachBody}>
          <Text style={styles.coachText}>{report.next_action}</Text>
          <Image
            accessibilityIgnoresInvertColors
            accessible={false}
            resizeMode="contain"
            source={imageAssets.mascotFeedback}
            style={styles.coachMascot}
          />
        </View>
      </ReportBlock>
    </View>
  );
}

function ReportBlock({
  children,
  index,
  title,
}: {
  children: ReactNode;
  index: string;
  title: string;
}) {
  return (
    <View style={styles.block}>
      <View style={styles.blockHeading}>
        <View style={styles.blockIndex}>
          <Text style={styles.blockIndexText}>{index}</Text>
        </View>
        <Text accessibilityRole="header" style={styles.blockTitle}>
          {title}
        </Text>
      </View>
      <View style={styles.card}>{children}</View>
    </View>
  );
}

function Count({
  emphasis = false,
  label,
  testID,
  value,
}: {
  emphasis?: boolean;
  label: string;
  testID?: string;
  value: number;
}) {
  return (
    <View
      style={[styles.count, emphasis && styles.countSerious]}
      testID={testID}
    >
      <Text style={[styles.countValue, emphasis && styles.countValueSerious]}>
        {value}
      </Text>
      <Text style={styles.countLabel}>{label}</Text>
    </View>
  );
}

function Metric({
  label,
  testID,
  value,
}: {
  label: string;
  testID?: string;
  value: string;
}) {
  return (
    <View style={styles.metricRow} testID={testID}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function CopyList({
  fallback,
  items,
  serious = false,
}: {
  fallback: string;
  items: string[];
  serious?: boolean;
}) {
  const visible = items.length > 0 ? items : [fallback];
  return (
    <View style={styles.copyList}>
      {visible.map((item) => (
        <View key={item} style={styles.copyRow}>
          <View style={[styles.copyDot, serious && styles.copyDotSerious]} />
          <Text style={[styles.bodyText, serious && styles.safetyBody]}>
            {item}
          </Text>
        </View>
      ))}
    </View>
  );
}

function copyForCodes(
  codes: string[] | null | undefined,
  copy: Record<string, string>,
): string[] {
  return (codes ?? []).flatMap((code) => (copy[code] ? [copy[code]] : []));
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

function intensityLabel(code: string): string {
  const labels: Record<string, string> = {
    LOW: '낮음',
    MODERATE: '보통',
    HIGH: '높음',
  };
  return labels[code] ?? '확인되지 않은 항목';
}

const styles = StyleSheet.create({
  container: { gap: 22 },
  block: { gap: 10 },
  blockHeading: { alignItems: 'center', flexDirection: 'row', gap: 9 },
  blockIndex: {
    alignItems: 'center',
    backgroundColor: colors.text,
    borderRadius: 12,
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  blockIndexText: { color: colors.surface, fontSize: 12, fontWeight: '900' },
  blockTitle: { color: colors.text, flex: 1, fontSize: 17, fontWeight: '900' },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    gap: 16,
    padding: 18,
  },
  heroCard: { alignItems: 'center', flexDirection: 'row', gap: 14 },
  heroMascotArea: { alignItems: 'center', gap: 10, width: 116 },
  heroMascot: { height: 96, width: 96 },
  speechBubble: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  speechBubbleText: {
    color: colors.text,
    fontSize: 11.5,
    fontWeight: '700',
    lineHeight: 16,
    textAlign: 'center',
  },
  speechTail: {
    borderLeftColor: 'transparent',
    borderLeftWidth: 7,
    borderRightColor: 'transparent',
    borderRightWidth: 7,
    borderTopColor: colors.surface,
    borderTopWidth: 8,
    bottom: -8,
    height: 0,
    left: '50%',
    marginLeft: -7,
    position: 'absolute',
    width: 0,
  },
  heroCopy: { flex: 1, gap: 6 },
  safetyBody: {
    color: colors.danger,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 21,
  },
  eyebrow: { color: colors.greenText, fontSize: 12, fontWeight: '900' },
  heroTitle: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '900',
    lineHeight: 28,
  },
  progressRow: { alignItems: 'center', flexDirection: 'row', gap: 16 },
  progressBadge: {
    alignItems: 'center',
    backgroundColor: colors.greenBand,
    borderRadius: 999,
    height: 92,
    justifyContent: 'center',
    position: 'relative',
    width: 92,
  },
  progressSvg: { left: 0, position: 'absolute', top: 0 },
  progressValue: { color: colors.greenText, fontSize: 24, fontWeight: '900' },
  progressLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
  progressCopy: { flex: 1, gap: 6 },
  metricHeadline: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '900',
    lineHeight: 24,
  },
  secondaryText: { color: colors.textMuted, fontSize: 13, fontWeight: '700' },
  countRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  count: {
    alignItems: 'center',
    backgroundColor: colors.surfaceAlt,
    borderRadius: 14,
    flexGrow: 1,
    minWidth: 66,
    paddingHorizontal: 10,
    paddingVertical: 12,
  },
  countSerious: { backgroundColor: colors.dangerSurface },
  countValue: { color: colors.text, fontSize: 20, fontWeight: '900' },
  countValueSerious: { color: colors.danger },
  countLabel: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  metricList: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: 12,
    paddingTop: 14,
  },
  metricRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  metricLabel: {
    color: colors.textMuted,
    flex: 1,
    fontSize: 13,
    fontWeight: '700',
  },
  metricValue: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '900',
    textAlign: 'right',
  },
  copyList: { gap: 12 },
  copyRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 10 },
  copyDot: {
    backgroundColor: colors.primaryBusy,
    borderRadius: 4,
    height: 8,
    marginTop: 6,
    width: 8,
  },
  copyDotSerious: { backgroundColor: colors.danger },
  bodyText: { color: colors.text, flex: 1, fontSize: 14, lineHeight: 22 },
  directionCard: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: 16,
    gap: 6,
    padding: 15,
  },
  directionLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '800' },
  directionTitle: { color: colors.text, fontSize: 17, fontWeight: '900' },
  coachBody: { minHeight: 84, paddingRight: 96, position: 'relative' },
  coachMascot: {
    bottom: -4,
    height: 84,
    position: 'absolute',
    right: 8,
    width: 92,
  },
  coachText: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
    lineHeight: 26,
  },
});
