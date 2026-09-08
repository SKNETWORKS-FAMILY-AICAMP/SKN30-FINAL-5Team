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
import type {
  WeeklyPlanRevisionResponse,
  WeeklyReportResponse,
  WeekResponse,
} from '../../api/types';
import {
  useAsyncAction,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import {
  GradientActionButton,
  InlineFeedback,
} from '../../components/primitives';
import { ErrorState, LoadingState } from '../../components/states/ScreenState';
import { colors } from '../../components/theme';
import { HomeBottomNavigation } from '../home/HomeScreen';
import {
  assertReportMatchesWeek,
  assertWeekMatchesSelection,
  weeklyReportAvailability,
} from './weeklyReportModel';
import { WeeklyReportSummary } from './WeeklyReportSummary';

type WeeklyReportScreenProps = {
  api: Api;
  now?: Date;
  onBack: () => void;
  onNavigateTab?: (tab: TabId) => void;
  onPlanRevisionChange?: (revision: WeeklyPlanRevisionResponse) => void;
  planRevision?: WeeklyPlanRevisionResponse | null;
  timeZone?: string;
  weekStart?: string;
};

export function WeeklyReportScreen({
  api,
  now = new Date(),
  onBack,
  onNavigateTab,
  onPlanRevisionChange,
  planRevision = null,
  timeZone,
  weekStart: selectedWeekStart,
}: WeeklyReportScreenProps) {
  const weekStart = selectedWeekStart ?? weekStartString(now, timeZone);
  const nextWeekStart = shiftLocalDate(weekStart, 7);
  const canApplyNextPlan = nextWeekStart === weekStartString(now, timeZone);
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

  const saveNextPlan = async (reportId: string) => {
    if (
      !canApplyNextPlan ||
      nextWeekStart === null ||
      onPlanRevisionChange === undefined
    ) {
      return;
    }
    const revision = await api.createInitialWeeklyPlan(nextWeekStart);
    if (
      revision.week_start !== nextWeekStart ||
      revision.source_weekly_report_id !== reportId
    ) {
      throw new Error(
        '다음 주 계획 정보가 리포트와 일치하지 않습니다. 다시 시도해주세요.',
      );
    }
    onPlanRevisionChange(revision);
  };

  const applyNextPlan = useAsyncAction(async (reportId: string) => {
    await saveNextPlan(reportId);
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
    await saveNextPlan(reportId);
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
  const appliedPlan =
    visibleReport !== null &&
    planRevision?.week_start === nextWeekStart &&
    planRevision.source_weekly_report_id === visibleReport.report_id
      ? planRevision
      : null;

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
          targetWorkoutCount={week.target_workout_count}
          pending={acknowledge.pending}
          error={acknowledge.error}
          onAcknowledge={() => void acknowledge.run(visibleReport.report_id)}
          nextPlan={appliedPlan}
          nextPlanPending={applyNextPlan.pending}
          nextPlanError={applyNextPlan.error}
          onRetryNextPlan={
            !canApplyNextPlan ||
            onPlanRevisionChange === undefined ||
            nextWeekStart === null
              ? undefined
              : () => {
                  acknowledge.clearError();
                  void applyNextPlan.run(visibleReport.report_id);
                }
          }
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
  const statusLabel = !closed ? '진행 중' : hasReport ? '리포트 준비됨' : null;

  return (
    <View style={styles.weekCard}>
      <View style={styles.weekCardTop}>
        <View style={styles.weekCardCopy}>
          <Text style={styles.weekLabel}>선택한 주</Text>
          <Text style={styles.weekRange}>
            {formatWeekRange(week.week_start, week.week_end)}
          </Text>
        </View>
        {statusLabel !== null ? (
          <View
            style={[styles.statusChip, !closed && styles.statusChipProgress]}
          >
            <Text
              style={[
                styles.statusChipText,
                !closed && styles.statusChipTextProgress,
              ]}
            >
              {statusLabel}
            </Text>
          </View>
        ) : null}
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
      <GradientActionButton
        accessibilityState={{ busy: pending }}
        disabled={pending}
        label={pending ? '리포트를 만들고 있어요…' : '리포트 생성하기'}
        labelStyle={styles.generateButtonText}
        onPress={onGenerate}
        style={styles.generateButton}
        testID="weekly-report-generate"
      />
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
  targetWorkoutCount,
  pending,
  error,
  onAcknowledge,
  nextPlan,
  nextPlanPending,
  nextPlanError,
  onRetryNextPlan,
}: {
  report: WeeklyReportResponse;
  targetWorkoutCount: number;
  pending: boolean;
  error: string | null;
  onAcknowledge: () => void;
  nextPlan: WeeklyPlanRevisionResponse | null;
  nextPlanPending: boolean;
  nextPlanError: string | null;
  onRetryNextPlan?: () => void;
}) {
  const acknowledged = report.acknowledged_at !== null;

  return (
    <>
      <WeeklyReportSummary
        report={report}
        targetWorkoutCount={targetWorkoutCount}
      />

      <View style={styles.reportStep}>
        {error && !acknowledged ? (
          <InlineFeedback tone="error" message={error} />
        ) : null}

        {acknowledged ? (
          <>
            <View style={styles.acknowledgedCard}>
              <View style={styles.acknowledgedMark}>
                <Text style={styles.acknowledgedMarkText}>✓</Text>
              </View>
              <View style={styles.acknowledgedCopy}>
                <Text style={styles.acknowledgedTitle}>
                  리포트를 확인했어요
                </Text>
                <Text style={styles.acknowledgedBody}>
                  확인한 내용을 다음 주 계획에 연결해요.
                </Text>
              </View>
            </View>
            {onRetryNextPlan ? (
              <NextPlanApplicationCard
                error={error ?? nextPlanError}
                onRetry={onRetryNextPlan}
                pending={pending || nextPlanPending}
                revision={nextPlan}
              />
            ) : null}
          </>
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
      </View>
    </>
  );
}

function NextPlanApplicationCard({
  error,
  onRetry,
  pending,
  revision,
}: {
  error: string | null;
  onRetry: () => void;
  pending: boolean;
  revision: WeeklyPlanRevisionResponse | null;
}) {
  const finalized = revision?.finalized === true && revision.routine !== null;
  const draft = revision !== null && !finalized;

  return (
    <View
      accessibilityRole={error || draft ? 'alert' : undefined}
      style={[
        styles.applicationCard,
        finalized && styles.applicationCardSuccess,
        (error || draft) && styles.applicationCardWarning,
      ]}
    >
      <Text style={styles.applicationEyebrow}>다음 주 계획</Text>
      <Text style={styles.applicationTitle}>
        {pending
          ? '다음 주 계획에 반영하고 있어요'
          : finalized
            ? '다음 주 계획에 반영했어요'
            : draft
              ? '계획 초안은 저장됐지만 아직 확정되지 않았어요'
              : '다음 주 계획 반영이 필요해요'}
      </Text>
      {revision ? (
        <Text style={styles.applicationBody}>
          {formatWeekRange(revision.week_start, revision.week_end)} · 홈에서
          해당 주의 최종 루틴을 확인할 수 있어요.
        </Text>
      ) : null}
      {error ? <InlineFeedback tone="error" message={error} /> : null}
      {!pending && revision === null ? (
        <Pressable
          accessibilityRole="button"
          onPress={onRetry}
          style={({ pressed }) => [
            styles.applicationButton,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.applicationButtonText}>
            {error ? '다시 반영하기' : '다음 주 계획 반영하기'}
          </Text>
        </Pressable>
      ) : null}
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

function shiftLocalDate(value: string, days: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) return null;
  const date = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
  );
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
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
    borderColor: '#E0A742',
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
  statusChipText: {
    color: colors.greenText,
    fontSize: 10.5,
    fontWeight: '800',
  },
  statusChipTextProgress: {
    color: colors.greenText,
  },
  weekGoalRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 8,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#F1D39A',
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
  reportStep: {
    gap: 10,
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
    marginTop: 18,
  },
  generateButtonText: {
    color: '#5A4636',
    fontSize: 18,
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
    borderColor: '#E0A742',
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
    color: '#A45F00',
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
  safetyStoppedCard: {
    minHeight: 66,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 10,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    borderRadius: 14,
    backgroundColor: colors.dangerSurface,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  safetyStoppedCopy: {
    minWidth: 0,
    flex: 1,
    gap: 3,
  },
  safetyStoppedLabel: {
    color: colors.danger,
    fontSize: 12.5,
    fontWeight: '800',
  },
  safetyStoppedNote: {
    color: colors.textMuted,
    fontSize: 10.5,
    lineHeight: 16,
  },
  safetyStoppedValueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 2,
  },
  safetyStoppedValue: {
    color: colors.danger,
    fontSize: 21,
    fontWeight: '900',
  },
  safetyStoppedUnit: { color: colors.danger, fontSize: 11, fontWeight: '800' },
  rateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: 12,
  },
  rateLabel: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '700',
  },
  rateValue: {
    color: colors.greenText,
    fontSize: 14,
    fontWeight: '800',
  },
  patternCard: {
    gap: 10,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  patternRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  patternLabel: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  patternValue: {
    minWidth: 0,
    flex: 1,
    color: colors.textSub,
    fontSize: 11.5,
    fontWeight: '800',
    textAlign: 'right',
  },
  blockerCard: {
    gap: 14,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  blockerGroup: {
    gap: 8,
  },
  blockerGroupLabel: {
    color: colors.textMuted,
    fontSize: 10.5,
    fontWeight: '800',
  },
  blockerList: {
    gap: 7,
  },
  blockerReasonChip: {
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  blockerReasonText: {
    color: colors.textSub,
    fontSize: 11.5,
    fontWeight: '800',
  },
  weekdayList: {
    gap: 7,
  },
  weekdayChip: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  weekdayChipLabel: {
    color: colors.text,
    fontSize: 11.5,
    fontWeight: '800',
  },
  weekdayCountMuted: {
    color: colors.textMuted,
    fontSize: 10.5,
    fontWeight: '700',
  },
  weekdayCountDanger: {
    color: colors.danger,
    fontSize: 10.5,
    fontWeight: '700',
  },
  emptyBlockerText: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 20,
    textAlign: 'center',
  },
  learningNote: {
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    color: colors.textMuted,
    fontSize: 11.5,
    lineHeight: 18,
    paddingTop: 12,
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
    color: colors.text,
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
    color: colors.text,
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
  applicationCard: {
    gap: 8,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 15,
  },
  applicationCardSuccess: {
    borderColor: colors.successBorder,
    backgroundColor: colors.successSurface,
  },
  applicationCardWarning: {
    borderColor: '#D98B16',
    backgroundColor: '#FFF3D4',
  },
  applicationEyebrow: {
    color: colors.greenText,
    fontSize: 10.5,
    fontWeight: '800',
  },
  applicationTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 23,
  },
  applicationBody: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
  },
  applicationButton: {
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
    borderRadius: 14,
    backgroundColor: colors.green,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  applicationButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  buttonPressed: {
    opacity: 0.82,
  },
  buttonDisabled: {
    opacity: 0.55,
  },
});
