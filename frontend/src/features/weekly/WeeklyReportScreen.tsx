/**
 * API-backed weekly report presented as a child of the report calendar.
 *
 * The server remains responsible for deciding whether a week is closed and
 * for generating/acknowledging the report. This screen only renders the saved
 * week/report state and sends explicit user actions to the existing endpoints.
 */

import { StatusBar } from 'expo-status-bar';
import { useState, type ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Api } from '../../api/endpoints';
import {
  adjustmentDirectionLabel,
  notCompletedReasonLabel,
} from '../../api/labels';
import type { WeeklyReportResponse, WeekResponse } from '../../api/types';
import {
  useAsyncAction,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import { InlineFeedback } from '../../components/primitives';
import { ErrorState, LoadingState } from '../../components/states/ScreenState';
import { colors } from '../../components/theme';
import { HomeBottomNavigation } from '../home/HomeScreen';
import {
  assertReportMatchesWeek,
  assertWeekMatchesSelection,
  weeklyReportAvailability,
} from './weeklyReportModel';

type WeeklyReportScreenProps = {
  api: Api;
  onBack: () => void;
  onNavigateTab?: (tab: TabId) => void;
  timeZone?: string;
  weekStart?: string;
};

export function WeeklyReportScreen({
  api,
  onBack,
  onNavigateTab,
  timeZone,
  weekStart: selectedWeekStart,
}: WeeklyReportScreenProps) {
  const weekStart = selectedWeekStart ?? weekStartString(new Date(), timeZone);
  const [reportOverride, setReportOverride] = useState<{
    weekStart: string;
    report: WeeklyReportResponse;
  } | null>(null);

  const { state, reload } = useAsyncData<{
    week: WeekResponse;
    storedReport: WeeklyReportResponse | null;
  }>(
    async (signal) => {
      const week = await api.getWeek(weekStart, signal);
      assertWeekMatchesSelection(weekStart, week);
      const availability = weeklyReportAvailability(week);
      const storedReport =
        week.report_id === null
          ? null
          : await api.getWeeklyReport(week.report_id, signal);
      if (storedReport !== null) {
        const expectedStatus =
          availability === 'GENERATED' || availability === 'ACKNOWLEDGED'
            ? availability
            : undefined;
        assertReportMatchesWeek(week, storedReport, expectedStatus);
      }
      return { week, storedReport };
    },
    [api, weekStart],
  );

  const generate = useAsyncAction(async () => {
    if (state.status !== 'ready') return;
    const report = await api.createWeeklyReport(weekStart);
    assertReportMatchesWeek(state.data.week, report, 'GENERATED');
    setReportOverride({
      weekStart,
      report,
    });
  });

  const acknowledge = useAsyncAction(async (reportId: string) => {
    if (state.status !== 'ready') return;
    const report = await api.acknowledgeWeeklyReport(
      reportId,
      new Date().toISOString(),
    );
    assertReportMatchesWeek(state.data.week, report, 'ACKNOWLEDGED');
    setReportOverride({
      weekStart,
      report,
    });
  });

  if (state.status === 'loading') {
    return (
      <ReportPage onBack={onBack} onNavigateTab={onNavigateTab}>
        <View style={styles.stateCard}>
          <LoadingState label="주간 기록을 불러오고 있어요" />
        </View>
      </ReportPage>
    );
  }

  if (state.status === 'error') {
    return (
      <ReportPage onBack={onBack} onNavigateTab={onNavigateTab}>
        <View style={styles.stateCard}>
          <ErrorState message={state.message} onRetry={reload} />
        </View>
      </ReportPage>
    );
  }

  const { week, storedReport } = state.data;
  const visibleReport =
    reportOverride?.weekStart === weekStart
      ? reportOverride.report
      : storedReport;
  const availability = weeklyReportAvailability(week);

  return (
    <ReportPage onBack={onBack} onNavigateTab={onNavigateTab}>
      <WeekSummaryCard week={week} hasReport={visibleReport !== null} />

      {generate.error ? (
        <InlineFeedback tone="warning" message={generate.error} />
      ) : null}

      {visibleReport === null && availability === 'AVAILABLE_TO_CREATE' ? (
        <ReportGenerationCard
          pending={generate.pending}
          onGenerate={() => void generate.run()}
        />
      ) : visibleReport === null ? (
        <OpenWeekCard />
      ) : (
        <ReportDetails
          report={visibleReport}
          pending={acknowledge.pending}
          error={acknowledge.error}
          onAcknowledge={() => void acknowledge.run(visibleReport.report_id)}
        />
      )}
    </ReportPage>
  );
}

function ReportPage({
  children,
  onBack,
  onNavigateTab,
}: {
  children: ReactNode;
  onBack: () => void;
  onNavigateTab?: (tab: TabId) => void;
}) {
  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
      >
        <View style={styles.pageHeader}>
          <Pressable
            accessibilityLabel="운동 캘린더로 돌아가기"
            accessibilityRole="button"
            hitSlop={8}
            onPress={onBack}
            style={styles.backButton}
          >
            <Text style={styles.backGlyph}>‹</Text>
          </Pressable>
          <View style={styles.pageHeading}>
            <Text style={styles.eyebrow}>리포트 · 주간 상세</Text>
            <Text accessibilityRole="header" style={styles.pageTitle}>
              주간 리포트
            </Text>
          </View>
        </View>
        {children}
      </ScrollView>
      <HomeBottomNavigation activeTab="report" onNavigate={onNavigateTab} />
    </SafeAreaView>
  );
}

function WeekSummaryCard({
  week,
  hasReport,
}: {
  week: WeekResponse;
  hasReport: boolean;
}) {
  const closed = week.status_code === 'CLOSED';
  const statusLabel = !closed
    ? '진행 중'
    : hasReport
      ? '리포트 준비됨'
      : '리포트 만들기';

  return (
    <View style={styles.weekCard}>
      <View style={styles.weekCardTop}>
        <View style={styles.weekCardCopy}>
          <Text style={styles.weekLabel}>선택한 주</Text>
          <Text style={styles.weekRange}>
            {formatWeekRange(week.week_start, week.week_end)}
          </Text>
        </View>
        <View
          style={[
            styles.statusChip,
            !closed && styles.statusChipProgress,
            closed && !hasReport && styles.statusChipMake,
          ]}
        >
          <Text
            style={[
              styles.statusChipText,
              !closed && styles.statusChipTextProgress,
              closed && !hasReport && styles.statusChipTextMake,
            ]}
          >
            {statusLabel}
          </Text>
        </View>
      </View>
      <View style={styles.weekGoalRow}>
        <View style={styles.weekGoalCount}>
          <Text style={styles.weekGoalValue}>{week.target_workout_count}</Text>
          <Text style={styles.weekGoalUnit}>회</Text>
        </View>
        <Text style={styles.weekGoalLabel}>이 주에 계획한 운동</Text>
      </View>
    </View>
  );
}

function ReportGenerationCard({
  pending,
  onGenerate,
}: {
  pending: boolean;
  onGenerate: () => void;
}) {
  return (
    <View style={styles.generationCard}>
      <View style={styles.sectionHeadingRow}>
        <View style={styles.sectionNumber}>
          <Text style={styles.sectionNumberText}>1</Text>
        </View>
        <Text style={styles.sectionEyebrow}>한 주 돌아보기</Text>
      </View>
      <Text style={styles.generationTitle}>
        운동 기록을 리포트로 정리할까요?
      </Text>
      <Text style={styles.generationBody}>
        저장된 완료·부분 수행·미수행 기록을 바탕으로 다음 주에 이어갈 방향을
        정리해요.
      </Text>
      <View style={styles.generationChecklist}>
        <ChecklistRow label="이번 주 수행 기록 요약" />
        <ChecklistRow label="꾸준함과 조정 패턴 정리" />
        <ChecklistRow label="다음 주를 위한 한 가지 제안" />
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: pending, disabled: pending }}
        disabled={pending}
        onPress={onGenerate}
        style={({ pressed }) => [
          styles.generateButton,
          pressed && !pending && styles.buttonPressed,
          pending && styles.buttonDisabled,
        ]}
      >
        <Text style={styles.generateButtonText}>
          {pending ? '리포트를 만들고 있어요…' : '리포트 생성하기'}
        </Text>
      </Pressable>
      <Text style={styles.generationFootnote}>
        리포트를 열어보는 것만으로는 확인 처리되지 않아요.
      </Text>
    </View>
  );
}

function OpenWeekCard() {
  return (
    <View style={styles.generationCard}>
      <View style={styles.sectionHeadingRow}>
        <View style={styles.sectionNumber}>
          <Text style={styles.sectionNumberText}>·</Text>
        </View>
        <Text style={styles.sectionEyebrow}>이번 주 진행 상황</Text>
      </View>
      <Text style={styles.generationTitle}>아직 진행 중인 주예요</Text>
      <Text style={styles.generationBody}>
        서버에서 이 주를 마감한 뒤 리포트를 만들 수 있어요.
      </Text>
    </View>
  );
}

function ChecklistRow({ label }: { label: string }) {
  return (
    <View style={styles.checklistRow}>
      <View style={styles.checkmark}>
        <Text style={styles.checkmarkText}>✓</Text>
      </View>
      <Text style={styles.checklistLabel}>{label}</Text>
    </View>
  );
}

function ReportDetails({
  report,
  pending,
  error,
  onAcknowledge,
}: {
  report: WeeklyReportResponse;
  pending: boolean;
  error: string | null;
  onAcknowledge: () => void;
}) {
  const acknowledged = report.acknowledged_at !== null;

  return (
    <>
      <View style={styles.reportCard}>
        <View style={styles.reportHeadingRow}>
          <View style={styles.reportHeadingCopy}>
            <Text style={styles.sectionEyebrow}>이번 주 한눈에 보기</Text>
            <Text style={styles.reportTitle}>{report.summary}</Text>
          </View>
          <View style={styles.completionBadge}>
            <Text style={styles.completionValue}>
              {Math.round(report.completion_rate * 100)}%
            </Text>
            <Text style={styles.completionLabel}>완료율</Text>
          </View>
        </View>

        <View style={styles.counts}>
          <Count label="완료" tone="success" value={report.counts.completed} />
          <Count label="부분" tone="partial" value={report.counts.partial} />
          <Count
            label="미수행"
            tone="muted"
            value={report.counts.not_completed}
          />
          <Count
            label="안전 중단"
            tone="danger"
            value={report.counts.stopped_for_safety}
          />
        </View>
      </View>

      <View style={styles.insightCard}>
        <Text style={styles.insightEyebrow}>저장된 기록에서 본 흐름</Text>
        <Text style={styles.insightBody}>{report.decision_summary}</Text>
        {report.primary_miss_reason_code ? (
          <View style={styles.reasonPill}>
            <Text style={styles.reasonPillLabel}>가장 큰 미수행 이유</Text>
            <Text style={styles.reasonPillValue}>
              {notCompletedReasonLabel(report.primary_miss_reason_code)}
            </Text>
          </View>
        ) : null}
      </View>

      <View style={styles.nextCard}>
        <View style={styles.nextMarker}>
          <Text style={styles.nextMarkerText}>→</Text>
        </View>
        <View style={styles.nextCopy}>
          <Text style={styles.nextEyebrow}>다음 주 방향</Text>
          <Text style={styles.nextTitle}>
            {adjustmentDirectionLabel(report.adjustment_direction_code)}
          </Text>
          <Text style={styles.nextBody}>{report.next_action}</Text>
        </View>
      </View>

      {error ? <InlineFeedback tone="error" message={error} /> : null}

      {acknowledged ? (
        <View style={styles.acknowledgedCard}>
          <View style={styles.acknowledgedMark}>
            <Text style={styles.acknowledgedMarkText}>✓</Text>
          </View>
          <View style={styles.acknowledgedCopy}>
            <Text style={styles.acknowledgedTitle}>리포트를 확인했어요</Text>
            <Text style={styles.acknowledgedBody}>
              이제 다음 주 계획을 확정할 수 있어요.
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.acknowledgeSection}>
          <Text style={styles.acknowledgeHint}>
            내용을 확인했다면 다음 주 계획에 반영할 수 있도록 알려주세요.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy: pending, disabled: pending }}
            disabled={pending}
            onPress={onAcknowledge}
            style={({ pressed }) => [
              styles.acknowledgeButton,
              pressed && !pending && styles.buttonPressed,
              pending && styles.buttonDisabled,
            ]}
          >
            <Text style={styles.acknowledgeButtonText}>
              {pending ? '확인을 저장하고 있어요…' : '리포트 확인했어요'}
            </Text>
          </Pressable>
        </View>
      )}
    </>
  );
}

function Count({
  label,
  tone,
  value,
}: {
  label: string;
  tone: 'success' | 'partial' | 'muted' | 'danger';
  value: number;
}) {
  return (
    <View style={styles.count}>
      <Text
        style={[
          styles.countValue,
          tone === 'partial' && styles.countValuePartial,
          tone === 'muted' && styles.countValueMuted,
          tone === 'danger' && styles.countValueDanger,
        ]}
      >
        {value}
      </Text>
      <Text style={styles.countLabel}>{label}</Text>
    </View>
  );
}

function formatWeekRange(weekStart: string, weekEnd: string): string {
  const compact = (value: string) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (match === null) return value;
    return `${Number(match[2])}.${Number(match[3])}`;
  };
  return `${compact(weekStart)} – ${compact(weekEnd)}`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  scroll: {
    flex: 1,
  },
  content: {
    gap: 12,
    paddingTop: 42,
    paddingHorizontal: 16,
    paddingBottom: 22,
  },
  pageHeader: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  backButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 22,
    backgroundColor: colors.surface,
  },
  backGlyph: {
    marginTop: -3,
    color: colors.textSub,
    fontSize: 34,
    fontWeight: '500',
    lineHeight: 38,
  },
  pageHeading: {
    minWidth: 0,
    flex: 1,
  },
  eyebrow: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '700',
  },
  pageTitle: {
    marginTop: 1,
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
  },
  stateCard: {
    minHeight: 260,
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: colors.surface,
    padding: 18,
  },
  weekCard: {
    borderWidth: 1.5,
    borderColor: '#7FAE5C',
    borderRadius: 22,
    backgroundColor: colors.greenTint,
    padding: 16,
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  weekCardTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  weekCardCopy: {
    minWidth: 0,
    flex: 1,
  },
  weekLabel: {
    color: colors.greenText,
    fontSize: 11.5,
    fontWeight: '800',
  },
  weekRange: {
    marginTop: 3,
    color: colors.text,
    fontSize: 23,
    fontWeight: '800',
  },
  statusChip: {
    borderWidth: 1.5,
    borderColor: colors.greenBorder,
    borderRadius: 999,
    backgroundColor: colors.surface,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusChipProgress: {
    borderColor: colors.greenBorder,
    backgroundColor: colors.surface,
  },
  statusChipMake: {
    borderColor: '#EFC02F',
    backgroundColor: colors.yellow,
  },
  statusChipText: {
    color: colors.greenText,
    fontSize: 10.5,
    fontWeight: '800',
  },
  statusChipTextProgress: {
    color: colors.greenText,
  },
  statusChipTextMake: {
    color: '#3A320F',
  },
  weekGoalRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 8,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#D6E4C5',
    paddingTop: 12,
  },
  weekGoalCount: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 2,
  },
  weekGoalValue: {
    color: colors.greenText,
    fontSize: 24,
    fontWeight: '800',
  },
  weekGoalUnit: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
  },
  weekGoalLabel: {
    color: colors.textSub,
    fontSize: 12.5,
    fontWeight: '700',
  },
  generationCard: {
    borderRadius: 22,
    backgroundColor: colors.surface,
    padding: 18,
  },
  sectionHeadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  sectionNumber: {
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: colors.greenTint,
  },
  sectionNumberText: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
  },
  sectionEyebrow: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
  },
  generationTitle: {
    marginTop: 13,
    color: colors.text,
    fontSize: 19,
    fontWeight: '800',
    lineHeight: 27,
  },
  generationBody: {
    marginTop: 8,
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 20,
  },
  generationChecklist: {
    gap: 9,
    marginTop: 16,
    borderRadius: 14,
    backgroundColor: colors.surfaceAlt,
    padding: 13,
  },
  checklistRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  checkmark: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: colors.greenBand,
  },
  checkmarkText: {
    color: colors.greenText,
    fontSize: 11,
    fontWeight: '800',
  },
  checklistLabel: {
    color: colors.textSub,
    fontSize: 12.5,
    fontWeight: '700',
  },
  generateButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 18,
    borderBottomWidth: 4,
    borderBottomColor: colors.yellowDeep,
    borderRadius: 15,
    backgroundColor: colors.yellow,
    paddingHorizontal: 16,
    paddingVertical: 13,
  },
  generateButtonText: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  generationFootnote: {
    marginTop: 10,
    color: colors.textMuted,
    fontSize: 10.5,
    lineHeight: 16,
    textAlign: 'center',
  },
  reportCard: {
    borderRadius: 22,
    backgroundColor: colors.surface,
    padding: 16,
  },
  reportHeadingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  reportHeadingCopy: {
    minWidth: 0,
    flex: 1,
  },
  reportTitle: {
    marginTop: 6,
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
    lineHeight: 24,
  },
  completionBadge: {
    width: 66,
    height: 66,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 5,
    borderColor: '#7FAE5C',
    borderRadius: 33,
    backgroundColor: colors.greenTint,
  },
  completionValue: {
    color: colors.greenText,
    fontSize: 16,
    fontWeight: '800',
  },
  completionLabel: {
    marginTop: 1,
    color: colors.textMuted,
    fontSize: 9.5,
    fontWeight: '700',
  },
  counts: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: 14,
  },
  count: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 2,
    paddingVertical: 10,
  },
  countValue: {
    color: colors.greenText,
    fontSize: 18,
    fontWeight: '800',
  },
  countValuePartial: {
    color: '#B58A1E',
  },
  countValueMuted: {
    color: colors.textMuted,
  },
  countValueDanger: {
    color: colors.danger,
  },
  countLabel: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 9.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  insightCard: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  insightEyebrow: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '800',
  },
  insightBody: {
    marginTop: 8,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 21,
  },
  reasonPill: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    marginTop: 13,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  reasonPillLabel: {
    color: colors.textMuted,
    fontSize: 10.5,
    fontWeight: '700',
  },
  reasonPillValue: {
    color: colors.textSub,
    fontSize: 11,
    fontWeight: '800',
  },
  nextCard: {
    flexDirection: 'row',
    gap: 12,
    borderRadius: 18,
    backgroundColor: colors.greenBand,
    padding: 16,
  },
  nextMarker: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 17,
    backgroundColor: colors.surface,
  },
  nextMarkerText: {
    color: colors.greenText,
    fontSize: 18,
    fontWeight: '800',
  },
  nextCopy: {
    minWidth: 0,
    flex: 1,
  },
  nextEyebrow: {
    color: colors.greenText,
    fontSize: 10.5,
    fontWeight: '800',
  },
  nextTitle: {
    marginTop: 2,
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
  },
  nextBody: {
    marginTop: 5,
    color: colors.textSub,
    fontSize: 12.5,
    lineHeight: 19,
  },
  acknowledgeSection: {
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 14,
  },
  acknowledgeHint: {
    color: colors.textMuted,
    fontSize: 11.5,
    lineHeight: 17,
    textAlign: 'center',
  },
  acknowledgeButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 11,
    borderRadius: 15,
    backgroundColor: colors.green,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  acknowledgeButtonText: {
    color: colors.surface,
    fontSize: 15,
    fontWeight: '800',
  },
  acknowledgedCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1.5,
    borderColor: colors.successBorder,
    borderRadius: 18,
    backgroundColor: colors.successSurface,
    padding: 15,
  },
  acknowledgedMark: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: colors.green,
  },
  acknowledgedMarkText: {
    color: colors.surface,
    fontSize: 17,
    fontWeight: '800',
  },
  acknowledgedCopy: {
    minWidth: 0,
    flex: 1,
  },
  acknowledgedTitle: {
    color: colors.greenText,
    fontSize: 14,
    fontWeight: '800',
  },
  acknowledgedBody: {
    marginTop: 2,
    color: colors.textSub,
    fontSize: 11.5,
    lineHeight: 17,
  },
  buttonPressed: {
    opacity: 0.82,
  },
  buttonDisabled: {
    opacity: 0.55,
  },
});
