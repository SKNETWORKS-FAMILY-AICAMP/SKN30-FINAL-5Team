/**
 * Weekly status, report generation and acknowledgement.
 *
 * The week closes logically on the server, so this screen shows the server's
 * week state and surfaces `409 WEEK_NOT_CLOSED` as an explanatory state rather
 * than hiding the button. Acknowledgement is an explicit user action; opening
 * the report never records it.
 */

import { StyleSheet, Text, View } from 'react-native';

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
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  ErrorState,
  InfoNotice,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import { useState } from 'react';

export function WeeklyReportScreen({
  api,
  onBack,
  timeZone,
  weekStart: selectedWeekStart,
}: {
  api: Api;
  onBack: () => void;
  timeZone?: string;
  weekStart?: string;
}) {
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
      const storedReport =
        week.report_id === null
          ? null
          : await api.getWeeklyReport(week.report_id, signal);
      return { week, storedReport };
    },
    [api, weekStart],
  );

  const generate = useAsyncAction(async () => {
    setReportOverride({
      weekStart,
      report: await api.createWeeklyReport(weekStart),
    });
  });

  const acknowledge = useAsyncAction(async (reportId: string) => {
    setReportOverride({
      weekStart,
      report: await api.acknowledgeWeeklyReport(
        reportId,
        new Date().toISOString(),
      ),
    });
  });

  if (state.status === 'loading') {
    return (
      <ScreenShell bands>
        <ScreenHeading title="주간 리포트" onBand />
        <LoadingState />
      </ScreenShell>
    );
  }

  if (state.status === 'error') {
    return (
      <ScreenShell bands>
        <ScreenHeading title="주간 리포트" onBand />
        <ErrorState message={state.message} onRetry={reload} />
        <Button label="돌아가기" tone="secondary" onPress={onBack} />
      </ScreenShell>
    );
  }

  const { week, storedReport } = state.data;
  const visibleReport =
    reportOverride?.weekStart === weekStart
      ? reportOverride.report
      : storedReport;

  return (
    <ScreenShell bands>
      <ScreenHeading
        title="주간 리포트"
        subtitle={`${week.week_start} ~ ${week.week_end}`}
        onBand
      />

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>
          {week.status_code === 'CLOSED' ? '마감된 주' : '진행 중인 주'}
        </Text>
        <Text style={styles.body}>목표 {week.target_workout_count}회</Text>
        {week.status_code === 'OPEN' ? (
          <Text style={styles.note}>
            이번 주가 끝나면 리포트를 만들 수 있어요. 리포트를 확인해야 다음 주
            계획을 확정할 수 있어요.
          </Text>
        ) : null}
      </Card>

      {generate.error ? (
        <InlineFeedback tone="warning" message={generate.error} />
      ) : null}

      {visibleReport === null ? (
        <Button
          label={generate.pending ? '만드는 중…' : '리포트 생성하기'}
          disabled={generate.pending}
          onPress={() => void generate.run()}
        />
      ) : (
        <ReportCard
          report={visibleReport}
          pending={acknowledge.pending}
          error={acknowledge.error}
          onAcknowledge={() => void acknowledge.run(visibleReport.report_id)}
        />
      )}

      <Button label="돌아가기" tone="secondary" onPress={onBack} />
    </ScreenShell>
  );
}

function ReportCard({
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
      <Card style={styles.card}>
        <Text style={styles.cardTitle}>{report.summary}</Text>
        <View style={styles.counts}>
          <Count label="완료" value={report.counts.completed} />
          <Count label="일부" value={report.counts.partial} />
          <Count label="미수행" value={report.counts.not_completed} />
          <Count label="안전 중단" value={report.counts.stopped_for_safety} />
        </View>
        <Text style={styles.body}>{report.decision_summary}</Text>
        <Text style={styles.note}>
          다음 주 방향:{' '}
          {adjustmentDirectionLabel(report.adjustment_direction_code)}
        </Text>
        <Text style={styles.note}>{report.next_action}</Text>
        {report.primary_miss_reason_code ? (
          <Text style={styles.note}>
            가장 큰 이유:{' '}
            {notCompletedReasonLabel(report.primary_miss_reason_code)}
          </Text>
        ) : null}
      </Card>

      {error ? <InlineFeedback tone="error" message={error} /> : null}

      {acknowledged ? (
        <InfoNotice
          title="리포트를 확인했어요"
          message="이제 다음 주 계획을 확정할 수 있어요."
        />
      ) : (
        <Button
          label={pending ? '저장 중…' : '리포트 확인'}
          disabled={pending}
          onPress={onAcknowledge}
        />
      )}
    </>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.count}>
      <Text style={styles.countValue}>{value}</Text>
      <Text style={styles.countLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 23,
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
  counts: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  count: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
    borderRadius: 12,
    backgroundColor: colors.surfaceAlt,
    paddingVertical: spacing.md,
  },
  countValue: {
    color: colors.primary,
    fontSize: 20,
    fontWeight: '700',
  },
  countLabel: {
    color: colors.textMuted,
    fontSize: 11,
  },
});
